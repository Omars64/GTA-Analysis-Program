from __future__ import annotations
import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Optional

from gta_weekly_scraper import (
    find_latest_powerupgaming_weekly_page,
    find_latest_gtabase_weekly_page,
    find_latest_rockstarintel_weekly_page,
    http_get_soup,
    extract_week_range_from_text,
    find_week_range_from_tez2,
    extract_article_publish_dt_kuwait,
    gta_week_from_publish_snap,
    gta_week_window_from_date,
    now_kw,
    parse_weekly_generic,
    PRIORITY_ORDER,
)
from vehicle_intelligence import collect_article_images, enrich_vehicles
from history_store import save_snapshot
from sendMail import send_email_with_attachment

Progress = Callable[[str, int, str, dict | None], None]
Cancel = Callable[[], bool]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _check_cancel(cancel: Optional[Cancel]):
    if cancel and cancel():
        raise InterruptedError("Run cancelled by user")


def _emit(progress: Optional[Progress], stage: str, pct: int, message: str, meta=None):
    if progress:
        progress(stage, pct, message, meta or {})


def _retry(fn, attempts: int, progress, label: str):
    last = None
    for i in range(max(1, attempts)):
        try:
            return fn()
        except Exception as exc:
            last = exc
            _emit(progress, "discover", 8 + i * 2, f"{label} attempt {i+1} failed: {exc}")
            if i + 1 < attempts:
                time.sleep(min(1.5 * (i + 1), 3))
    raise last


def _discover_sources(manual_url: str | None, retries: int, progress=None, cancel=None):
    _check_cancel(cancel)
    if manual_url:
        return [{"url": manual_url.strip(), "label": "Manual", "provider": "Manual"}]
    providers = [
        ("PowerUpGaming", find_latest_powerupgaming_weekly_page),
        ("GTABase", find_latest_gtabase_weekly_page),
        ("RockstarINTEL", find_latest_rockstarintel_weekly_page),
    ]
    found = []
    for idx, (name, fn) in enumerate(providers):
        _check_cancel(cancel)
        _emit(progress, "discover", 7 + idx * 5, f"Discovering {name} weekly article…")
        try:
            url, title = _retry(fn, retries, progress, name)
            found.append({"url": url, "label": f"{name}: {title}", "provider": name})
            _emit(progress, "discover", 10 + idx * 5, f"{name} source found", {"url": url})
        except Exception as exc:
            _emit(progress, "discover", 10 + idx * 5, f"{name} unavailable: {exc}", {"level": "warning"})
    if not found:
        raise RuntimeError("No weekly source could be discovered. Try a manual article URL.")
    return found


def _week_for_url(url: str):
    try:
        soup = http_get_soup(url)
        rng = extract_week_range_from_text(soup)
        if rng:
            return rng
    except Exception:
        pass
    try:
        pub = extract_article_publish_dt_kuwait(url)
        if pub:
            return gta_week_from_publish_snap(pub)
    except Exception:
        pass
    return None


def _resolve_week(primary_url: str, progress=None):
    _emit(progress, "collect", 24, "Resolving GTA Online Thursday → Wednesday week window…")
    try:
        soup = http_get_soup(primary_url)
        rng = extract_week_range_from_text(soup)
        if rng:
            return rng, "article"
    except Exception:
        pass
    try:
        tez = find_week_range_from_tez2()
        if tez:
            return tez, "tez2"
    except Exception:
        pass
    try:
        pub = extract_article_publish_dt_kuwait(primary_url)
        if pub:
            return gta_week_from_publish_snap(pub), "publish-date"
    except Exception:
        pass
    return gta_week_window_from_date(now_kw()), "current-week"


