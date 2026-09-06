# -*- coding: utf-8 -*-
from __future__ import annotations
import calendar
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from dateutil.tz import gettz
from dateutil.parser import parse as dateparse

# =========================
# CONFIG
# =========================
OUTDIR = os.getenv("GTA_OUTPUT_DIR", os.path.join(os.path.dirname(__file__), "runtime", "exports"))
MANUAL_URL = ""  # leave blank to auto-discover; or paste a weekly article URL here

# NEW: Email toggle + optional sleep before sending
SEND_EMAIL = os.getenv("GTA_SEND_EMAIL", "false").strip().lower() in ("1", "true", "yes", "y", "on")
SLEEP_BEFORE_EMAIL_SECONDS = int(os.getenv("GTA_EMAIL_SLEEP_SECS", "30"))  # was 30s fixed

KUWAIT_TZ = gettz("Asia/Kuwait") or datetime.now().astimezone().tzinfo
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; GTAWeeklyBot/5.0; +https://local-run)",
    "Accept-Language": "en-US,en;q=0.9",
}
REQUEST_TIMEOUT = 30

# Nitter mirrors for Tez2 tweet text (used only to detect week date range)
NITTER_MIRRORS = [
    "https://nitter.net",
    "https://nitter.poast.org",
    "https://nitter.lucabased.xyz",
    "https://ntrqq.com",
    "https://nitter.moomoo.me",
]

# =========================
# EMAIL IMPORT
# =========================
try:
    from sendMail import send_email_with_attachment
except ImportError:
    from pathlib import Path

    sys.path.append(str(Path(__file__).parent))
    from sendMail import send_email_with_attachment

# =========================
# CATEGORIZATION / FILTERS
# =========================
SECTION_ALIASES = {
    # Vehicles
    "podium vehicle": "Podium Vehicle",
    "podium car": "Podium Vehicle",
    "podium": "Podium Vehicle",
    "prize ride": "Prize Ride",
    "prize ride challenge": "Prize Ride",
    "ls car meet prize ride": "Prize Ride",
    "new vehicle": "New Vehicle",
    "free vehicle": "Free Vehicle",

    # Showrooms
    "simeon": "Simeon's Showroom",
    "premium deluxe motorsport": "Simeon's Showroom",
    "simeon's premium deluxe motorsport": "Simeon's Showroom",
    "luxury autos": "Luxury Autos",
    "luxury autos showroom": "Luxury Autos",
    "dealership": "Dealership",
    "showrooms": "Dealership",

    # Trials / races
    "time trial": "Time Trials",
    "time trials": "Time Trials",
    "rc bandito time trial": "Time Trials",
    "hsw time trial": "Time Trials",
    "premium race": "Time Trials",

    # Bonuses / discounts
    "bonuses": "Bonuses",
    "bonus rewards": "Bonuses",
    "double money": "Bonuses",
    "triple money": "Bonuses",
    "2x": "Bonuses",
    "3x": "Bonuses",
    "discounts": "Discounts",
    "discount": "Discounts",
    "sale": "Discounts",
    "sales": "Discounts",

    # Regular blocks
    "weekly challenge": "Weekly Challenge",
    "community series": "Community Series",
    "test ride": "Test Rides",
    "test rides": "Test Rides",
    "premium test ride": "Test Rides",
    "ls car meet test ride": "Test Rides",
    "gun van": "Gun Van",
    "new content": "New Content",
}

_KEYMAP = [
    (r"\bpodium\b", "Podium Vehicle"),
    (r"\bprize\s*ride\b", "Prize Ride"),
    (r"simeon|premium\s+deluxe", "Simeon's Showroom"),
    (r"luxury\s*autos", "Luxury Autos"),
    (r"\b(test\s*ride|test\s*track|premium\s*test\s*ride)\b", "Test Rides"),
    (r"\b(2x|3x|double|triple)\b", "Bonuses"),
    (r"\b(time\s*trial|hsw|rc\s*bandito|premium\s*race)\b", "Time Trials"),
    (r"\bweekly\s*challenge\b", "Weekly Challenge"),
    (r"\bcommunity\s*series\b", "Community Series"),
    (r"\bgun\s*van\b", "Gun Van"),
    (r"\bdiscount|% off|sale|price\b", "Discounts"),
    (r"\bfree\s+vehicle\b", "Free Vehicle"),
]

LISTING_KEYWORDS = (
    "this week in gta online",
    "weekly update",
    "weekly event",
    "this week’s",
    "this week in gta",
    "gta online weekly",
)

MONTHS = ("January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec")

# Noisy promos to drop entirely
BLOCKLIST_PHRASES = [
    "shark card", "shark cards", "cash card", "cash cards",
    "gta+", "gta plus", "prime gaming", "amazon prime", "twitch prime",
    "subscription", "newsletter", "social club",
    # NEW: share/footer junk
    "share this", "share on", "facebook.com", "twitter.com", "x.com", "reddit.com",
    "pinterest", "whatsapp", "telegram", "linkedin.com"
]
DROP_SECTION_NAMES = {"more", "free abilities", "share this"}  # remove “Free abilities” and generic “More” blocks

