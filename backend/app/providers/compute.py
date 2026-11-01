"""Where video analysis runs: this machine's CPU, or a remote GPU worker (e.g. Google Colab).

The remote worker (app/worker.py) runs the same analysis code and returns the same outputs, so
everything downstream is identical whichever compute was used.
"""
from __future__ import annotations

import io
import json
import time
import zipfile
from pathlib import Path
from typing import Callable

import requests

from app.db.models import AppSetting
from app.db.session import session_scope
from app.pipeline.analyze import cache_path

KEY = "compute"
DEFAULT = {"mode": "local", "remote_url": "", "remote_token": "", "fallback_to_local": True}


def get_compute() -> dict:
    with session_scope() as db:
        row = db.get(AppSetting, KEY)
        return {**DEFAULT, **(row.value if row else {})}


def set_compute(value: dict) -> dict:
    merged = {**get_compute(), **value}
    merged["remote_url"] = merged["remote_url"].strip().rstrip("/")
    with session_scope() as db:
        row = db.get(AppSetting, KEY)
        if row:
            row.value = merged
        else:
            db.add(AppSetting(key=KEY, value=merged))
    return merged


def _headers(cfg: dict) -> dict:
    return {"X-Worker-Token": cfg.get("remote_token", "")}


def test_remote(cfg: dict) -> dict:
    """Ping the worker; returns its device info or raises with a readable message."""
    if not cfg.get("remote_url"):
        raise ValueError("Paste the worker URL from the Colab notebook first")
    try:
        r = requests.get(f"{cfg['remote_url']}/health", headers=_headers(cfg), timeout=15)
    except requests.RequestException as exc:
        raise ValueError(f"Worker not reachable: {exc.__class__.__name__}. Is the Colab notebook still running?")
    if r.status_code == 401:
        raise ValueError("Worker rejected the token. Copy it again from the notebook")
    r.raise_for_status()
    return r.json()


def analyze_remote(cfg: dict, asset_id: str, path: Path, progress: Callable[[float, str], None]) -> dict:
    """Upload a video to the worker, follow its progress, download summary + arrays into the cache."""
    base, h = cfg["remote_url"], _headers(cfg)
    progress(0.01, "Uploading to Colab GPU")
    with open(path, "rb") as f:
        r = requests.post(f"{base}/jobs", headers=h, files={"file": (path.name, f, "video/mp4")},
                          data={"asset_id": asset_id}, timeout=600)
    r.raise_for_status()
    job_id = r.json()["job_id"]
    deadline = time.time() + 3600
    while time.time() < deadline:
        s = requests.get(f"{base}/jobs/{job_id}", headers=h, timeout=30).json()
        if s["status"] == "failed":
            raise RuntimeError(f"Worker failed: {s.get('error')}")
        if s["status"] == "done":
            break
        progress(0.05 + 0.9 * float(s.get("progress", 0)), f"Colab GPU: {s.get('message', '')}")
        time.sleep(1.5)
    else:
        raise TimeoutError("Worker took longer than an hour")
    progress(0.96, "Downloading results from Colab")
    z = zipfile.ZipFile(io.BytesIO(requests.get(f"{base}/jobs/{job_id}/result", headers=h, timeout=300).content))
    cache_path(asset_id).write_bytes(z.read("arrays.npz"))
    return json.loads(z.read("summary.json"))
