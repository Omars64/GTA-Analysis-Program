from __future__ import annotations
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import tempfile
import time
from urllib.parse import urlsplit

if not os.getenv('VERCEL') and os.getenv('GTA_CLOUD') != '1':
    recovery = Path(__file__).resolve().parents[1] / '.env.gta-access.local'
    if recovery.exists():
        for line in recovery.read_text().splitlines():
            key, separator, value = line.partition('=')
            if separator and key in {'GTA_APP_PASSWORD', 'GTA_SESSION_SECRET', 'SMTP_USERNAME', 'SMTP_PASSWORD', 'SMTP_SERVER', 'SMTP_PORT', 'EMAIL_FROM'}:
                os.environ.setdefault(key, value.strip())

# Respect trusted Windows enterprise/proxy certificates without disabling TLS checks.
if os.name == "nt":
    import truststore
    truststore.inject_into_ssl()

from flask import Flask, jsonify, request, send_file, Response, session
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from config import get_settings, update_settings, DEFAULT_EXPORT_DIR
from history_store import list_history, latest_snapshot, get_snapshot
from intelligence_engine import _write_pdf
from job_manager import manager, TERMINAL
from knowledge_engine import answer_query
from network import validate_url
from storage import cloud_mode, store
from report_editor import revise
from sendMail import send_email_with_attachment

app = Flask(__name__)
password = os.getenv("GTA_APP_PASSWORD", "")
app.secret_key = hashlib.sha256((os.getenv("GTA_SESSION_SECRET", "gta-session:") + password).encode()).hexdigest()
app.config.update(MAX_CONTENT_LENGTH=32768, SESSION_COOKIE_HTTPONLY=True,
                  SESSION_COOKIE_SECURE=cloud_mode(), SESSION_COOKIE_SAMESITE="Lax")
origins = [x.strip() for x in os.getenv("GTA_CORS_ORIGINS", "" if cloud_mode() else "http://localhost:5173,http://127.0.0.1:5173").split(",") if x.strip()]
CORS(app, resources={r"/api/*": {"origins": origins}}, supports_credentials=True)


def setup_missing():
    missing = []
    if cloud_mode():
        if len(password) < 14:
            missing.append("GTA_APP_PASSWORD (at least 14 characters)")
        if not store.url:
            missing.append("DATABASE_URL")
    return missing


@app.before_request
def protect_api():
    if not request.path.startswith("/api/"):
        return
    origin = request.headers.get("Origin")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
        same_origin = urlsplit(origin).netloc == request.host
        if not same_origin and origin not in origins:
            return jsonify(error="Origin is not allowed."), 403
    if request.path in {"/api/health", "/api/session"} or request.method == "OPTIONS":
        return
    if setup_missing():
        return jsonify(error="Cloud setup is incomplete.", missing=setup_missing()), 503
    if password and not session.get("authenticated"):
        return jsonify(error="Sign in to use your companion."), 401


@app.after_request
def response_headers(response):
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.errorhandler(Exception)
def handle_error(exc):
    if isinstance(exc, HTTPException):
        return jsonify(error=exc.description), exc.code
    if isinstance(exc, ValueError):
        return jsonify(error=str(exc)), 400
    app.logger.exception("API request failed")
    return jsonify(error="The service could not complete the request. Check server configuration and retry."), 500


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("A JSON object is required.")
    return data


def flag(data, key, default=False):
    value = data.get(key, default)
    if type(value) is not bool:
        raise ValueError(f"{key} must be true or false.")
    return value


@app.route("/api/session", methods=["GET", "POST", "DELETE"])
def auth_session():
    if setup_missing():
        return jsonify(error="Cloud setup is incomplete.", missing=setup_missing()), 503
    if request.method == "DELETE":
        session.clear()
    if request.method == "POST":
        entered = body().get("password", "")
        if not isinstance(entered, str) or not secrets.compare_digest(entered.encode(), password.encode()):
            return jsonify(error="Incorrect password."), 401
        session.clear()
        session["authenticated"] = True
    return jsonify(authenticated=bool(session.get("authenticated") or not password), required=bool(password))


@app.get("/api/capabilities")
def capabilities():
    return jsonify(cloud=cloud_mode(), native_folder_picker=not cloud_mode() and os.name == "nt",
                   email_configured=bool(os.getenv("SMTP_USERNAME") and os.getenv("SMTP_PASSWORD")),
                   email_recipients_configured=bool(os.getenv("EMAIL_TO")))


