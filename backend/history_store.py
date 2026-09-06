from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
HISTORY_DIR = BASE_DIR / "runtime" / "history"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

def save_snapshot(result: dict):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    week = result.get("week_start", "unknown")
    path = HISTORY_DIR / f"{week}_{stamp}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)

def list_history(limit: int = 20):
    records = []
    for path in sorted(HISTORY_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            records.append({
                "id": path.stem,
                "week_start": data.get("week_start"),
                "week_end": data.get("week_end"),
                "row_count": data.get("row_count", 0),
                "vehicle_count": len(data.get("vehicles") or []),
                "confidence": data.get("overall_confidence"),
                "created_at": data.get("generated_at"),
                "result": data,
            })
        except Exception:
            continue
    return records

def latest_snapshot():
    items = list_history(1)
    return items[0]["result"] if items else None
