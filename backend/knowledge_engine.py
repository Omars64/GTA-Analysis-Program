from __future__ import annotations
import re
from difflib import SequenceMatcher
from history_store import latest_snapshot

def _norm(s):
    return re.sub(r"[^a-z0-9%$]+", " ", (s or "").lower()).strip()

def _score(query, text):
    q = _norm(query); t = _norm(text)
    if not q or not t: return 0.0
    qset, tset = set(q.split()), set(t.split())
    overlap = len(qset & tset) / max(1, len(qset))
    return max(overlap, SequenceMatcher(None, q, t).ratio() * 0.55)

def answer_query(query: str, dataset: dict | None = None):
    data = dataset or latest_snapshot()
    if not data:
        return {"answer": "No weekly dataset is available yet. Run the intelligence scan first.", "matches": []}
    q = _norm(query)
    vehicles = data.get("vehicles") or []
    sections = data.get("sections") or {}
    if "podium" in q:
        rows = sections.get("Podium Vehicle") or []
        answer = rows[0].get("item") if rows else "No podium vehicle was identified."
        return {"answer": f"Podium vehicle: {answer}", "matches": rows[:3]}
    if "prize" in q and "ride" in q:
        rows = sections.get("Prize Ride") or []
        answer = rows[0].get("item") if rows else "No Prize Ride was identified."
        return {"answer": f"Prize Ride: {answer}", "matches": rows[:3]}
    if "vehicle" in q or "car" in q:
        ranked = sorted(vehicles, key=lambda v: _score(query, " ".join(filter(None, [v.get("name"), v.get("category"), v.get("details")] ))), reverse=True)
        ranked = [v for v in ranked if _score(query, " ".join(filter(None, [v.get("name"), v.get("category"), v.get("details")] ))) > .18][:8]
        if not ranked:
            ranked = vehicles[:8]
        names = ", ".join(v.get("name", "Unknown") for v in ranked[:5]) or "None identified"
        return {"answer": f"Relevant weekly vehicles: {names}.", "matches": ranked}
    corpus = []
    for cat, rows in sections.items():
        for row in rows:
            text = f"{cat} {row.get('item','')} {row.get('details','')}"
            corpus.append((text, {"category": cat, **row}))
    ranked = sorted(corpus, key=lambda pair: _score(query, pair[0]), reverse=True)
    matches = [r for text, r in ranked if _score(query, text) > .18][:8]
    if not matches:
        return {"answer": "I could not find a strong match in the current weekly dataset.", "matches": []}
    top = matches[0]
    answer = f"{top.get('category')}: {top.get('item')}"
    if top.get("details"): answer += f" — {top['details']}"
    return {"answer": answer, "matches": matches}
