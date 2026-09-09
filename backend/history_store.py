from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
import uuid
from storage import store, cloud_mode, runtime_dir

BASE_DIR = Path(__file__).resolve().parent
HISTORY_DIR = runtime_dir() / "history"

def save_snapshot(result: dict):
    result.setdefault("id", uuid.uuid4().hex)
    store.put("history", result["id"], result)
    return result["id"]

def get_snapshot(snapshot_id):
    data = store.get("history", snapshot_id)
    if data:
        return data
    # Read old local snapshots without moving or deleting the user's files.
    if not cloud_mode() and snapshot_id == Path(snapshot_id).name:
        try:
            data = json.loads((HISTORY_DIR / f"{snapshot_id}.json").read_text(encoding="utf-8"))
            data["id"] = snapshot_id
            return data
        except (OSError, ValueError):
            pass
    return None

def list_history(limit: int = 20):
    records = dict(store.list("history", limit))
    paths = [] if cloud_mode() else sorted(HISTORY_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            records.setdefault(path.stem, data)
        except (OSError, ValueError):
            continue
    output = []
    for key, data in records.items():
        data = {**data, "id": key}
        output.append({
                "id": key,
                "week_start": data.get("week_start"),
                "week_end": data.get("week_end"),
                "row_count": data.get("row_count", 0),
                "vehicle_count": len(data.get("vehicles") or []),
                "confidence": data.get("overall_confidence"),
                "created_at": data.get("generated_at"),
                "result": data,
            })
    return sorted(output, key=lambda row: row.get("created_at") or "", reverse=True)[:limit]

def latest_snapshot():
    items = list_history(1)
    return items[0]["result"] if items else None