# Visual priority (order in PDF)
PRIORITY_ORDER = [
    "New Content", "New Vehicle", "Free Vehicle",
    "Podium Vehicle", "Prize Ride",
    "Luxury Autos", "Simeon's Showroom", "Dealership", "Test Rides",
    "Bonuses", "Discounts",
    "Time Trials", "Weekly Challenge", "Community Series",
    "Gun Van",
]


# =========================
# UTILITIES
# =========================
def now_kw() -> datetime:
    return datetime.now(tz=KUWAIT_TZ)


def http_get_soup(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def _text(soup) -> str:
    return " ".join(soup.get_text(" ").split())


# Week helpers
def gta_week_window_from_date(base_dt: datetime) -> Tuple[datetime, datetime]:
    ref = base_dt.astimezone(KUWAIT_TZ)
    weekday = ref.weekday()  # Thu = 3
    days_since_thu = (weekday - 3) % 7
    start = (ref - timedelta(days=days_since_thu)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = (start + timedelta(days=6)).replace(hour=23, minute=59, second=59, microsecond=0)
    return start, end


def first_thursday_on_or_after(dt_kw: datetime) -> datetime:
    d = dt_kw.astimezone(KUWAIT_TZ)
    while d.weekday() != 3:
        d += timedelta(days=1)
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def gta_week_from_publish_snap(pub_kw: datetime) -> tuple[datetime, datetime]:
    start = first_thursday_on_or_after(pub_kw)
    end = (start + timedelta(days=6)).replace(hour=23, minute=59, second=59, microsecond=0)
    return start, end


# =========================
# DATE/RANGE EXTRACTION (article + Tez2)
# =========================
def extract_week_range_from_text(soup) -> Optional[tuple[datetime, datetime]]:
    txt = _text(soup)

    # "Month d–d, YYYY"
    m = re.search(rf"\b{MONTHS}\s+(\d{{1,2}})\s*[–\-to]+\s*(\d{{1,2}})\s*,\s*(\d{{4}})\b", txt, re.IGNORECASE)
    if m:
        month, d1, d2, year = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
        mnum = (list(calendar.month_name).index(month.capitalize())
                if len(month) > 3 else list(calendar.month_abbr).index(month.capitalize()))
        start = datetime(year, mnum, d1, tzinfo=KUWAIT_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
        end = datetime(year, mnum, d2, tzinfo=KUWAIT_TZ).replace(hour=23, minute=59, second=59, microsecond=0)
        return start, end

    # "d–d Month YYYY"
    m = re.search(rf"\b(\d{{1,2}})\s*[–\-to]+\s*(\d{{1,2}})\s+{MONTHS}\s+(\d{{4}})\b", txt, re.IGNORECASE)
    if m:
        d1, d2, month, year = int(m.group(1)), int(m.group(2)), m.group(3), int(m.group(4))
        mnum = (list(calendar.month_name).index(month.capitalize())
                if len(month) > 3 else list(calendar.month_abbr).index(month.capitalize()))
        start = datetime(year, mnum, d1, tzinfo=KUWAIT_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
        end = datetime(year, mnum, d2, tzinfo=KUWAIT_TZ).replace(hour=23, minute=59, second=59, microsecond=0)
        return start, end

    # "Mon d - Mon d, YYYY"
    m = re.search(rf"\b({MONTHS})\s+(\d{{1,2}})\s*[–\-to]+\s*({MONTHS})\s+(\d{{1,2}})\s*,\s*(\d{{4}})\b", txt,
                  re.IGNORECASE)
    if m:
        m1, d1, m2, d2, year = m.group(1), int(m.group(2)), m.group(3), int(m.group(4)), int(m.group(5))

        def mon2num(mon):
            return (list(calendar.month_name).index(mon.capitalize())
                    if len(mon) > 3 else list(calendar.month_abbr).index(mon.capitalize()))

        start = datetime(year, mon2num(m1), d1, tzinfo=KUWAIT_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
        end = datetime(year, mon2num(m2), d2, tzinfo=KUWAIT_TZ).replace(hour=23, minute=59, second=59, microsecond=0)
        return start, end

    return None


def extract_article_publish_dt_kuwait(url: str) -> Optional[datetime]:
    soup = http_get_soup(url)
    for (attr, key) in (("property", "article:published_time"),
                        ("name", "pubdate"), ("name", "publishdate"), ("name", "date"),
                        ("name", "dc.date"), ("name", "dc.date.issued")):
        m = soup.find("meta", attrs={attr: key})
        if m and m.get("content"):
            try:
                dt = dateparse(m["content"])
                return dt.astimezone(KUWAIT_TZ)
            except Exception:
                continue
    for t in soup.find_all("time"):
        val = t.get("datetime") or t.get("content")
        if val:
            try:
                dt = dateparse(val)
                return dt.astimezone(KUWAIT_TZ)
            except Exception:
                pass
    header = soup.find("header") or soup.find(class_=re.compile("article-header|post-header|entry-header", re.I))
    if header:
        m = re.search(rf"({MONTHS})\s+\d{{1,2}},\s+\d{{4}}", header.get_text(" "), re.IGNORECASE)
        if m:
            try:
                dt = dateparse(m.group(0))
                return dt.replace(tzinfo=gettz("UTC")).astimezone(KUWAIT_TZ)
            except Exception:
                pass
    return None


def find_week_range_from_tez2() -> Optional[tuple[datetime, datetime]]:
    """Read @TezFunz2 via Nitter mirrors; extract a date range for 'this week' GTA Online post."""
    patterns = [
        (re.compile(rf"\b({MONTHS})\s+(\d{{1,2}})\s*[–\-to]+\s*(\d{{1,2}})\s*,\s*(\d{{4}})\b", re.I), "mon_d_to_d"),
        (re.compile(rf"\b(\d{{1,2}})\s*[–\-to]+\s*(\d{{1,2}})\s+({MONTHS})\s+(\d{{4}})\b", re.I), "d_to_d_mon"),
        (re.compile(rf"\b({MONTHS})\s+(\d{{1,2}})\s*[–\-to]+\s*({MONTHS})\s+(\d{{1,2}})\s*,\s*(\d{{4}})\b", re.I),
         "mon_d_to_mon_d"),
    ]
    must_have = ["this week", "gta online"]
    for base in NITTER_MIRRORS:
        url = f"{base}/TezFunz2"
        try:
            soup = http_get_soup(url)
        except Exception:
            continue
        containers = soup.select(".timeline-item .tweet-content, .timeline-item .tweet-body, .timeline-item")
        if not containers:
            containers = soup.select(".tweet-content, .tweet-body")
        for c in containers[:12]:
            text_low = _text(c).lower()
            if not all(t in text_low for t in must_have):
                continue
            raw = _text(c)
            for pat, kind in patterns:
                m = pat.search(raw)
                if not m:
                    continue
                if kind == "mon_d_to_d":
                    month, d1, d2, year = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
                    mnum = (list(calendar.month_name).index(month.capitalize())
                            if len(month) > 3 else list(calendar.month_abbr).index(month.capitalize()))
                    return (
                        datetime(year, mnum, d1, tzinfo=KUWAIT_TZ).replace(hour=0, minute=0, second=0, microsecond=0),
                        datetime(year, mnum, d2, tzinfo=KUWAIT_TZ).replace(hour=23, minute=59, second=59,
                                                                           microsecond=0),
                    )
                if kind == "d_to_d_mon":
                    d1, d2, month, year = int(m.group(1)), int(m.group(2)), m.group(3), int(m.group(4))
                    mnum = (list(calendar.month_name).index(month.capitalize())
                            if len(month) > 3 else list(calendar.month_abbr).index(month.capitalize()))
                    return (
                        datetime(year, mnum, d1, tzinfo=KUWAIT_TZ).replace(hour=0, minute=0, second=0, microsecond=0),
                        datetime(year, mnum, d2, tzinfo=KUWAIT_TZ).replace(hour=23, minute=59, second=59,
                                                                           microsecond=0),
                    )
                if kind == "mon_d_to_mon_d":
                    m1, d1, m2, d2, year = m.group(1), int(m.group(2)), m.group(3), int(m.group(4)), int(m.group(5))

                    def mon2num(mon):
                        return (list(calendar.month_name).index(mon.capitalize())
                                if len(mon) > 3 else list(calendar.month_abbr).index(mon.capitalize()))

                    return (
                        datetime(year, mon2num(m1), d1, tzinfo=KUWAIT_TZ).replace(hour=0, minute=0, second=0,
                                                                                  microsecond=0),
                        datetime(year, mon2num(m2), d2, tzinfo=KUWAIT_TZ).replace(hour=23, minute=59, second=59,
                                                                                  microsecond=0),
                    )
    return None


# =========================
# DISCOVERY (PowerUpGaming → GTABase → RockstarINTEL)
# =========================
def looks_weekly_page(soup: BeautifulSoup, title: str) -> bool:
    t = (title or "").lower()
    kw_hit = any(k in t for k in LISTING_KEYWORDS)
    content = soup.find("article") or soup
    text = (content.get_text(" ") or "").lower()
    section_hit = any(s in text for s in [
        "podium vehicle", "prize ride", "luxury autos", "premium deluxe motorsport",
        "time trial", "weekly challenge", "bonuses", "discounts"
    ])
    return kw_hit or section_hit


def find_latest_powerupgaming_weekly_page() -> tuple[str, str]:
    import urllib.parse
    candidates = []
    listing_urls = [
        "https://powerupgaming.co.uk/category/guides/",
        "https://powerupgaming.co.uk/?s=GTA+Online+Weekly+Update",
    ]
    for url in listing_urls:
        try:
            soup = http_get_soup(url)
        except Exception:
            continue
        for a in soup.select("article h2 a, article h1 a, .entry-title a, h2.entry-title a"):
            title = (a.get_text(strip=True) or "")
            href = a.get("href") or ""
            if not href:
                continue
            if not href.startswith("http"):
                href = urllib.parse.urljoin(url, href)
            if "gta online weekly update" in title.lower():
                candidates.append((href, title))
    for href, title in candidates[:12]:
        try:
            page = http_get_soup(href)
            if looks_weekly_page(page, title):
                return href, title or "Weekly Article"
        except Exception:
            continue
    raise RuntimeError("PowerUpGaming: could not locate a weekly article.")


def find_latest_gtabase_weekly_page() -> Tuple[str, str]:
    import urllib.parse
    listing_urls = [
        "https://www.gtabase.com/grand-theft-auto-v/news/",
        "https://www.gtabase.com/news/",
        "https://www.gtabase.com/articles/grand-theft-auto-v/news/",
    ]
    candidates = []
    for url in listing_urls:
        try:
            soup = http_get_soup(url)
            for a in soup.select("article h1 a, article h2 a, article h3 a, .blog-item h2 a, .blog-items h2 a"):
                title = (a.get_text(strip=True) or "")
                href = a.get("href") or ""
                if not href:
                    continue
                if not href.startswith("http"):
                    href = urllib.parse.urljoin(url, href)
                if href not in [x[0] for x in candidates]:
                    candidates.append((href, title))
        except Exception as e:
            logging.warning("GTABase listing fetch failed %s: %s", url, e)
    for href, title in candidates[:12]:
        try:
            page = http_get_soup(href)
            if looks_weekly_page(page, title):
                return href, title or "Weekly Article"
        except Exception:
            continue
    raise RuntimeError("GTABase: could not locate a weekly article.")


def find_latest_rockstarintel_weekly_page() -> Tuple[str, str]:
    import urllib.parse
    listing_urls = [
        "https://rockstarintel.com/category/news",
        "https://rockstarintel.com/category/grand-theft-auto-v",
        "https://rockstarintel.com/category/grand-theft-auto-online-news",
    ]
    candidates = []
    for url in listing_urls:
        try:
            soup = http_get_soup(url)
            for a in soup.select("article h2 a, article h3 a, .post-title a, .entry-title a, h2.entry-title a"):
                title = (a.get_text(strip=True) or "")
                href = a.get("href") or ""
                if not href:
                    continue
                if not href.startswith("http"):
                    href = urllib.parse.urljoin(url, href)
                if href not in [x[0] for x in candidates]:
                    candidates.append((href, title))
        except Exception as e:
            logging.warning("RockstarINTEL listing fetch failed %s: %s", url, e)
    for href, title in candidates[:12]:
        try:
            page = http_get_soup(href)
            if looks_weekly_page(page, title):
                return href, title or "Weekly Article"
        except Exception:
            continue
    raise RuntimeError("RockstarINTEL: could not locate a weekly article.")


# =========================
# PARSING (GENERIC)
# =========================
def normalize_section_name(raw: str) -> Optional[str]:
    s = (raw or "").strip()
    if not s: return None
    s_clean = re.sub(r"[:：\-–—]+$", "", s).strip()
    s_lower = s_clean.lower()
    for key, val in SECTION_ALIASES.items():
        if key in s_lower:
            return val
    if 3 <= len(s_clean) <= 80:
        return s_clean
    return None


def split_item_details(text: str) -> Tuple[str, str]:
    t = text.strip()
    m = re.search(r"^(.*?)\s*\(([^()]{2,})\)\s*$", t)
    if m:
        left = m.group(1).strip(" -–—");
        right = m.group(2).strip()
        return (left or t, right)
    m = re.search(r"^(\b[23]x\b.*? on )(.+)$", t, flags=re.IGNORECASE)
    if m:
        details = m.group(1).strip();
        item = m.group(2).strip(" .")
        return (item, details)
    if any(k in t.lower() for k in ["2x", "3x", "double", "triple"]):
        m = re.search(r"^(.*?)(?:\s+on\s+)(.+)$", t, flags=re.IGNORECASE)
        if m:
            left = m.group(1).strip(" .");
            right = m.group(2).strip(" .")
            return (right or t, left or "")
    m = re.search(
        r"^(podium vehicle|prize ride|luxury autos|simeon.*?|premium deluxe motorsport|time trial|hsw time trial|rc bandito time trial|weekly challenge)\s*:\s*(.+)$",
        t, flags=re.IGNORECASE)
    if m: return (m.group(2).strip(), m.group(1).strip())
    return (t, "")


def recategorize(category: str, item: str, details: str) -> str:
    cat_clean = (category or "").strip()
    cat_lower = cat_clean.lower()
    txt = " ".join(filter(None, [category, item, details])).lower()
    if cat_lower in {"more", "misc", "other", "others"} or cat_clean not in set(SECTION_ALIASES.values()):
        for pattern, target in _KEYMAP:
            if re.search(pattern, txt, flags=re.IGNORECASE):
                return target
    return cat_clean or "Misc"


def _clean_candidate_text(value: str) -> str:
    text = " ".join((value or "").split()).strip(" •\t\r\n")
    # Ignore obvious UI/navigation fragments and pathological container text.
    if len(text) < 3 or len(text) > 700:
        return ""
    return text


def parse_weekly_soup(soup: BeautifulSoup, url: str) -> List[Dict[str, str]]:
    """Extract normalized weekly rows from an already-fetched article.

    The extractor intentionally uses several structural signals instead of a
    site-specific CSS selector: semantic article roots, heading-bounded blocks,
    list items, leaf paragraphs/divs, and compact tables. This gives each source
    adapter a common fallback when site markup changes.
    """
    content_root = (
        soup.find("article")
        or soup.find("main")
        or soup.find(id=re.compile(r"(content|article|entry|main)", re.I))
        or soup.find(class_=re.compile(r"(content|article|entry|post|single-post)", re.I))
        or soup
    )

    sections: List[Tuple[str, List[str]]] = []
    headings = content_root.find_all(["h1", "h2", "h3", "h4", "h5"])

    for heading in headings:
        header_title = _clean_candidate_text(heading.get_text(" ", strip=True))
        norm_cat = normalize_section_name(header_title)
        if not norm_cat:
            continue

        items: List[str] = []
        # Walk document order until the next heading. Prefer atomic text nodes
        # so nested divs do not duplicate the same entire section repeatedly.
        for node in heading.find_all_next():
            if node is heading:
                continue
            if node.name in ["h1", "h2", "h3", "h4", "h5"]:
                break
            if node.name == "li":
                text = _clean_candidate_text(node.get_text(" ", strip=True))
                if text:
                    items.append(text)
            elif node.name in ["p", "div"]:
                # Keep only leaf-ish containers; lists/tables are handled below.
                if node.find(["p", "div", "li", "table"], recursive=False):
                    continue
                text = _clean_candidate_text(node.get_text(" ", strip=True))
                if text:
                    items.append(text)
            elif node.name == "tr":
                cells = [_clean_candidate_text(c.get_text(" ", strip=True)) for c in node.find_all(["th", "td"], recursive=False)]
                cells = [c for c in cells if c]
                if 1 <= len(cells) <= 5:
                    items.append(" — ".join(cells))

        if items:
            # Stable per-section dedupe while preserving article order.
            seen_items, unique_items = set(), []
            for item in items:
                key = item.lower()
                if key not in seen_items:
                    seen_items.add(key)
                    unique_items.append(item)
            sections.append((norm_cat, unique_items))

    # Fallback for pages with useful lists but weak/missing headings.
    if not sections:
        for ul in content_root.find_all(["ul", "ol"]):
            h = ul.find_previous(["h1", "h2", "h3", "h4", "h5"])
            norm_cat = normalize_section_name(h.get_text(" ", strip=True)) if h else "Misc"
            items = []
            for li in ul.find_all("li", recursive=False):
                text = _clean_candidate_text(li.get_text(" ", strip=True))
                if text:
                    items.append(text)
            if items:
                sections.append((norm_cat or "Misc", items))

    rows: List[Dict[str, str]] = []
    for cat, items in sections:
        for raw in items:
            item, details = split_item_details(raw)
            rows.append({"category": cat, "item": item, "details": details, "source_url": url})

    for row in rows:
        row["category"] = recategorize(row["category"], row["item"], row["details"])

    def blocked(value: str) -> bool:
        value = (value or "").lower()
        return any(phrase in value for phrase in BLOCKLIST_PHRASES)

    cleaned = []
    for row in rows:
        cat = (row.get("category") or "").strip()
        if cat.lower() in DROP_SECTION_NAMES:
            continue
        if blocked(cat) or blocked(row.get("item", "")) or blocked(row.get("details", "")):
            continue
        cleaned.append(row)

    seen, unique = set(), []
    for row in cleaned:
        key = (
            row["category"].lower(),
            row["item"].lower(),
            (row["details"] or "").lower(),
            row["source_url"],
        )
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


def parse_weekly_generic(url: str) -> List[Dict[str, str]]:
    return parse_weekly_soup(http_get_soup(url), url)


# =========================
# PDF OUTPUT (ReportLab preferred; fallback to FPDF)
# =========================
def pdf_path_for(week_start: datetime, week_end: datetime) -> str:
    return os.path.join(OUTDIR, f"GTA_Weekly_Update_{week_start.date()}_to_{week_end.date()}.pdf")


def write_pdf(rows: List[Dict[str, str]], week_start: datetime, week_end: datetime) -> str:
    os.makedirs(OUTDIR, exist_ok=True)

    # group rows by category & sort
    by_cat: Dict[str, List[Dict[str, str]]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)

    def cat_key(c):
        return (PRIORITY_ORDER.index(c) if c in PRIORITY_ORDER else 999, c.lower())

    cats = sorted(by_cat.keys(), key=cat_key)

    out_pdf = pdf_path_for(week_start, week_end)
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
        from reportlab.lib.units import cm

        doc = SimpleDocTemplate(out_pdf, pagesize=A4,
                                leftMargin=2 * cm, rightMargin=2 * cm,
                                topMargin=1.8 * cm, bottomMargin=1.6 * cm)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("TitleBold", parent=styles["Title"],
                                     alignment=1, textColor=colors.HexColor("#0f172a"))
        subtitle_style = ParagraphStyle("Sub", parent=styles["Heading3"],
                                        alignment=1, textColor=colors.HexColor("#1e293b"))
        header_style = ParagraphStyle("Header", parent=styles["Heading2"],
                                      backColor=colors.HexColor("#e2e8f0"),
                                      textColor=colors.HexColor("#0a2a66"),
                                      spaceBefore=10, spaceAfter=6,
                                      leftIndent=0, rightIndent=0,
                                      borderPadding=(6, 6, 6, 6))
        item_style = ParagraphStyle("Item", parent=styles["BodyText"],
                                    fontSize=11, leading=15, spaceAfter=2)

        story = []
        story.append(Paragraph("GTA Online — Weekly Update", title_style))
        story.append(Paragraph(f"{week_start.date()} → {week_end.date()}", subtitle_style))
        story.append(Spacer(1, 10))
        story.append(Paragraph("What’s active this week (by section):", styles["BodyText"]))
        story.append(Spacer(1, 4))

        for cat in cats:
            story.append(Paragraph(cat, header_style))
            bullets = []
            for r in by_cat[cat]:
                item = (r.get("item") or "").strip()
                details = (r.get("details") or "").strip()
                txt = f"{item}" if item else "(No item)"
                if details:
                    txt += f" — <font color='#374151'><i>{details}</i></font>"
                bullets.append(Paragraph(txt, item_style))

            lf = ListFlowable([ListItem(b, leftIndent=12) for b in bullets],
                              bulletType="bullet", start="•")
            story.append(lf)
            story.append(Spacer(1, 6))

        doc.build(story)
        return out_pdf

    except Exception as e:
        try:
            from fpdf import FPDF
            pdf = FPDF(format="A4")
            pdf.set_auto_page_break(auto=True, margin=15)
            pdf.add_page()

            pdf.set_font("Helvetica", "B", 16)
            pdf.cell(0, 10, "GTA Online — Weekly Update", ln=True, align="C")
            pdf.set_font("Helvetica", "", 12)
            pdf.cell(0, 8, f"{week_start.date()} \u2192 {week_end.date()}", ln=True, align="C")
            pdf.ln(6)

            pdf.set_font("Helvetica", "", 11)
            pdf.multi_cell(0, 6, "What’s active this week (by section):")
            pdf.ln(2)

            for cat in cats:
                pdf.set_font("Helvetica", "B", 13)
                x = pdf.l_margin;
                y = pdf.get_y();
                w = pdf.w - pdf.l_margin - pdf.r_margin;
                h = 8
                pdf.set_fill_color(226, 232, 240)
                pdf.rect(x, y, w, h, "F")
                pdf.set_xy(x + 2, y + 1.5)
                pdf.cell(0, 5, cat, ln=1)
                pdf.set_y(y + h + 1)

                pdf.set_font("Helvetica", "", 11)
                for r in by_cat[cat]:
                    item = (r.get("item") or "").strip()
                    details = (r.get("details") or "").strip()
                    line = f"• {item}" if item else "• (No item)"
                    if details:
                        line += f" — {details}"
                    pdf.multi_cell(0, 6, line)
                pdf.ln(2)

            pdf.output(out_pdf)
            return out_pdf
        except Exception as e2:
            raise RuntimeError(f"PDF generation failed: {e} | {e2}")


# =========================
# MAIN
# =========================

def run_weekly_scrape(
    manual_url: Optional[str] = None,
    send_email: Optional[bool] = None,
    email_config: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    """Programmatic entry point used by the Flask API.

    Parameters
    ----------
    manual_url:
        Explicit article URL to parse. If omitted, the scraper will auto-discover
        the latest weekly article from the configured sources.
    send_email:
        If True, attempt to send an email using the provided ``email_config``.
        If False, skip email. If None, fall back to the global SEND_EMAIL flag.
    email_config:
        Optional dict with SMTP / identity settings, expected keys:
            - smtp_server (str)
            - smtp_port (int)
            - username (str)
            - password (str)
            - from_addr (str)
            - to_addrs (list[str])
            - use_tls (bool)
    """
    log_messages: List[str] = []

    def _log(level: str, msg: str, *args) -> None:
        text = msg % args if args else msg
        log_messages.append(f"[{level}] {text}")
        level_lower = level.lower()
        logger = getattr(logging, level_lower, logging.info)
        logger(text)

    _log("INFO", "Starting GTA Online weekly scrape run.")

    # 1) Pick URL(s)
    urls_to_try: List[Tuple[str, str]] = []
    if manual_url and manual_url.strip():
        urls_to_try.append((manual_url.strip(), "Manual"))
        _log("INFO", "Using manual URL supplied via API: %s", manual_url.strip())
    elif MANUAL_URL.strip():
        urls_to_try.append((MANUAL_URL.strip(), "Manual"))
        _log("INFO", "Using MANUAL_URL override: %s", MANUAL_URL.strip())
    else:
        try:
            p_url, p_title = find_latest_powerupgaming_weekly_page()
            urls_to_try.append((p_url, f"PowerUpGaming: {p_title}"))
            _log("INFO", "Found PowerUpGaming weekly article: %s", p_url)
        except Exception as e:
            _log("WARNING", "PowerUpGaming discovery failed: %s", e)

        try:
            g_url, g_title = find_latest_gtabase_weekly_page()
            urls_to_try.append((g_url, f"GTABase: {g_title}"))
            _log("INFO", "Found GTABase weekly article: %s", g_url)
        except Exception as e:
            _log("WARNING", "GTABase discovery failed: %s", e)

        try:
            r_url, r_title = find_latest_rockstarintel_weekly_page()
            urls_to_try.append((r_url, f"RockstarINTEL: {r_title}"))
            _log("INFO", "Found RockstarINTEL weekly article: %s", r_url)
        except Exception as e:
            _log("WARNING", "RockstarINTEL discovery failed: %s", e)

    if not urls_to_try:
        _log("ERROR", "No candidate weekly URLs found.")
        raise RuntimeError("No candidate weekly URLs found.")

    # 2) Determine week range using primary article
    chosen_url, chosen_label = urls_to_try[0]
    _log("INFO", "Primary weekly URL: %s", chosen_url)
    soup = http_get_soup(chosen_url)

    week_start: datetime
    week_end: datetime

    try:
        rng = extract_week_range_from_text(soup)
    except Exception as e:
        _log("WARNING", "extract_week_range_from_text failed: %s", e)
        rng = None

    if rng:
        week_start, week_end = rng
        _log("INFO", "Week from article text: %s -> %s", week_start.date(), week_end.date())
    else:
        tez = None
        try:
            tez = find_week_range_from_tez2()
        except Exception as e:
            _log("WARNING", "find_week_range_from_tez2 failed: %s", e)

        if tez:
            week_start, week_end = tez
            _log("INFO", "Week from Tez2: %s -> %s", week_start.date(), week_end.date())
        else:
            pub_dt_kw = extract_article_publish_dt_kuwait(chosen_url)
            if pub_dt_kw:
                week_start, week_end = gta_week_from_publish_snap(pub_dt_kw)
                _log(
                    "INFO",
                    "Week from publish date (snapped Thu→Wed): %s -> %s",
                    week_start.date(),
                    week_end.date(),
                )
            else:
                week_start, week_end = gta_week_window_from_date(now_kw())
                _log(
                    "WARNING",
                    "Using current week window (Thu→Wed) from now(): %s -> %s",
                    week_start.date(),
                    week_end.date(),
                )

    # 3) Parse primary
    try:
        rows_primary = parse_weekly_generic(chosen_url)
        _log("INFO", "Parsed %d rows from primary.", len(rows_primary))
    except Exception as e:
        _log("ERROR", "Primary parse failed: %s", e)
        rows_primary = []

    rows_merged = list(rows_primary)

    # 4) If backup exists & same week, merge
    if len(urls_to_try) > 1:
        backup_url, backup_label = urls_to_try[1]
        _log("INFO", "Attempting backup merge from: %s", backup_url)

        try:
            soup_b = http_get_soup(backup_url)
            rng_b = extract_week_range_from_text(soup_b)
        except Exception as e:
            _log("WARNING", "Backup article week-range parse failed: %s", e)
            rng_b = None

        if not rng_b:
            try:
                rng_b = find_week_range_from_tez2()
            except Exception as e:
                _log("WARNING", "Backup Tez2 week-range parse failed: %s", e)

        b_start = b_end = None
        if rng_b:
            b_start, b_end = rng_b
        else:
            pub_b = extract_article_publish_dt_kuwait(backup_url)
            if pub_b:
                b_start, b_end = gta_week_from_publish_snap(pub_b)

        if b_start and b_end and (b_start.date(), b_end.date()) == (week_start.date(), week_end.date()):
            try:
                rows_backup = parse_weekly_generic(backup_url)
                _log("INFO", "Parsed %d rows from backup; merging.", len(rows_backup))
                seen = {
                    (
                        (r.get("category") or "").lower(),
                        (r.get("item") or "").lower(),
                        (r.get("details") or "").lower(),
                        r.get("source_url") or "",
                    )
                    for r in rows_merged
                }
                for r in rows_backup:
                    key = (
                        (r.get("category") or "").lower(),
                        (r.get("item") or "").lower(),
                        (r.get("details") or "").lower(),
                        r.get("source_url") or "",
                    )
                    if key not in seen:
                        seen.add(key)
                        rows_merged.append(r)
            except Exception as e:
                _log("WARNING", "Backup parse/merge failed: %s", e)
        else:
            _log("INFO", "Backup article is not for the same week (or unknown); skipping merge.")

    # 5) Write PDF
    pdf_path = write_pdf(rows_merged, week_start, week_end)
    _log("INFO", "Saved PDF: %s", pdf_path)

    # 6) Optional email
    if send_email is None:
        send_email_flag = SEND_EMAIL
    else:
        send_email_flag = bool(send_email)

    email_sent = False
    email_error: Optional[str] = None

    if send_email_flag:
        if not email_config:
            email_error = "sendEmail=True but no emailConfig was provided."
            _log("WARNING", email_error)
        else:
            subject = f"GTA Online Weekly Update {week_start.date()} → {week_end.date()}"
            body = (
                f"GTA Online Weekly Update for {week_start.date()} → {week_end.date()}\n"
                f"Attached: {os.path.basename(pdf_path)}\n\n"
                f"Sent automatically by GTA Weekly Scraper."
            )
            try:
                send_email_with_attachment(
                    subject=subject,
                    body=body,
                    attachment_path=pdf_path,
                    smtp_server=email_config.get("smtp_server"),
                    smtp_port=email_config.get("smtp_port"),
                    username=email_config.get("username"),
                    password=email_config.get("password"),
                    email_from=email_config.get("from_addr"),
                    recipients=email_config.get("to_addrs"),
                    use_tls=bool(email_config.get("use_tls", True)),
                )
                email_sent = True
                _log("INFO", "Email sent successfully via sendMail.py")
            except Exception as e:
                email_error = str(e)
                _log("ERROR", "Email sending failed: %s", e)
    else:
        _log("INFO", "Email sending disabled for this run.")

    # 7) Group rows by category for API consumers
    sections: Dict[str, List[Dict[str, str]]] = {}
    for r in rows_merged:
        cat = (r.get("category") or "Uncategorized").strip() or "Uncategorized"
        sections.setdefault(cat, []).append(
            {
                "item": (r.get("item") or "").strip(),
                "details": (r.get("details") or "").strip(),
                "source_url": r.get("source_url") or "",
            }
        )

    return {
        "week_start": week_start.date().isoformat(),
        "week_end": week_end.date().isoformat(),
        "sources": [{"url": u, "label": lbl} for (u, lbl) in urls_to_try],
        "sections": sections,
        "row_count": len(rows_merged),
        "pdf_path": pdf_path,
        "email_sent": email_sent,
        "email_error": email_error,
        "logs": log_messages,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    # 1) Pick URL(s)
    urls_to_try: List[Tuple[str, str]] = []
    if MANUAL_URL.strip():
        urls_to_try.append((MANUAL_URL.strip(), "Manual"))
    else:
        try:
            p_url, p_title = find_latest_powerupgaming_weekly_page()
            urls_to_try.append((p_url, f"PowerUpGaming: {p_title}"))
        except Exception as e:
            logging.warning("PowerUpGaming discovery failed: %s", e)
        try:
            g_url, g_title = find_latest_gtabase_weekly_page()
            urls_to_try.append((g_url, f"GTABase: {g_title}"))
        except Exception as e:
            logging.warning("GTABase discovery failed: %s", e)
        try:
            r_url, r_title = find_latest_rockstarintel_weekly_page()
            urls_to_try.append((r_url, f"RockstarINTEL: {r_title}"))
        except Exception as e:
            logging.warning("RockstarINTEL discovery failed: %s", e)
        if not urls_to_try:
            logging.error("No candidate weekly URLs found.")
            return

    # 2) Determine week range using primary article
    chosen_url, chosen_label = urls_to_try[0]
    logging.info("Primary weekly URL: %s", chosen_url)
    soup = http_get_soup(chosen_url)

    rng = extract_week_range_from_text(soup)
    if rng:
        week_start, week_end = rng
        logging.info("Week from article text: %s -> %s", week_start.date(), week_end.date())
    else:
        tez = find_week_range_from_tez2()
        if tez:
            week_start, week_end = tez
            logging.info("Week from Tez2: %s -> %s", week_start.date(), week_end.date())
        else:
            pub_dt_kw = extract_article_publish_dt_kuwait(chosen_url)
            if pub_dt_kw:
                week_start, week_end = gta_week_from_publish_snap(pub_dt_kw)
                logging.info("Week from publish date (snapped Thu→Wed): %s -> %s", week_start.date(), week_end.date())
            else:
                week_start, week_end = gta_week_window_from_date(now_kw())
                logging.warning("Using current week: %s -> %s", week_start.date(), week_end.date())

    # 3) Parse primary
    try:
        rows_primary = parse_weekly_generic(chosen_url)
        logging.info("Parsed %d rows from primary.", len(rows_primary))
    except Exception as e:
        logging.exception("Primary parse failed: %s", e)
        rows_primary = []

    # 4) If backup exists & same week, merge
    rows_merged = list(rows_primary)
    if len(urls_to_try) > 1:
        backup_url, _ = urls_to_try[1]
        try:
            soup_b = http_get_soup(backup_url)
            rng_b = extract_week_range_from_text(soup_b) or find_week_range_from_tez2()
            if rng_b:
                b_start, b_end = rng_b
            else:
                pub_b = extract_article_publish_dt_kuwait(backup_url)
                b_start, b_end = gta_week_from_publish_snap(pub_b) if pub_b else (None, None)

            if b_start and b_end and (b_start.date(), b_end.date()) == (week_start.date(), week_end.date()):
                rows_backup = parse_weekly_generic(backup_url)
                logging.info("Parsed %d rows from backup; merging.", len(rows_backup))
                seen = set(
                    (r["category"].lower(), r["item"].lower(), (r["details"] or "").lower(), r["source_url"]) for r in
                    rows_merged
                )
                for r in rows_backup:
                    key = (r["category"].lower(), r["item"].lower(), (r["details"] or "").lower(), r["source_url"])
                    if key not in seen:
                        seen.add(key)
                        rows_merged.append(r)
            else:
                logging.info("Backup article is not for the same week; skip merge.")
        except Exception as e:
            logging.warning("Backup parse skipped due to error: %s", e)

    # 5) Write PDF (ONLY)
    pdf_path = write_pdf(rows_merged, week_start, week_end)
    logging.info("Saved PDF: %s", pdf_path)
    print(pdf_path)

    # 6) Email (toggleable)
    if not os.path.isfile(pdf_path):
        logging.error("PDF not found after save; email not sent.")
        return

    if SEND_EMAIL:
        logging.info("Email sending ENABLED. Waiting %d seconds before emailing...", SLEEP_BEFORE_EMAIL_SECONDS)
        if SLEEP_BEFORE_EMAIL_SECONDS > 0:
            time.sleep(SLEEP_BEFORE_EMAIL_SECONDS)
        subject = f"GTA Online Weekly Update {week_start.date()} → {week_end.date()}"
        body = (
            f"GTA Online Weekly Update for {week_start.date()} → {week_end.date()}\n"
            f"Attached: {os.path.basename(pdf_path)}\n\n"
            f"Sent automatically by GTA Weekly Scraper."
        )
        try:
            send_email_with_attachment(subject=subject, body=body, attachment_path=pdf_path)
            logging.info("Email sent successfully via sendMail.py")
        except Exception as e:
            logging.exception("Email sending failed (sendMail.py): %s", e)
    else:
        logging.info("Email sending DISABLED (SEND_EMAIL=False). Skipping email step.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.exception("Fatal error: %s", e)
        raise