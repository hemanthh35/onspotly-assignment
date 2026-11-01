"""Background job runner.

Jobs are persisted in the database (status, progress, timings, resource usage) and executed on a
thread pool. The handler interface is queue-agnostic, so moving to Celery/RQ/Arq later only means
replacing `submit()`.
"""
from __future__ import annotations

import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable

import psutil

from app.db.models import Job
from app.db.session import session_scope
from app.services.tracking import log_activity, record_compute

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="job")
_handlers: dict[str, Callable[["JobContext"], dict]] = {}
# Heavy model work is serialised so two jobs don't fight for the CPU.
heavy_lock = threading.Lock()


def handler(kind: str):
    def deco(fn):
        _handlers[kind] = fn
        return fn
    return deco


class JobContext:
    def __init__(self, job_id: str, project_id: str, params: dict):
        self.job_id, self.project_id, self.params = job_id, project_id, params
        self.steps: list[dict] = []
        self._step_name: str | None = None
        self._step_t = self._step_cpu = 0.0
        self._last_write = 0.0
        self._proc = psutil.Process()
        self.peak_rss = self._proc.memory_info().rss

    def _cpu(self) -> float:
        # Process CPU (all threads) + FFmpeg subprocesses started by this job's thread.
        from app.services.exporter import child_cpu_seconds

        t = self._proc.cpu_times()
        return t.user + t.system + child_cpu_seconds()

    def step(self, name: str) -> None:
        """Start a named step; the previous one is closed and timed."""
        now, cpu = time.perf_counter(), self._cpu()
        if self._step_name:
            self.steps.append({"name": self._step_name, "wall": round(now - self._step_t, 3),
                               "cpu": round(cpu - self._step_cpu, 3)})
        self._step_name, self._step_t, self._step_cpu = name, now, cpu

    def close_steps(self) -> None:
        self.step("")  # flush
        self._step_name = None

    def progress(self, value: float, message: str = "", force: bool = False) -> None:
        self.peak_rss = max(self.peak_rss, self._proc.memory_info().rss)
        now = time.time()
        if not force and now - self._last_write < 0.7:
            return
        self._last_write = now
        with session_scope() as db:
            job = db.get(Job, self.job_id)
            if job:
                job.progress = round(max(0.0, min(1.0, value)), 3)
                if message:
                    job.message = message[:500]


def submit(project_id: str, kind: str, params: dict | None = None) -> str:
    with session_scope() as db:
        job = Job(project_id=project_id, kind=kind, params=params or {}, message="Queued")
        db.add(job)
        db.flush()
        job_id = job.id
        log_activity(db, f"job.{kind}.queued", f"{kind} job queued", project_id, job_id=job_id)
    _executor.submit(_run, job_id)
    return job_id


def _run(job_id: str) -> None:
    with session_scope() as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        job.status, job.started_at, job.message = "running", datetime.now(timezone.utc), "Starting"
        ctx = JobContext(job.id, job.project_id, dict(job.params or {}))
        kind = job.kind
    t0, cpu0 = time.perf_counter(), ctx._cpu()
    status, error, result = "done", "", {}
    try:
        result = _handlers[kind](ctx) or {}
    except Exception as exc:
        status, error = "failed", f"{exc}\n{traceback.format_exc()[-3000:]}"
    ctx.close_steps()
    wall, cpu = time.perf_counter() - t0, ctx._cpu() - cpu0
    with session_scope() as db:
        job = db.get(Job, job_id)
        job.status, job.error, job.result = status, error, result
        job.steps = ctx.steps
        job.progress = 1.0 if status == "done" else job.progress
        job.message = "Done" if status == "done" else f"Failed: {str(error).splitlines()[0][:300]}"
        job.wall_seconds, job.cpu_seconds = round(wall, 3), round(cpu, 3)
        job.peak_rss_mb = round(ctx.peak_rss / 2**20, 1)
        job.finished_at = datetime.now(timezone.utc)
        record_compute(db, job.project_id, job_id, cpu, wall, kind)
        log_activity(db, f"job.{kind}.{status}", f"{kind} job {status} in {wall:.1f}s", job.project_id,
                     job_id=job_id, wall_seconds=round(wall, 2))
