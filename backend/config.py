from __future__ import annotations
import json
import os
from pathlib import Path
from threading import RLock

BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
CONFIG_FILE = CONFIG_DIR / "settings.json"
DEFAULT_EXPORT_DIR = BASE_DIR / "runtime" / "exports"
_lock = RLock()

DEFAULTS = {
    "output_directory": str(DEFAULT_EXPORT_DIR),
    "request_timeout": 30,
    "source_retries": 2,
    "generate_pdf": True,
    "save_json": True,
    "history_limit": 52,
}

def _ensure():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps(DEFAULTS, indent=2), encoding="utf-8")

def get_settings():
    with _lock:
        _ensure()
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        merged = {**DEFAULTS, **data}
        return merged

def update_settings(patch: dict):
    allowed = set(DEFAULTS)
    clean = {k: v for k, v in (patch or {}).items() if k in allowed}
    if "output_directory" in clean:
        value = os.path.abspath(os.path.expanduser(str(clean["output_directory"])))
        os.makedirs(value, exist_ok=True)
        if not os.access(value, os.W_OK):
            raise ValueError("Output directory is not writable")
        clean["output_directory"] = value
    with _lock:
        current = get_settings()
        current.update(clean)
        CONFIG_FILE.write_text(json.dumps(current, indent=2), encoding="utf-8")
        return current
