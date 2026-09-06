from __future__ import annotations
import json
import os
import time
from flask import Flask, jsonify, request, send_file, Response
from flask_cors import CORS

from config import get_settings, update_settings
from history_store import list_history, latest_snapshot
from job_manager import manager
from knowledge_engine import answer_query
from intelligence_engine import run_intelligence_scan

app = Flask(__name__)
allowed_origins = os.getenv("GTA_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
CORS(app, resources={r"/api/*": {"origins": [x.strip() for x in allowed_origins if x.strip()]}})

def _params(data: dict):
    settings = get_settings()
    email_cfg_in = data.get("emailConfig") or {}
    recipients = email_cfg_in.get("recipients") or []
    if isinstance(recipients, str):
        recipients = [x.strip() for x in recipients.split(",") if x.strip()]
    email_config = {
        "smtp_server": email_cfg_in.get("smtpServer") or "smtp.gmail.com",
        "smtp_port": int(email_cfg_in.get("smtpPort") or 587),
        "username": email_cfg_in.get("username") or "",
        "password": email_cfg_in.get("password") or "",
        "from_addr": email_cfg_in.get("fromAddress") or email_cfg_in.get("username") or "",
        "to_addrs": recipients,
        "use_tls": bool(email_cfg_in.get("useTls", True)),
    }
    return {
        "manual_url": data.get("manualUrl") or None,
        "output_dir": data.get("outputDirectory") or settings["output_directory"],
        "send_email": bool(data.get("sendEmail")),
        "email_config": email_config if data.get("sendEmail") else None,
        "source_retries": int(settings.get("source_retries", 2)),
        "generate_pdf": bool(data.get("generatePdf", settings.get("generate_pdf", True))),
        "save_json": bool(data.get("saveJson", settings.get("save_json", True))),
    }

@app.post("/api/runs")
def create_run():
    job = manager.create(_params(request.get_json(silent=True) or {}))
    return jsonify(job.snapshot()), 202

@app.get("/api/runs/<job_id>")
def get_run(job_id):
    job = manager.get(job_id)
    return (jsonify(job.snapshot()), 200) if job else (jsonify({"error":"Run not found"}), 404)

@app.post("/api/runs/<job_id>/cancel")
def cancel_run(job_id):
    job = manager.cancel(job_id)
    return (jsonify(job.snapshot()), 200) if job else (jsonify({"error":"Run not found"}), 404)

@app.get("/api/runs/<job_id>/events")
def run_events(job_id):
    job = manager.get(job_id)
    if not job: return jsonify({"error":"Run not found"}), 404
    def stream():
        cursor = 0
        while True:
            with job.lock:
                pending = list(job.events[cursor:])
                terminal = job.status in {"completed", "failed", "cancelled"}
            for event in pending:
                cursor += 1
                yield f"event: progress\ndata: {json.dumps(event)}\n\n"
            if terminal and cursor >= len(job.events):
                yield f"event: done\ndata: {json.dumps(job.snapshot())}\n\n"
                break
            yield ": keepalive\n\n"
            time.sleep(.65)
    return Response(stream(), mimetype="text/event-stream", headers={"Cache-Control":"no-cache", "X-Accel-Buffering":"no"})

@app.get("/api/runs/<job_id>/pdf")
def run_pdf(job_id):
    job = manager.get(job_id)
    path = job.result.get("pdf_path") if job and job.result else None
    if not path or not os.path.isfile(path): return jsonify({"error":"PDF not available"}), 404
    return send_file(path, mimetype="application/pdf", as_attachment=False)

@app.get("/api/runs/<job_id>/json")
def run_json(job_id):
    job = manager.get(job_id)
    path = job.result.get("json_path") if job and job.result else None
    if not path or not os.path.isfile(path): return jsonify({"error":"JSON export not available"}), 404
    return send_file(path, mimetype="application/json", as_attachment=False)

@app.get("/api/history")
def history():
    limit = min(100, max(1, int(request.args.get("limit", 20))))
    return jsonify({"history": list_history(limit)})

@app.get("/api/latest")
def latest():
    return jsonify(latest_snapshot() or {})

@app.post("/api/knowledge/query")
def knowledge_query():
    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()
    if not query: return jsonify({"error":"query is required"}), 400
    return jsonify(answer_query(query))

@app.get("/api/settings")
def settings_get():
    return jsonify(get_settings())

@app.put("/api/settings")
def settings_put():
    try: return jsonify(update_settings(request.get_json(silent=True) or {}))
    except Exception as exc: return jsonify({"error":str(exc)}), 400

@app.post("/api/system/select-output-directory")
def select_output_directory():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        path = filedialog.askdirectory(title="Select GTA Weekly export directory")
        root.destroy()
        if not path: return jsonify({"cancelled": True})
        settings = update_settings({"output_directory": path})
        return jsonify({"cancelled": False, "output_directory": settings["output_directory"]})
    except Exception as exc:
        return jsonify({"error": f"Native folder picker unavailable: {exc}"}), 501

# Backward-compatible endpoint: same route as the original project.
@app.post("/api/gta-weekly/run")
def legacy_run():
    try: return jsonify(run_intelligence_scan(**_params(request.get_json(silent=True) or {})))
    except Exception as exc: return jsonify({"error":str(exc)}), 500

@app.get("/api/health")
def health():
    return jsonify({"status":"ok", "engine":"GTA Weekly Intelligence", "schema_version":2})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=os.getenv("FLASK_DEBUG", "0") == "1", threaded=True)
