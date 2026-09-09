import json
import os
from pathlib import Path
from storage import BASE_DIR, cloud_mode, runtime_dir, store

DEFAULT_EXPORT_DIR = runtime_dir() / "exports"

DEFAULTS = {
    "output_directory": str(DEFAULT_EXPORT_DIR),
    "request_timeout": 20,
    "source_retries": 2,
    "generate_pdf": True,
    "save_json": True,
    "history_limit": 52,
    "game_number": 5,
    "source_urls": ["https://rockstarintel.com/category/gta/event-week/", "https://www.gtabase.com/grand-theft-auto-v/news/", "https://powerupgaming.co.uk/?s=GTA+Online+Weekly+Update"],
}

def get_settings():
    saved = store.get("settings", "default")
    if saved is None:
        legacy = BASE_DIR / "config" / "settings.json"
        try:
            saved = json.loads(legacy.read_text(encoding="utf-8")) if not cloud_mode() else {}
        except (OSError, ValueError):
            saved = {}
    result = {**DEFAULTS, **(saved or {})}
    if cloud_mode():
        result["output_directory"] = str(DEFAULT_EXPORT_DIR)
    return result


def update_settings(patch):
    clean = {key: value for key, value in patch.items() if key in DEFAULTS}
    for key, low, high in [("game_number", 1, 20), ("request_timeout", 5, 60), ("source_retries", 1, 3), ("history_limit", 1, 200)]:
        if key in clean and (type(clean[key]) is not int or not low <= clean[key] <= high):
            raise ValueError(f"{key} must be an integer between {low} and {high}.")
    for key in ("generate_pdf", "save_json"):
        if key in clean and type(clean[key]) is not bool:
            raise ValueError(f"{key} must be true or false.")
    if "source_urls" in clean:
        from network import validate_url
        if not isinstance(clean["source_urls"], list) or not 1 <= len(clean["source_urls"]) <= 10:
            raise ValueError("Provide 1 to 10 source URLs.")
        clean["source_urls"] = list(dict.fromkeys(validate_url(url.strip()) for url in clean["source_urls"] if isinstance(url, str) and url.strip()))
        if not clean["source_urls"]:
            raise ValueError("Provide at least one source URL.")
    if cloud_mode():
        clean.pop("output_directory", None)
    elif "output_directory" in clean:
        if not isinstance(clean["output_directory"], str) or not clean["output_directory"].strip():
            raise ValueError("Output directory cannot be empty.")
        path = Path(clean["output_directory"]).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        if not os.access(path, os.W_OK):
            raise ValueError("Output directory is not writable.")
        clean["output_directory"] = str(path)
    current = get_settings()
    return store.mutate("settings", "default", lambda saved: {**current, **(saved or {}), **clean})
