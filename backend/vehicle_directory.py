"""Cached GTA V/Online vehicle directory for the in-app vehicle browser.

The directory stores names, manufacturers and links only. Detailed facts and
images are still loaded on demand through vehicle_profiles.py so the app does
not copy a third-party site's article text into its database.
"""
from __future__ import annotations

import re
import time
from urllib.parse import urljoin

from network import fetch_context, get_soup
from storage import store
from vehicle_intelligence import MANUFACTURERS, _best_catalog_match, _norm, load_catalog
from vehicle_profiles import BASE, BASES

CACHE_KEY = "catalog"
LOOKUP_VERSION = 1
CACHE_TTL = 6 * 60 * 60


def _manufacturer(name: str) -> str:
    words = _norm(name).split()
    if not words:
        return "Other"
    first = words[0]
    known = {value.lower() for value in MANUFACTURERS}
    return first.title() if first in known else (name.split()[0] if name.split() else "Other")


def _seed_items():
    items = []
    for entry in load_catalog():
        name = entry.get("name", "").strip()
        if not name:
            continue
        items.append({
            "id": entry.get("page_slug") or _norm(name).replace(" ", "-"),
            "name": name,
            "manufacturer": entry.get("manufacturer") or _manufacturer(name),
            "vehicle_class": entry.get("vehicle_class"),
            "price": entry.get("price"),
            "image_url": entry.get("image_url"),
            "source_url": urljoin(BASE, entry.get("page_slug", "")),
        })
    return items


def _parse_directory(soup):
    catalog = load_catalog()
    items, seen = [], set()
    for link in soup.select("a[href]"):
        href = urljoin(BASE, link.get("href", "")).split("?")[0].rstrip("/")
        if not href.startswith(BASES):
            continue
        text = link.get("title") or link.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text or "").strip()
        if not text or len(text) > 90 or _norm(text) in {"vehicle", "view", "read more"}:
            continue
        key = _norm(text)
        if key in seen:
            continue
        match, _ = _best_catalog_match(text, catalog)
        items.append({
            "id": href.rsplit("/", 1)[-1],
            "name": match.get("name") if match else text,
            "manufacturer": (match or {}).get("manufacturer") or _manufacturer(text),
            "vehicle_class": (match or {}).get("vehicle_class"),
            "price": (match or {}).get("price"),
            "image_url": (match or {}).get("image_url"),
            "source_url": href,
        })
        seen.add(key)
    return items


def get_directory(refresh=False):
    cached = store.get("vehicle-directory", CACHE_KEY)
    if cached and not refresh and cached.get("version") == LOOKUP_VERSION and time.time() - cached.get("checked_at", 0) < CACHE_TTL:
        return cached
    result = {"version": LOOKUP_VERSION, "checked_at": time.time(), "source_url": BASE, "items": _seed_items(), "stale": False}
    try:
        with fetch_context(timeout=12, budget=28):
            items = _parse_directory(get_soup(BASE))
        if len(items) >= len(result["items"]):
            result["items"] = items
    except Exception:
        if cached and cached.get("items"):
            result = {**cached, "stale": True}
        else:
            result["stale"] = True
    store.put("vehicle-directory", CACHE_KEY, result)
    return result


def search_directory(query="", manufacturer="", refresh=False, limit=1000):
    data = get_directory(refresh=refresh)
    q = _norm(query)
    maker = _norm(manufacturer)
    items = data.get("items", [])
    if maker:
        items = [item for item in items if _norm(item.get("manufacturer", "")) == maker]
    if q:
        items = [item for item in items if q in _norm(item.get("name", "")) or q in _norm(item.get("manufacturer", ""))]
    makers = sorted({item.get("manufacturer") for item in data.get("items", []) if item.get("manufacturer")}, key=str.casefold)
    return {"items": items[:limit], "total": len(items), "manufacturers": makers, "source_url": data.get("source_url", BASE), "stale": bool(data.get("stale")), "checked_at": data.get("checked_at")}
