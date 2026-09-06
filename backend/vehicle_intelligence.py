from __future__ import annotations
import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urljoin
import requests
import threading
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent
CATALOG_FILE = BASE_DIR / "data" / "vehicle_catalog.json"
IMAGE_CACHE_FILE = BASE_DIR / "runtime" / "vehicle_image_cache.json"
_cache_lock = threading.RLock()
VEHICLE_CATEGORIES = {
    "Podium Vehicle", "Prize Ride", "New Vehicle", "Free Vehicle",
    "Luxury Autos", "Simeon's Showroom", "Test Rides"
}
MANUFACTURERS = {
    "albany","annis","benefactor","bf","bollokan","bravado","buckingham","canis","coil","declasse",
    "dewbauchee","dinka","dundreary","emperor","enus","fathom","gallivanter","grotti","hijak","hvy",
    "imponte","invetero","karin","lampadati","maibatsu","mammoth","maxwell","nagasaki","obey","ocelot",
    "overflod","pegassi","pfister","progen","rune","schyster","shitzu","speedophile","truffade","ubermacht",
    "vapid","vulcar","weeny","western","willard","zirconium"
}

def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()

def load_catalog():
    try:
        return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

def _best_catalog_match(name: str, catalog: list[dict]):
    n = _norm(name)
    best, best_score = None, 0.0
    for entry in catalog:
        names = [entry.get("name", ""), *(entry.get("aliases") or [])]
        for candidate in names:
            c = _norm(candidate)
            if not c:
                continue
            score = 1.0 if n == c else SequenceMatcher(None, n, c).ratio()
            if c in n or n in c:
                score = max(score, 0.92)
            if score > best_score:
                best, best_score = entry, score
    return (best, best_score) if best_score >= 0.72 else (None, best_score)

def clean_vehicle_name(item: str) -> str:
    text = re.sub(r"^[•\-–—\s]+", "", item or "").strip()
    text = re.sub(r"\b\d{1,3}%\s*(?:off|discount)?\b", "", text, flags=re.I)
    text = re.sub(r"^(?:up to\s+)?\$[\d,.]+\s*[-–—:]?\s*", "", text, flags=re.I)
    text = re.sub(r"\s+[-–—:]\s+.*$", "", text).strip(" -–—:")
    return text.strip()

def looks_like_vehicle(category: str, item: str, catalog: list[dict]) -> bool:
    if category in VEHICLE_CATEGORIES:
        return True
    candidate = clean_vehicle_name(item)
    first = _norm(candidate).split(" ")[0] if _norm(candidate) else ""
    if first in MANUFACTURERS:
        return True
    match, score = _best_catalog_match(candidate, catalog)
    return bool(match and score >= 0.78)

def collect_article_images(url: str, timeout: int = 25):
    images = []
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 GTAWeeklyCompanion/6.0"}, timeout=timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for img in soup.find_all("img"):
            src = img.get("data-src") or img.get("data-lazy-src") or img.get("src")
            if not src:
                srcset = img.get("srcset") or img.get("data-srcset") or ""
                if srcset:
                    src = srcset.split(",")[-1].strip().split(" ")[0]
            if not src:
                continue
            src = urljoin(url, src)
            if src.startswith("data:"):
                continue
            alt = " ".join([img.get("alt", ""), img.get("title", "")]).strip()
            parent = img.parent.get_text(" ", strip=True)[:500] if img.parent else ""
            images.append({"url": src, "text": f"{alt} {parent}".strip()})
    except Exception:
        pass
    return images



def _slug(text: str) -> str:
    text = _norm(text).replace(" ", "-")
    return re.sub(r"-+", "-", text).strip("-")


def _load_image_cache():
    with _cache_lock:
        try:
            return json.loads(IMAGE_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}


