"""Remote analysis worker, e.g. on a free Google Colab T4 GPU.

Runs the exact same analysis code (scenes, quality, CLIP, Whisper) on whatever device is available
and serves it over a small HTTP API, so the main platform can offload its heaviest step.
Asynchronous on purpose: free tunnels cut single requests after ~100 s.

    WORKER_TOKEN=secret uvicorn app.worker:app --port 8765

    GET  /health                 device / GPU / models
    POST /jobs   (file, asset_id) -> {job_id}
    GET  /jobs/{id}              -> {status, progress, message, error}
    GET  /jobs/{id}/result       -> zip(summary.json, arrays.npz)
"""
from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response

from app.pipeline.analyze import analyze_video, cache_path

TOKEN = os.getenv("WORKER_TOKEN", "")
app = FastAPI(title="OnSpotly analysis worker")
_jobs: dict[str, dict] = {}
_lock = threading.Lock()  # one analysis at a time on the GPU


def auth(x_worker_token: str = Header("")) -> None:
    if TOKEN and x_worker_token != TOKEN:
        raise HTTPException(401, "Bad worker token")


def _device_info() -> dict:
    import torch

    cuda = torch.cuda.is_available()
    return {"device": "cuda" if cuda else "cpu", "gpu": torch.cuda.get_device_name(0) if cuda else None}


@app.get("/health", dependencies=[Depends(auth)])
def health():
    from app.core.config import settings

    return {"ok": True, **_device_info(), "clip": settings.clip_model, "whisper": settings.whisper_model,
            "busy": any(j["status"] == "running" for j in _jobs.values())}


def _run(job_id: str, asset_id: str, path: Path) -> None:
    job = _jobs[job_id]
    t0 = time.time()
    try:
        with _lock:
            job["status"] = "running"

            def progress(p: float, m: str) -> None:
                job["progress"], job["message"] = round(p, 3), m

            summary = analyze_video(asset_id, path, progress)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("summary.json", json.dumps(summary))
            z.write(cache_path(asset_id), "arrays.npz")
        job.update(status="done", progress=1.0, message="Analysis complete", result=buf.getvalue(),
                   seconds=round(time.time() - t0, 1))
    except Exception as exc:  # report, don't crash the worker
        job.update(status="failed", error=str(exc)[:2000])
    finally:
        shutil.rmtree(path.parent, ignore_errors=True)


@app.post("/jobs", dependencies=[Depends(auth)])
def submit(file: UploadFile = File(...), asset_id: str = Form(...)):
    tmp = Path(tempfile.mkdtemp())
    path = tmp / Path(file.filename or "video.mp4").name
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    job_id = uuid.uuid4().hex
    _jobs[job_id] = {"status": "queued", "progress": 0.0, "message": "Queued on worker", "error": ""}
    threading.Thread(target=_run, args=(job_id, asset_id, path), daemon=True).start()
    return {"job_id": job_id}


@app.get("/jobs/{job_id}", dependencies=[Depends(auth)])
def status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job")
    return {k: v for k, v in job.items() if k != "result"}


@app.get("/jobs/{job_id}/result", dependencies=[Depends(auth)])
def result(job_id: str):
    job = _jobs.get(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(409, "Result not ready")
    data = job.pop("result")
    job["status"] = "collected"
    return Response(data, media_type="application/zip")
