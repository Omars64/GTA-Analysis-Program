"""Exercise a real deployed scan without exposing credentials or sending email."""
import argparse
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit

if os.name == "nt":
    import truststore
    truststore.inject_into_ssl()
import requests

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://gta-analysis-program.vercel.app")
    parser.add_argument("--manual-url")
    parser.add_argument("--resume")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    base = args.url.rstrip("/")
    host = urlsplit(base).hostname or ""
    if host not in {"localhost", "127.0.0.1", "gta-analysis-program.vercel.app"}:
        raise SystemExit("This verifier only sends app credentials to the named production app or localhost.")
    client = requests.Session()

    def request(method, path, **kwargs):
        response = client.request(method, base + "/api" + path, timeout=40, **kwargs)
        if not response.ok:
            raise RuntimeError(f"{method} {path}: HTTP {response.status_code}: {response.text[:240]}")
        return response

    assert request("GET", "/health").json()["status"] == "ok"
    auth = request("GET", "/session").json()
    if auth["required"]:
        assert client.get(base + "/api/history", timeout=30).status_code == 401
        values = dict(line.split("=", 1) for line in (ROOT / ".env.gta-access.local").read_text().splitlines() if "=" in line and not line.startswith("#"))
        request("POST", "/session", json={"password": values["GTA_APP_PASSWORD"]})
        assert request("GET", "/session").json()["authenticated"]
    print("PASS: health, database, private session", flush=True)
    request("GET", "/settings")
    capabilities = request("GET", "/capabilities").json()
    print(f"Email configured: {capabilities['email_configured']} (no email will be sent)", flush=True)
    if args.resume:
        job_id = args.resume
    else:
        payload = {"sendEmail": False, "generatePdf": True, "saveJson": True}
        if args.manual_url:
            payload["manualUrl"] = args.manual_url
        job_id = request("POST", "/runs", json=payload).json()["id"]
    print(f"Run: {job_id}", flush=True)
    last = None
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        job = request("GET", f"/runs/{job_id}").json()
        status = (job["status"], job["stage"], job["progress"], job["message"])
        if status != last:
            print(f"{status[0]} | {status[1]} | {status[2]}% | {status[3]}", flush=True)
            last = status
        if job["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(5)
    else:
        raise RuntimeError(f"Verification time limit reached; run {job_id} remains resumable.")
    if job["status"] != "completed":
        raise RuntimeError(job.get("error") or job["status"])
    result = job["result"]
    assert result["items"], "No extracted items"
    assert request("GET", f"/history/{job_id}").json()["id"] == job_id
    assert any(item["id"] == job_id for item in request("GET", "/history").json()["history"])
    assert request("GET", "/latest").json()["id"] == job_id
    answer = request("POST", "/knowledge/query", json={"query": "podium vehicle", "snapshotId": job_id}).json()
    assert answer["matches"], "Podium query has no source-backed matches"
    output = ROOT / "backend" / "runtime" / "verification" / job_id
    output.mkdir(parents=True, exist_ok=True)
    for kind in ("json", "pdf"):
        response = request("GET", f"/history/{job_id}/{kind}")
        if kind == "pdf":
            assert response.content.startswith(b"%PDF")
        else:
            assert response.json()["id"] == job_id
        (output / f"report.{kind}").write_bytes(response.content)
    # A fresh login proves reports do not depend on the scanning session.
    if auth["required"]:
        request("DELETE", "/session")
        assert client.get(base + "/api/history", timeout=30).status_code == 401
        request("POST", "/session", json={"password": values["GTA_APP_PASSWORD"]})
        assert request("GET", f"/history/{job_id}").json()["id"] == job_id
    print(f"PASS: scan, queue continuation, archive, query, PDF, JSON, session recovery. Items: {result['row_count']}; vehicles: {len(result['vehicles'])}.", flush=True)
    print(f"Report files: {output}", flush=True)
    print(f"Source warnings: {result.get('warnings', [])}", flush=True)


if __name__ == "__main__":
    main()
