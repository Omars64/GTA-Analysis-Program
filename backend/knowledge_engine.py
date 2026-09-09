from __future__ import annotations
import re
from difflib import SequenceMatcher, get_close_matches
from history_store import latest_snapshot

def _norm(s):
    return re.sub(r"[^a-z0-9%$]+", " ", (s or "").lower()).strip()

def _score(query, text):
    q = _norm(query); t = _norm(text)
    if not q or not t: return 0.0
    stop = {'what', 'is', 'the', 'this', 'week', 'show', 'me', 'a', 'an', 'are', 'on', 'in', 'for', 'please'}
    qset, tset = set(q.split()) - stop, set(t.split())
    overlap = len(qset & tset) / max(1, len(qset))
    fuzzy = sum(max((SequenceMatcher(None, word, candidate).ratio() for candidate in tset), default=0) >= .8 for word in qset) / max(1, len(qset))
    return max(overlap, fuzzy * .85)


def correct_query(query, data):
    vocabulary = set(_norm(' '.join(f"{category} " + ' '.join(f"{r.get('item', '')} {r.get('details', '')}" for r in rows) for category, rows in (data.get('sections') or {}).items())).split())
    vocabulary.update({'podium', 'vehicle', 'vehicles', 'car', 'cars', 'prize', 'ride', 'discounts', 'bonuses'})
    common = {'what', 'which', 'is', 'the', 'this', 'week', 'show', 'me', 'a', 'an', 'are', 'on', 'in', 'for', 'please', 'how', 'much'}
    words = _norm(query).split()
    corrected = []
    for word in words:
        matches = get_close_matches(word, sorted(vocabulary), n=1, cutoff=.76) if len(word) >= 4 and word not in vocabulary | common else []
        corrected.append(matches[0] if matches else word)
    return ' '.join(corrected)

def answer_query(query: str, dataset: dict | None = None):
    data = dataset or latest_snapshot()
    if not data:
        return {"answer": "No weekly dataset is available yet. Run the intelligence scan first.", "matches": []}
    corrected = correct_query(query, data)
    result = _answer(corrected, data)
    if corrected != _norm(query):
        result['corrected_query'] = corrected
    return result


def _answer(query, data):
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
    if set(q.split()) & {'vehicle', 'vehicles', 'car', 'cars'}:
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