def _params(data):
    settings = get_settings()
    manual = data.get("manualUrl") or None
    if manual:
        validate_url(manual)
        if cloud_mode():
            host = urlsplit(manual).hostname.lower()
            allowed = ("powerupgaming.co.uk", "gtabase.com", "rockstarintel.com", "rockstargames.com")
            if not any(host == name or host.endswith("." + name) for name in allowed):
                raise ValueError("Use a weekly article from PowerUpGaming, GTABase, RockstarINTEL, or Rockstar Games.")
    email_in = data.get("emailConfig") or {}
    if not isinstance(email_in, dict):
        raise ValueError("emailConfig must be an object.")
    recipients = email_in.get("recipients")
    if isinstance(recipients, str):
        recipients = [value.strip() for value in recipients.split(",") if value.strip()]
    if recipients is not None and (not isinstance(recipients, list) or any(not isinstance(v, str) or "@" not in v or "\n" in v or "\r" in v for v in recipients)):
        raise ValueError("Enter valid recipient email addresses.")
    email_config = {"to_addrs": recipients or None}
    if not cloud_mode():
        email_config.update(smtp_server=email_in.get("smtpServer"), smtp_port=email_in.get("smtpPort"),
                            username=email_in.get("username"), password=email_in.get("password"),
                            from_addr=email_in.get("fromAddress"), use_tls=email_in.get("useTls", True))
    send_email = flag(data, "sendEmail")
    generate_pdf = flag(data, "generatePdf", settings["generate_pdf"])
    if send_email:
        if not generate_pdf:
            raise ValueError("Enable PDF generation before emailing a report.")
        if not ((email_config.get("username") or os.getenv("SMTP_USERNAME")) and (email_config.get("password") or os.getenv("SMTP_PASSWORD"))):
            raise ValueError("Configure SMTP credentials before enabling email.")
        if not (recipients or os.getenv("EMAIL_TO")):
            raise ValueError("Provide an email recipient.")
    output = str(DEFAULT_EXPORT_DIR) if cloud_mode() else data.get("outputDirectory") or settings["output_directory"]
    if not isinstance(output, str):
        raise ValueError("Output directory must be a path.")
    return dict(manual_url=manual, output_dir=str(Path(output).expanduser().resolve()),
                source_urls=settings["source_urls"],
                send_email=send_email, email_config=email_config if send_email else None,
                source_retries=settings["source_retries"], request_timeout=settings["request_timeout"],
                generate_pdf=generate_pdf, save_json=flag(data, "saveJson", settings["save_json"]))


@app.post("/api/runs")
@app.post("/api/gta-weekly/run")
def create_run():
    active = manager.latest_active()
    if active:
        return jsonify(error="A scan is already active.", job=active.snapshot()), 409
    job = manager.create(_params(body()))
    return jsonify(job.snapshot()), 202


@app.get("/api/runs/active")
def active_run():
    job = manager.latest_active()
    return jsonify(job.snapshot() if job else {})


@app.get("/api/runs/<job_id>")
def get_run(job_id):
    job = manager.get(job_id)
    return (jsonify(job.snapshot()), 200) if job else (jsonify(error="Run not found"), 404)


@app.post("/api/runs/<job_id>/cancel")
def cancel_run(job_id):
    job = manager.cancel(job_id)
    return (jsonify(job.snapshot()), 200) if job else (jsonify(error="Run not found"), 404)


@app.get("/api/runs/<job_id>/events")
def run_events(job_id):
    if not manager.get(job_id):
        return jsonify(error="Run not found"), 404
    try:
        cursor = max(0, int(request.headers.get("Last-Event-ID") or request.args.get("after", 0)))
    except ValueError:
        raise ValueError("Invalid event cursor.")
    def stream():
        nonlocal cursor
        deadline = time.monotonic() + 25
        yield "retry: 2000\n\n"
        while time.monotonic() < deadline:
            job = manager.get(job_id)
            if not job:
                return
            data = job.snapshot()
            for event in data["events"]:
                if event["seq"] > cursor:
                    cursor = event["seq"]
                    yield f"id: {cursor}\nevent: progress\ndata: {json.dumps(event)}\n\n"
            if data["status"] in TERMINAL:
                yield f"event: done\ndata: {json.dumps(data)}\n\n"
                return
            yield ": keepalive\n\n"
            time.sleep(2)
    return Response(stream(), mimetype="text/event-stream", headers={"X-Accel-Buffering": "no"})


def export_snapshot(data, kind):
    if not data:
        return jsonify(error="Report not found"), 404
    enabled = data.get("exports", {}).get(kind, bool(data.get(f"{kind}_path")))
    if not enabled:
        return jsonify(error=f"{kind.upper()} export was disabled for this report."), 404
    name = f"GTA_Weekly_{data['week_start']}_to_{data['week_end']}"
    if kind == "json":
        return send_file(io.BytesIO(json.dumps(data, ensure_ascii=False, indent=2).encode()), mimetype="application/json",
                         as_attachment=True, download_name=f"{name}.json")
    if kind == "pdf":
        with tempfile.TemporaryDirectory(prefix="gta-pdf-") as output:
            path = _write_pdf(data, output)
            content = Path(path).read_bytes()
        return send_file(io.BytesIO(content), mimetype="application/pdf", as_attachment=True, download_name=f"{name}.pdf")
    return jsonify(error="Unknown export format"), 404


