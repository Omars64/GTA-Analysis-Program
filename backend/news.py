"""Small, source-linked Rockstar Newswire index."""
from __future__ import annotations

import time
from urllib.parse import urljoin

from network import fetch_context, get_soup
from storage import store

NEWSWIRE = "https://www.rockstargames.com/newswire"


def get_news(refresh=False):
    cached = store.get("rockstar-news", "latest")
    if cached and not refresh and time.time() - cached.get("checked_at", 0) < 30 * 60:
        return cached
    result = {"source_url": NEWSWIRE, "checked_at": time.time(), "items": [], "stale": False}
    try:
        with fetch_context(timeout=12, budget=20):
            soup = get_soup(NEWSWIRE)
        seen = set()
        for link in soup.select("a[href]"):
            url = urljoin(NEWSWIRE, link.get("href", "")).split("?")[0]
            title = link.get_text(" ", strip=True)
            if "rockstargames.com/newswire/" not in url or not title or len(title) < 8 or url in seen:
                continue
            seen.add(url)
            items = {"title": title[:180], "url": url, "source": "Rockstar Newswire"}
            parent = link.find_parent(["article", "li", "div"])
            if parent:
                time_tag = parent.find("time")
                if time_tag:
                    items["date"] = time_tag.get("datetime") or time_tag.get_text(" ", strip=True)
            result["items"].append(items)
            if len(result["items"]) >= 12:
                break
    except Exception:
        if cached:
            result = {**cached, "stale": True}
        else:
            result["stale"] = True
    store.put("rockstar-news", "latest", result)
    return result