def _merge_rows(source_rows: list[tuple[dict, list[dict]]]):
    groups: list[dict] = []
    for source, rows in source_rows:
        for row in rows:
            cat = row.get("category") or "Uncategorized"
            item = (row.get("item") or "").strip()
            details = (row.get("details") or "").strip()
            nk = _norm(item)
            match = None
            for g in groups:
                if g["category"] != cat:
                    continue
                ratio = SequenceMatcher(None, nk, g["norm_item"]).ratio() if nk and g["norm_item"] else 0
                if nk == g["norm_item"] or (len(nk) > 5 and ratio >= 0.88):
                    match = g
                    break
            if not match:
                match = {
                    "category": cat,
                    "item": item,
                    "details": details,
                    "norm_item": nk,
                    "sources": [],
                    "variants": [],
                }
                groups.append(match)
            if source["url"] not in [s["url"] for s in match["sources"]]:
                match["sources"].append({"url": source["url"], "provider": source["provider"], "label": source["label"]})
            if details and len(details) > len(match["details"]):
                match["details"] = details
            match["variants"].append({"item": item, "details": details, "provider": source["provider"]})

    normalized = []
    for g in groups:
        count = len(g["sources"])
        confidence = min(0.98, 0.62 + 0.16 * max(0, count - 1) + (0.04 if g["details"] else 0))
        if count == 1 and g["sources"][0]["provider"] == "Manual":
            confidence = max(confidence, 0.78)
        normalized.append({
            "category": g["category"],
            "item": g["item"],
            "details": g["details"],
            "source_count": count,
            "verified": count >= 2,
            "confidence": round(confidence, 3),
            "source_urls": [s["url"] for s in g["sources"]],
            "sources": g["sources"],
            "variants": g["variants"],
        })

    def key(row):
        c = row["category"]
        return (PRIORITY_ORDER.index(c) if c in PRIORITY_ORDER else 999, c.lower(), row["item"].lower())
    return sorted(normalized, key=key)


def _sections(rows):
    out = defaultdict(list)
    for row in rows:
        out[row["category"]].append({k: v for k, v in row.items() if k != "category"})
    return dict(out)


def _write_pdf(dataset: dict, output_dir: str):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"GTA_Weekly_Intelligence_{dataset['week_start']}_to_{dataset['week_end']}.pdf")
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=1.6*cm, rightMargin=1.6*cm, topMargin=1.4*cm, bottomMargin=1.4*cm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("GTATitle", parent=styles["Title"], textColor=colors.HexColor("#6d1bd1"), fontSize=22, leading=26)
    sub = ParagraphStyle("GTASub", parent=styles["BodyText"], textColor=colors.HexColor("#475569"), alignment=1)
    head = ParagraphStyle("GTAHead", parent=styles["Heading2"], textColor=colors.HexColor("#d946ef"), spaceBefore=10, spaceAfter=5)
    body = ParagraphStyle("GTABody", parent=styles["BodyText"], fontSize=9.5, leading=13)
    story = [Paragraph("GTA Online Weekly Intelligence", title), Paragraph(f"{dataset['week_start']} → {dataset['week_end']} · confidence {round(dataset['overall_confidence']*100)}%", sub), Spacer(1, 10)]
    for category, items in dataset.get("sections", {}).items():
        story.append(Paragraph(category, head))
        rows = [["Item", "Details", "Confidence"]]
        for item in items:
            rows.append([
                Paragraph(item.get("item") or "—", body),
                Paragraph(item.get("details") or "", body),
                f"{round((item.get('confidence') or 0)*100)}%",
            ])
        table = Table(rows, colWidths=[6.1*cm, 9.1*cm, 1.7*cm], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#17152b")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("GRID", (0,0), (-1,-1), .25, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f8fafc")]),
            ("FONTSIZE", (0,0), (-1,-1), 9),
            ("LEFTPADDING", (0,0), (-1,-1), 5),
            ("RIGHTPADDING", (0,0), (-1,-1), 5),
            ("TOPPADDING", (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ]))
        story.extend([table, Spacer(1, 7)])
    doc.build(story)
    return path


