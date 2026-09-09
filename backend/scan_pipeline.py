"""One bounded, checkpointable piece of a weekly intelligence run."""
from datetime import datetime
from pathlib import Path
import json
import tempfile

from gta_weekly_scraper import (
    find_latest_powerupgaming_weekly_page, find_latest_gtabase_weekly_page,
    find_latest_rockstarintel_weekly_page, parse_weekly_generic,
    gta_week_window_from_date, now_kw,
)
from intelligence_engine import _merge_rows, _sections, _week_for_url, _write_pdf
from vehicle_intelligence import collect_article_images, enrich_vehicles, looks_like_vehicle, load_catalog, vehicle_key
from history_store import save_snapshot
from sendMail import send_email_with_attachment
from storage import cloud_mode, store

PROVIDERS = [
    ("PowerUpGaming", find_latest_powerupgaming_weekly_page),
    ("GTABase", find_latest_gtabase_weekly_page),
    ("RockstarINTEL", find_latest_rockstarintel_weekly_page),
]


def advance(job_id, state, params, progress, cancel):
    if cancel():
        raise InterruptedError("Run cancelled by user")
    phase = state.get("phase", "discover")
    state.setdefault("warnings", [])
    if phase == "discover":
        state.setdefault("sources", [])
        index = state.get("index", 0)
        manual = params.get("manual_url")
        if manual:
            state["sources"] = [{"url": manual, "provider": "Manual", "label": "Manual article"}]
            index = len(PROVIDERS)
        else:
            name, discover = PROVIDERS[index]
            progress("discover", 5 + index * 6, f"Discovering {name} weekly article…")
            try:
                url, title = discover()
                state["sources"].append({"url": url, "provider": name, "label": title})
            except InterruptedError:
                raise
            except Exception as exc:
                warning = f"{name} unavailable: {type(exc).__name__}"
                state["warnings"].append(warning)
                progress("discover", 10 + index * 6, warning, {"level": "warning"})
            index += 1
        state["index"] = index
        if index >= len(PROVIDERS):
            if not state["sources"]:
                raise ValueError("No source was reachable. Retry or provide a weekly article URL.")
            state.update(phase="extract", index=0, extracted=[])
        return state, None

    if phase == "extract":
        index = state["index"]
        source = state["sources"][index]
        progress("extract", 25 + index * 8, f"Reading {source['provider']}…")
        try:
            rows = parse_weekly_generic(source["url"])
            week = _week_for_url(source["url"])
            if rows:
                state["extracted"].append({
                    "source": source, "rows": rows,
                    "week": [d.date().isoformat() for d in week] if week else None,
                    "images": collect_article_images(source["url"]),
                })
                progress("extract", 30 + index * 8, f"{source['provider']}: {len(rows)} candidate items")
            else:
                state["warnings"].append(f"{source['provider']}: no weekly items extracted.")
        except InterruptedError:
            raise
        except Exception as exc:
            attempt = state.get("attempt", 1)
            if attempt < params.get("source_retries", 2):
                state["attempt"] = attempt + 1
                progress("extract", 25 + index * 8, f"Retrying {source['provider']} after {type(exc).__name__}", {"level": "warning"})
                return state, None
            state["warnings"].append(f"{source['provider']} extraction failed: {type(exc).__name__}")
        state.pop("attempt", None)
        state["index"] += 1
        if state["index"] >= len(state["sources"]):
            state["phase"] = "normalize"
        return state, None

    if phase == "normalize":
        extracted = state["extracted"]
        if not extracted:
            raise ValueError("Sources were found, but no weekly rows could be extracted.")
        weeks = [entry["week"] for entry in extracted if entry["week"]]
        week = max(weeks) if weeks else [d.date().isoformat() for d in gta_week_window_from_date(now_kw())]
        accepted = [entry for entry in extracted if entry["week"] == week or (not weeks and not entry["week"])]
        for entry in extracted:
            if entry not in accepted:
                state["warnings"].append(f"Skipped {entry['source']['provider']}: its week differs or could not be established.")
        rows = _merge_rows([(entry["source"], entry["rows"]) for entry in accepted])
        verified = sum(row["verified"] for row in rows)
        today = now_kw().date().isoformat()
        current = week[0] <= today <= week[1]
        if not current:
            state["warnings"].append(f"These sources describe {week[0]} to {week[1]}, not the current week.")
        if not weeks:
            state["warnings"].append("No article date was established; the displayed week is estimated.")
        state["dataset"] = {
            "id": job_id, "schema_version": 3, "week_start": week[0], "week_end": week[1],
            "week_resolution": "article" if weeks else "estimated-current-week", "is_current": current and bool(weeks),
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "sources": [entry["source"] for entry in accepted], "items": rows, "sections": _sections(rows),
            "vehicles": [], "row_count": len(rows), "verified_count": verified,
            "overall_confidence": round(sum(row["confidence"] for row in rows) / max(1, len(rows)), 3),
            "warnings": state["warnings"], "pdf_path": None, "json_path": None,
            "exports": {"pdf": params.get("generate_pdf", True), "json": params.get("save_json", True)},
            "email_sent": False, "email_error": None,
        }
        state["images"] = {entry["source"]["url"]: entry["images"] for entry in accepted}
        catalog = load_catalog()
        candidates = {}
        for row in rows:
            if row.get("entity_type") == "vehicle" or looks_like_vehicle(row["category"], row["item"], catalog):
                candidates.setdefault(vehicle_key(row["item"]), row)
        state["candidates"] = list(candidates.values())
        state.update(phase="enrich", index=0)
        progress("verify", 62, f"Normalized {len(rows)} items; {verified} agree across sources")
        return state, None

    if phase == "enrich":
        candidates = state["candidates"]
        index = state["index"]
        if index < len(candidates):
            progress("enrich", 65 + int(20 * index / max(1, len(candidates))), f"Resolving vehicle {index + 1} of {len(candidates)}…")
            vehicles = enrich_vehicles([candidates[index]], state["images"])
            known = {v["name"].casefold() for v in state["dataset"]["vehicles"]}
            state["dataset"]["vehicles"].extend(v for v in vehicles if v["name"].casefold() not in known)
            state["index"] += 1
        if state["index"] >= len(candidates):
            state["phase"] = "export"
        return state, None

    if phase == "export":
        data = state["dataset"]
        data["stats"] = {
            "sources": len(data["sources"]), "items": data["row_count"], "verified": data["verified_count"],
            "vehicles": len(data["vehicles"]), "discounts": len(data["sections"].get("Discounts", [])),
            "bonuses": len(data["sections"].get("Bonuses", [])),
        }
        progress("export", 92, "Preparing exports and saving the weekly archive…")
        with tempfile.TemporaryDirectory(prefix="gta-export-") as temp:
            output = Path(temp) if cloud_mode() else Path(params["output_dir"]) / job_id
            output.mkdir(parents=True, exist_ok=True)
            pdf = _write_pdf(data, str(output)) if data["exports"]["pdf"] else None
            if pdf and not cloud_mode():
                data["pdf_path"] = pdf
            if params.get("send_email"):
                # An unknown delivery is never automatically re-sent after a crash.
                claimed = []
                def claim_email(previous):
                    if previous is None:
                        claimed.append(True)
                        return {"status": "attempting"}
                    return previous
                previous = store.mutate("email", job_id, claim_email)
                if claimed:
                    progress("email", 96, "Sending the requested report…")
                    try:
                        cfg = params.get("email_config") or {}
                        send_email_with_attachment(
                            subject=f"GTA Online Weekly Intelligence {data['week_start']} to {data['week_end']}",
                            body=f"Weekly intelligence report for {data['week_start']} to {data['week_end']}.",
                            attachment_path=pdf, smtp_server=cfg.get("smtp_server"), smtp_port=cfg.get("smtp_port"),
                            username=cfg.get("username"), password=cfg.get("password"),
                            email_from=cfg.get("from_addr"), recipients=cfg.get("to_addrs"), use_tls=cfg.get("use_tls", True),
                        )
                        data["email_sent"] = True
                        store.put("email", job_id, {"status": "sent"})
                    except Exception:
                        data["email_error"] = "Email delivery failed. Check the SMTP configuration. Your report is saved."
                        store.put("email", job_id, {"status": "failed"})
                else:
                    data["email_sent"] = previous["status"] == "sent"
                    if not data["email_sent"]:
                        data["email_error"] = "A previous email attempt failed or its delivery could not be confirmed; it was not sent again."
            if data["exports"]["json"] and not cloud_mode():
                data["json_path"] = str(output / "weekly.json")
                Path(data["json_path"]).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        save_snapshot(data)
        return {"phase": "done"}, data
    raise ValueError(f"Unknown scan phase: {phase}")
