"""Durable jobs with atomic step leases and resumable queue delivery."""
import copy
from datetime import datetime
import os
import threading
import time
import uuid

from network import fetch_context
from storage import store

TERMINAL = {"completed", "failed", "cancelled"}


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Job:
    def __init__(self, data):
        self.data = data
        self.id = data["id"]

    def snapshot(self):
        return {key: value for key, value in self.data.items() if not key.startswith("_")}


class JobManager:
    def __init__(self, storage=None, dispatch=None, advance=None):
        self.store = storage or store
        self.dispatch = dispatch
        self.advance = advance
        self.email_configs = {}

    def _queue(self, job_id, version):
        if self.dispatch:
            self.dispatch(job_id, version)
        elif os.getenv("VERCEL") == "1":
            from tasks import run_step
            run_step.apply_async(args=[job_id, version], task_id=f"{job_id}-{version}")
        else:
            threading.Thread(target=self.execute, args=(job_id, version), daemon=True).start()

    def create(self, params):
        job_id = uuid.uuid4().hex
        params = copy.deepcopy(params)
        email_config = params.get("email_config")
        if email_config:
            # Queue messages and stored jobs never contain SMTP passwords.
            self.email_configs[job_id] = email_config
            params["email_config"] = {"to_addrs": email_config.get("to_addrs")}
        data = {
            "id": job_id, "status": "queued", "stage": "queued", "progress": 0,
            "message": "Queued", "created_at": now(), "started_at": None, "finished_at": None,
            "result": None, "error": None, "cancel_requested": False, "events": [],
            "_params": params, "_state": {}, "_version": 0, "_lease": 0,
        }
        self.store.put("jobs", job_id, data)
        try:
            self._queue(job_id, 0)
        except Exception:
            self._finish(job_id, "failed", "Unable to enqueue this scan. Check the worker configuration.")
            raise RuntimeError("Unable to enqueue the scan. Please try again.")
        return self.get(job_id)

    def get(self, job_id):
        data = self.store.get("jobs", job_id)
        return Job(data) if data else None

    def latest_active(self):
        for _, data in self.store.list("jobs", 200):
            if data["status"] not in TERMINAL:
                # A status refresh repairs interrupted local processes once their lease expires.
                if os.getenv("VERCEL") != "1" and not self.dispatch and data["_lease"] <= time.time():
                    self._queue(data["id"], data["_version"])
                return Job(data)
        return None

    def _event(self, data, level="info", meta=None):
        event = {key: data[key] for key in ("status", "stage", "progress", "message")}
        event.update(seq=len(data["events"]) + 1, at=now(), level=level, meta=meta or {})
        data["events"].append(event)

    def _finish(self, job_id, status, message, owner=None):
        def finish(data):
            if data is None or data["status"] in TERMINAL:
                return data
            if owner and data.get("_owner") != owner:
                return data
            data.update(status=status, stage=status, message=message, finished_at=now(), _lease=0)
            if status == "failed":
                data["error"] = message
            self._event(data, "error" if status == "failed" else "warning")
            return data
        self.store.mutate("jobs", job_id, finish)
        self.email_configs.pop(job_id, None)

    def cancel(self, job_id):
        if not self.get(job_id):
            return None
        def cancel(data):
            if data["status"] not in TERMINAL:
                data.update(cancel_requested=True, message="Cancellation requested…")
                self._event(data, "warning")
            return data
        self.store.mutate("jobs", job_id, cancel)
        current = self.get(job_id)
        if current.data["_lease"] <= time.time():
            self._finish(job_id, "cancelled", "Run cancelled by user")
        return self.get(job_id)

    def execute(self, job_id, version):
        claimed = []
        token = uuid.uuid4().hex
        def claim(data):
            if not data or data["status"] in TERMINAL:
                return data
            if data["_version"] != version or data["_lease"] > time.time():
                return data
            data.update(status="running", _lease=time.time() + 240, _owner=token)
            data["started_at"] = data["started_at"] or now()
            claimed.append(True)
            return data
        data = self.store.mutate("jobs", job_id, claim)
        if not claimed:
            # A redelivered message can repair a crash between checkpoint and enqueue.
            if data and data["status"] not in TERMINAL and data["_version"] > version:
                self._queue(job_id, data["_version"])
            return
        def cancelled():
            latest = self.store.get("jobs", job_id)
            return latest["cancel_requested"] or latest.get("_owner") != token

        def progress(stage, pct, message, meta=None):
            def update(latest):
                if latest.get("_owner") == token and latest["status"] not in TERMINAL:
                    latest.update(stage=stage, progress=max(latest["progress"], int(pct)), message=message)
                    self._event(latest, (meta or {}).get("level", "info"), meta)
                return latest
            self.store.mutate("jobs", job_id, update)
        try:
            if data["cancel_requested"]:
                raise InterruptedError("Run cancelled by user")
            from scan_pipeline import advance
            params = data["_params"]
            if job_id in self.email_configs:
                params["email_config"] = self.email_configs[job_id]
            with fetch_context(params.get("request_timeout", 20), cancelled, budget=150):
                state, result = (self.advance or advance)(job_id, data["_state"], params, progress, cancelled)
            def checkpoint(latest):
                if latest.get("_owner") != token or latest["status"] in TERMINAL:
                    raise InterruptedError("Run was superseded by another worker")
                latest.update(_state=state, _version=version + 1, _lease=0)
                if result:
                    latest.update(status="completed", stage="complete", progress=100, result=result,
                                  finished_at=now(), message="Weekly intelligence scan completed")
                    latest["_params"] = {}
                    self._event(latest, "success")
                return latest
            updated = self.store.mutate("jobs", job_id, checkpoint)
        except InterruptedError:
            self._finish(job_id, "cancelled", "Run cancelled by user", owner=token)
            return
        except Exception as exc:
            import logging
            logging.exception("Scan step failed: %s", job_id)
            message = str(exc) if isinstance(exc, ValueError) else f"Scan step failed ({type(exc).__name__}). Retry the scan."
            self._finish(job_id, "failed", message, owner=token)
            return
        if updated["status"] not in TERMINAL:
            # If publishing fails, let the queue retry this delivery and repair the handoff.
            self._queue(job_id, version + 1)
        else:
            self.email_configs.pop(job_id, None)

    def resume_local(self):
        if os.getenv("VERCEL") == "1":
            return
        for job_id, data in self.store.list("jobs", 200):
            if data["status"] not in TERMINAL and data["_lease"] <= time.time():
                self._queue(job_id, data["_version"])


manager = JobManager()