@app.get("/api/runs/<job_id>/<kind>")
def run_export(job_id, kind):
    job = manager.get(job_id)
    data = job.data.get("result") if job else None
    return export_snapshot(get_snapshot(job_id) or data, kind)


@app.get("/api/history/<snapshot_id>/<kind>")
def history_export(snapshot_id, kind):
    return export_snapshot(get_snapshot(snapshot_id), kind)


@app.get("/api/history/<snapshot_id>")
def history_item(snapshot_id):
    data = get_snapshot(snapshot_id)
    return (jsonify(data), 200) if data else (jsonify(error="Report not found"), 404)


@app.put('/api/history/<snapshot_id>')
def edit_report(snapshot_id):
    if not get_snapshot(snapshot_id):
        return jsonify(error='Report not found'), 404
    payload = body()
    return jsonify(store.mutate('history', snapshot_id, lambda current: revise(current, payload)))


@app.post('/api/history/<snapshot_id>/email')
def email_report(snapshot_id):
    data = get_snapshot(snapshot_id)
    if not data:
        return jsonify(error='Report not found'), 404
    payload = body()
    recipients = payload.get('recipients')
    if not isinstance(recipients, list) or not 1 <= len(recipients) <= 10 or any(not isinstance(v, str) or '@' not in v or '\n' in v or '\r' in v for v in recipients):
        raise ValueError('Provide 1 to 10 valid recipient email addresses.')
    key = payload.get('requestId')
    if not isinstance(key, str) or not 16 <= len(key) <= 80:
        raise ValueError('A valid delivery request ID is required.')
    if not os.getenv('SMTP_USERNAME') or not os.getenv('SMTP_PASSWORD'):
        return jsonify(error='Email is not configured on the server.'), 503
    claimed = []
    def claim(previous):
        if previous is None:
            claimed.append(True)
            return {'status': 'attempting'}
        return previous
    previous = store.mutate('email', snapshot_id + ':' + key, claim)
    if not claimed:
        return jsonify(status=previous['status']), 200 if previous['status'] == 'sent' else 409
    try:
        with tempfile.TemporaryDirectory(prefix='gta-mail-') as output:
            path = _write_pdf(data, output)
            send_email_with_attachment(subject=f"GTA Weekly Report {data['week_start']}", body='Your requested weekly report is attached.', attachment_path=path, recipients=recipients)
        store.put('email', snapshot_id + ':' + key, {'status': 'sent'})
        return jsonify(status='sent')
    except Exception:
        store.put('email', snapshot_id + ':' + key, {'status': 'failed'})
        return jsonify(error='Email delivery failed or could not be confirmed. Check SMTP configuration before retrying.'), 502


@app.get("/api/history")
def history():
    limit = min(200, max(1, int(request.args.get("limit", get_settings()["history_limit"]))))
    return jsonify(history=list_history(limit))


@app.get("/api/latest")
def latest():
    return jsonify(latest_snapshot() or {})


@app.post("/api/knowledge/query")
def knowledge_query():
    data = body()
    query = data.get("query", "")
    if not isinstance(query, str) or not query.strip() or len(query) > 1000:
        raise ValueError("Enter a question of 1 to 1000 characters.")
    snapshot = get_snapshot(data["snapshotId"]) if data.get("snapshotId") else None
    if data.get("snapshotId") and not snapshot:
        return jsonify(error="Report not found"), 404
    return jsonify(answer_query(query, snapshot))


@app.get("/api/settings")
def settings_get():
    return jsonify(get_settings())


@app.put("/api/settings")
def settings_put():
    return jsonify(update_settings(body()))


@app.post("/api/system/select-output-directory")
def select_output_directory():
    if cloud_mode() or os.name != "nt":
        return jsonify(error="Download reports through your browser in hosted mode."), 409
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    try:
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(title="Select GTA Weekly export directory")
    finally:
        root.destroy()
    if not path:
        return jsonify(cancelled=True)
    settings = update_settings({"output_directory": path})
    return jsonify(cancelled=False, output_directory=settings["output_directory"])


@app.get("/api/health")
def health():
    missing = setup_missing()
    if missing:
        return jsonify(status="setup_required", missing=missing), 503
    try:
        store.get("settings", "default")
    except Exception:
        return jsonify(status="error", error="Database connection failed"), 503
    return jsonify(status="ok", engine="GTA Weekly Intelligence", schema_version=3)


if __name__ == "__main__":
    manager.resume_local()
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False, threaded=True)
