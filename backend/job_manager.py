from __future__ import annotations
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from intelligence_engine import run_intelligence_scan

@dataclass
class Job:
    id: str
    status: str = "queued"
    stage: str = "queued"
    progress: int = 0
    message: str = "Queued"
    created_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds"))
    started_at: str | None = None
    finished_at: str | None = None
    result: dict | None = None
    error: str | None = None
    cancel_requested: bool = False
    events: list[dict] = field(default_factory=list)
    lock: threading.RLock = field(default_factory=threading.RLock)

    def snapshot(self):
        with self.lock:
            return {
                "id": self.id, "status": self.status, "stage": self.stage, "progress": self.progress,
                "message": self.message, "created_at": self.created_at, "started_at": self.started_at,
                "finished_at": self.finished_at, "result": self.result, "error": self.error,
                "cancel_requested": self.cancel_requested,
            }

class JobManager:
    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self.lock = threading.RLock()

    def create(self, params: dict):
        job = Job(id=uuid.uuid4().hex[:12])
        with self.lock:
            self.jobs[job.id] = job
        t = threading.Thread(target=self._run, args=(job, params), daemon=True, name=f"gta-job-{job.id}")
        t.start()
        return job

    def get(self, job_id: str):
        with self.lock:
            return self.jobs.get(job_id)

    def cancel(self, job_id: str):
        job = self.get(job_id)
        if not job: return None
        with job.lock:
            job.cancel_requested = True
            if job.status in {"queued", "running"}:
                job.message = "Cancellation requested…"
                job.events.append(self._event(job, "warning"))
        return job

    def _event(self, job, level="info", meta=None):
        return {
            "seq": len(job.events) + 1,
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "status": job.status, "stage": job.stage, "progress": job.progress,
            "message": job.message, "level": level, "meta": meta or {},
        }

    def _run(self, job: Job, params: dict):
        with job.lock:
            job.status = "running"; job.started_at = datetime.now().astimezone().isoformat(timespec="seconds")
            job.message = "Worker started"; job.events.append(self._event(job))

        def progress(stage, pct, message, meta=None):
            with job.lock:
                job.stage = stage; job.progress = int(pct); job.message = message
                level = (meta or {}).get("level", "info")
                job.events.append(self._event(job, level, meta))

        try:
            result = run_intelligence_scan(progress=progress, cancel=lambda: job.cancel_requested, **params)
            with job.lock:
                job.result = result; job.status = "completed"; job.stage = "complete"; job.progress = 100
                job.message = "Weekly intelligence scan completed"; job.finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
                job.events.append(self._event(job, "success"))
        except InterruptedError as exc:
            with job.lock:
                job.status = "cancelled"; job.stage = "cancelled"; job.message = str(exc); job.finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
                job.events.append(self._event(job, "warning"))
        except Exception as exc:
            with job.lock:
                job.status = "failed"; job.stage = "failed"; job.error = str(exc); job.message = str(exc); job.finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
                job.events.append(self._event(job, "error"))

manager = JobManager()