def run_intelligence_scan(*, manual_url=None, output_dir=None, send_email=False, email_config=None,
                          progress: Progress | None = None, cancel: Cancel | None = None,
                          source_retries: int = 2, generate_pdf: bool = True, save_json: bool = True):
    _emit(progress, "initialize", 2, "Initializing Los Santos weekly intelligence engine…")
    _check_cancel(cancel)
    sources = _discover_sources(manual_url, source_retries, progress, cancel)
    _emit(progress, "discover", 20, f"Discovered {len(sources)} usable source(s)")

    (week_start, week_end), week_method = _resolve_week(sources[0]["url"], progress)
    _emit(progress, "collect", 28, f"Resolved week {week_start.date()} → {week_end.date()} via {week_method}")

    accepted = []
    source_rows = []
    source_images_by_url = {}
    total = len(sources)
    for i, source in enumerate(sources):
        _check_cancel(cancel)
        pct = 30 + int((i / max(1,total)) * 25)
        _emit(progress, "extract", pct, f"Extracting {source['provider']}…")
        same_week = True
        if i > 0:
            srng = _week_for_url(source["url"])
            if srng:
                same_week = (srng[0].date(), srng[1].date()) == (week_start.date(), week_end.date())
        if not same_week:
            _emit(progress, "extract", pct + 2, f"Skipped {source['provider']}: article appears to be another week", {"level":"warning"})
            continue
        try:
            rows = _retry(lambda: parse_weekly_generic(source["url"]), source_retries, progress, source["provider"])
            if rows:
                accepted.append(source)
                source_rows.append((source, rows))
                source_images_by_url[source["url"]] = collect_article_images(source["url"])
                _emit(progress, "extract", pct + 5, f"{source['provider']}: extracted {len(rows)} candidate rows")
        except Exception as exc:
            _emit(progress, "extract", pct + 5, f"{source['provider']} extraction failed: {exc}", {"level":"warning"})
    if not source_rows:
        raise RuntimeError("Sources were found, but no weekly rows could be extracted.")

    _check_cancel(cancel)
    _emit(progress, "normalize", 58, "Normalizing source variants and building consensus…")
    rows = _merge_rows(source_rows)
    _emit(progress, "verify", 67, f"Cross-validating {len(rows)} normalized weekly items…")
    verified = sum(1 for r in rows if r["verified"])
    overall = sum(r["confidence"] for r in rows) / max(1, len(rows))

    _check_cancel(cancel)
    _emit(progress, "enrich", 74, "Resolving vehicle entities, metadata and article images…")
    vehicles = enrich_vehicles(rows, source_images_by_url)
    _emit(progress, "enrich", 82, f"Identified {len(vehicles)} weekly vehicle entities")

    dataset = {
        "schema_version": 2,
        "week_start": week_start.date().isoformat(),
        "week_end": week_end.date().isoformat(),
        "week_resolution": week_method,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "sources": accepted,
        "sections": _sections(rows),
        "items": rows,
        "vehicles": vehicles,
        "row_count": len(rows),
        "verified_count": verified,
        "overall_confidence": round(overall, 3),
        "stats": {
            "sources": len(accepted),
            "items": len(rows),
            "verified": verified,
            "vehicles": len(vehicles),
            "discounts": len([r for r in rows if r["category"] == "Discounts"]),
            "bonuses": len([r for r in rows if r["category"] == "Bonuses"]),
        },
        "pdf_path": None,
        "json_path": None,
        "email_sent": False,
        "email_error": None,
    }

    output_dir = os.path.abspath(os.path.expanduser(output_dir or str(Path(__file__).resolve().parent / "runtime" / "exports")))
    os.makedirs(output_dir, exist_ok=True)
    _check_cancel(cancel)
    if save_json:
        _emit(progress, "export", 88, "Saving structured weekly intelligence JSON…")
        json_path = os.path.join(output_dir, f"GTA_Weekly_Intelligence_{dataset['week_start']}_to_{dataset['week_end']}.json")
        Path(json_path).write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
        dataset["json_path"] = json_path
    if generate_pdf:
        _emit(progress, "export", 92, "Rendering PDF from the same structured dataset…")
        dataset["pdf_path"] = _write_pdf(dataset, output_dir)

    _check_cancel(cancel)
    if send_email:
        _emit(progress, "email", 96, "Sending weekly intelligence export by email…")
        if not email_config:
            dataset["email_error"] = "Email enabled but no SMTP configuration was supplied."
        elif not dataset.get("pdf_path"):
            dataset["email_error"] = "Email requires PDF generation to be enabled."
        else:
            try:
                send_email_with_attachment(
                    subject=f"GTA Online Weekly Intelligence {dataset['week_start']} → {dataset['week_end']}",
                    body=f"Weekly intelligence report for {dataset['week_start']} → {dataset['week_end']}.",
                    attachment_path=dataset["pdf_path"],
                    smtp_server=email_config.get("smtp_server"), smtp_port=email_config.get("smtp_port"),
                    username=email_config.get("username"), password=email_config.get("password"),
                    email_from=email_config.get("from_addr"), recipients=email_config.get("to_addrs"),
                    use_tls=bool(email_config.get("use_tls", True)),
                )
                dataset["email_sent"] = True
            except Exception as exc:
                dataset["email_error"] = str(exc)

    # Rewrite JSON with final export/email paths/status.
    if dataset.get("json_path"):
        Path(dataset["json_path"]).write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    save_snapshot(dataset)
    _emit(progress, "complete", 100, f"Complete: {len(rows)} items, {len(vehicles)} vehicles, {verified} cross-source verified")
    return dataset