def _save_image_cache(cache):
    with _cache_lock:
        IMAGE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        IMAGE_CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def resolve_gtabase_image(vehicle_name: str, catalog_entry: dict | None = None, timeout: int = 10):
    """Best-effort image fallback from a vehicle detail page.

    This is intentionally cached and only used after article-image matching fails.
    It validates the page title against the requested vehicle before accepting og:image,
    so a guessed slug cannot silently attach an unrelated vehicle image.
    """
    cache = _load_image_cache()
    key = _norm(vehicle_name)
    if key in cache:
        return cache[key] or None
    names = []
    if catalog_entry and catalog_entry.get("page_slug"):
        names.append(catalog_entry["page_slug"])
    cleaned = clean_vehicle_name(vehicle_name)
    parts = cleaned.split()
    names.append(_slug(cleaned))
    if parts and _norm(parts[0]) in MANUFACTURERS and len(parts) > 1:
        names.append(_slug(" ".join(parts[1:])))
    # Keep network impact small and stable.
    candidates = []
    for slug in names:
        if slug and slug not in candidates:
            candidates.append(slug)
    result = None
    for slug in candidates[:3]:
        url = f"https://www.gtabase.com/grand-theft-auto-v/vehicles/{slug}"
        try:
            r = requests.get(url, headers={"User-Agent":"Mozilla/5.0 GTAWeeklyCompanion/6.0"}, timeout=timeout)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            title = soup.title.get_text(" ", strip=True) if soup.title else ""
            target = _norm(cleaned)
            title_norm = _norm(title)
            short_target = _norm(" ".join(parts[1:])) if parts and _norm(parts[0]) in MANUFACTURERS else target
            similarity = max(SequenceMatcher(None, target, title_norm[:max(80,len(target)*3)]).ratio(), 1.0 if short_target and short_target in title_norm else 0.0)
            if similarity < 0.55:
                continue
            meta = soup.find("meta", attrs={"property":"og:image"}) or soup.find("meta", attrs={"name":"twitter:image"})
            image = meta.get("content") if meta else None
            if image:
                result = urljoin(url, image)
                break
        except Exception:
            continue
    cache[key] = result
    try:
        _save_image_cache(cache)
    except Exception:
        pass
    return result

def resolve_image(vehicle_name: str, source_images: list[dict], catalog_entry: dict | None = None):
    if catalog_entry and catalog_entry.get("image_url"):
        return catalog_entry["image_url"], "catalog"
    target = _norm(vehicle_name)
    target_tokens = set(target.split())
    best_url, best_score = None, 0.0
    for image in source_images:
        hay = _norm(image.get("text", ""))
        if not hay:
            continue
        overlap = len(target_tokens & set(hay.split())) / max(1, len(target_tokens))
        seq = SequenceMatcher(None, target, hay[: max(len(target) * 3, 60)]).ratio()
        score = overlap * 0.8 + seq * 0.2
        if target and target in hay:
            score = max(score, 0.95)
        if score > best_score:
            best_score, best_url = score, image.get("url")
    if best_url and best_score >= 0.48:
        return best_url, "article"
    fallback = resolve_gtabase_image(vehicle_name, catalog_entry)
    return (fallback, "vehicle-database") if fallback else (None, "placeholder")

def enrich_vehicles(items: list[dict], source_images_by_url: dict[str, list[dict]]):
    catalog = load_catalog()
    vehicles = []
    seen = set()
    for row in items:
        category = row.get("category", "")
        item = row.get("item", "")
        if not looks_like_vehicle(category, item, catalog):
            continue
        name = clean_vehicle_name(item)
        if not name or len(name) < 2:
            continue
        key = _norm(name)
        if key in seen:
            continue
        seen.add(key)
        match, match_score = _best_catalog_match(name, catalog)
        source_urls = row.get("source_urls") or ([row.get("source_url")] if row.get("source_url") else [])
        source_images = []
        for url in source_urls:
            source_images.extend(source_images_by_url.get(url, []))
        image_url, image_source = resolve_image(name, source_images, match)
        vehicle = {
            "name": match.get("name") if match else name,
            "manufacturer": match.get("manufacturer") if match else (name.split()[0] if name.split() and _norm(name.split()[0]) in MANUFACTURERS else None),
            "vehicle_class": match.get("vehicle_class") if match else None,
            "price": match.get("price") if match else None,
            "website": match.get("website") if match else None,
            "image_url": image_url,
            "image_source": image_source,
            "category": category,
            "details": row.get("details", ""),
            "confidence": row.get("confidence", 0.6),
            "verified": row.get("verified", False),
            "source_count": row.get("source_count", 1),
            "source_urls": source_urls,
            "catalog_match": round(match_score, 3) if match else None,
        }
        vehicles.append(vehicle)
    return vehicles
