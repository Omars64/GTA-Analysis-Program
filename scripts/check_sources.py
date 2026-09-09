from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import app
from discovery import resolve_source
from config import DEFAULTS
from network import fetch_context
from gta_weekly_scraper import parse_weekly_generic

for url in DEFAULTS['source_urls']:
    try:
        with fetch_context(timeout=12, budget=45):
            article, title = resolve_source(url)
            print(article, title, len(parse_weekly_generic(article)), flush=True)
    except Exception as exc:
        print(type(exc).__name__, str(exc), flush=True)
