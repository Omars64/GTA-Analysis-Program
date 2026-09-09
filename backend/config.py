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
    for key, low, high in [("request_timeout", 5, 60), ("source_retries", 1, 3), ("history_limit", 1, 200)]:
        if key in clean and (type(clean[key]) is not int or not low <= clean[key] <= high):
            raise ValueError(f"{key} must be an integer between {low} and {high}.")
    for key in ("generate_pdf", "save_json"):
        if key in clean and type(clean[key]) is not bool:
            raise ValueError(f"{key} must be true or false.")
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
