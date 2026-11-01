"""Admin analytics: platform KPIs, processing statistics, activity and cost analysis."""
from __future__ import annotations

import hashlib
import hmac
import shutil
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import numpy as np
import psutil
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import ActivityEvent, Asset, CostRecord, Export, FinderRun, Job, Project
from app.db.session import get_db
from app.providers.storage import storage

router = APIRouter(prefix="/admin")
TOKEN_TTL = 12 * 3600


def _sign(expires: int) -> str:
    return hmac.new(settings.secret_key.encode(), f"admin:{expires}".encode(), hashlib.sha256).hexdigest()


def require_admin(authorization: str = Header("")) -> None:
    if not settings.admin_password:
        return  # no password configured: local development mode
    try:
        expires, sig = authorization.removeprefix("Bearer ").split(".", 1)
        if int(expires) < time.time() or not hmac.compare_digest(sig, _sign(int(expires))):
            raise ValueError
    except Exception:
        raise HTTPException(401, "Admin login required")


class LoginIn(BaseModel):
    password: str


@router.post("/login")
def login(body: LoginIn):
    if settings.admin_password and not hmac.compare_digest(body.password, settings.admin_password):
        raise HTTPException(401, "Wrong password")
    expires = int(time.time()) + TOKEN_TTL
    return {"token": f"{expires}.{_sign(expires)}", "expires": expires,
            "auth_required": bool(settings.admin_password)}


def _utc(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


@router.get("/dashboard", dependencies=[Depends(require_admin)])
def dashboard(days: int = 30, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    projects = list(db.scalars(select(Project)))
    assets = [a for a in db.scalars(select(Asset))]
    videos = [a for a in assets if not a.filename.startswith("_")]
    jobs = list(db.scalars(select(Job)))
    costs = list(db.scalars(select(CostRecord)))
    runs = list(db.scalars(select(FinderRun)))
    exports = list(db.scalars(select(Export)))
    events = list(db.scalars(select(ActivityEvent).order_by(ActivityEvent.created_at.desc()).limit(5000)))
    names = {p.id: p.name for p in projects}

    # ---------------- KPIs
    done = [j for j in jobs if j.status == "done"]
    failed = [j for j in jobs if j.status == "failed"]
    total_cost = sum(c.amount_usd for c in costs)
    renders = [e for e in exports if e.kind == "mp4"]
    processed_projects = {r.project_id for r in runs}
    analyze_jobs = [j for j in done if j.kind == "analyze"]
    footage_s = sum(a.duration for a in videos)
    an_wall = sum(j.wall_seconds for j in analyze_jobs)
    kpis = {
        "projects": len(projects), "videos_uploaded": len(videos),
        "videos_analyzed": sum(a.analysis_status == "done" for a in videos),
        "footage_minutes": round(footage_s / 60, 1), "finder_runs": len(runs), "renders": len(renders),
        "jobs_total": len(jobs), "jobs_failed": len(failed),
        "success_rate": round(len(done) / max(1, len(done) + len(failed)), 3),
        "total_cost_usd": round(total_cost, 4),
        "avg_cost_per_project_usd": round(total_cost / max(1, len(processed_projects)), 4),
        "avg_processing_seconds": round(np.mean([j.wall_seconds for j in done]) if done else 0, 1),
        "processing_speed_x": round(footage_s / an_wall, 2) if an_wall else 0,  # footage seconds per wall second
        "storage_bytes": sum(a.size_bytes for a in assets) + sum(e.size_bytes for e in renders),
        "downloads": sum(e.downloads for e in exports),
    }

    # ---------------- cost analysis
    by_cat = defaultdict(float)
    for c in costs:
        by_cat[c.category] += c.amount_usd
    per_project = []
    for p in projects:
        pc = [c for c in costs if c.project_id == p.id]
        pj = [j for j in jobs if j.project_id == p.id and j.status == "done"]
        cat = defaultdict(float)
        for c in pc:
            cat[c.category] += c.amount_usd
        tokens = sum(c.quantity for c in pc if c.category == "llm")
        fs = sum(a.duration for a in p.assets if not a.filename.startswith("_"))
        total = sum(cat.values())
        per_project.append({
            "project_id": p.id, "name": p.name, "status": p.status, "created_at": p.created_at,
            "footage_seconds": round(fs, 1), "videos": sum(1 for a in p.assets if not a.filename.startswith("_")),
            "processing_seconds": round(sum(j.wall_seconds for j in pj), 1),
            "cpu_seconds": round(sum(j.cpu_seconds for j in pj), 1),
            "peak_ram_mb": round(max([j.peak_rss_mb for j in pj] or [0]), 0),
            "llm_tokens": int(tokens), "storage_mb": round(sum(a.size_bytes for a in p.assets) / 2**20 +
                                                           sum(e.size_bytes for e in p.exports if e.kind == "mp4") / 2**20, 1),
            "renders": sum(1 for e in p.exports if e.kind == "mp4"),
            "compute_usd": round(cat["compute"], 5), "llm_usd": round(cat["llm"], 5),
            "storage_usd": round(cat["storage"], 5), "egress_usd": round(cat["egress"], 5),
            "total_usd": round(total, 5),
            "usd_per_footage_minute": round(total / (fs / 60), 5) if fs else 0,
        })
    per_project.sort(key=lambda r: r["created_at"], reverse=True)

    # ---------------- time series (daily)
    day_keys = [(since + timedelta(days=i + 1)).date().isoformat() for i in range(days)]
    daily = {d: {"date": d, "jobs": 0, "failed": 0, "compute": 0.0, "llm": 0.0, "storage": 0.0, "egress": 0.0,
                 "processing_seconds": 0.0, "uploads": 0, "renders": 0} for d in day_keys}
    for j in jobs:
        d = _utc(j.created_at).date().isoformat()
        if d in daily:
            daily[d]["jobs"] += 1
            daily[d]["failed"] += j.status == "failed"
            daily[d]["processing_seconds"] += j.wall_seconds
    for c in costs:
        d = _utc(c.created_at).date().isoformat()
        if d in daily:
            daily[d][c.category] += c.amount_usd
    for a in videos:
        d = _utc(a.created_at).date().isoformat()
        if d in daily:
            daily[d]["uploads"] += 1
    for e in renders:
        d = _utc(e.created_at).date().isoformat()
        if d in daily:
            daily[d]["renders"] += 1
    series = [{**v, **{k: round(v[k], 6) for k in ("compute", "llm", "storage", "egress")},
               "processing_seconds": round(v["processing_seconds"], 1)} for v in daily.values()]

    # ---------------- processing statistics
    by_kind = {}
    for kind in ("analyze", "find", "render"):
        ks = [j for j in jobs if j.kind == kind]
        walls = [j.wall_seconds for j in ks if j.status == "done"]
        by_kind[kind] = {"count": len(ks), "failed": sum(j.status == "failed" for j in ks),
                         "avg_seconds": round(float(np.mean(walls)), 2) if walls else 0,
                         "p95_seconds": round(float(np.percentile(walls, 95)), 2) if walls else 0,
                         "avg_cpu_seconds": round(float(np.mean([j.cpu_seconds for j in ks if j.status == "done"])), 2) if walls else 0,
                         "avg_peak_ram_mb": round(float(np.mean([j.peak_rss_mb for j in ks if j.status == "done"])), 0) if walls else 0}
    step_totals = defaultdict(float)
    for j in done:
        for s in j.steps or []:
            if s.get("name"):
                step_totals[s["name"].split(":")[0]] += s.get("wall", 0)
    steps = sorted(({"step": k, "seconds": round(v, 1)} for k, v in step_totals.items()), key=lambda x: -x["seconds"])
    # Processing time vs footage length (one point per analysed video).
    scatter = []
    for j in analyze_jobs:
        ids = j.params.get("asset_ids", [])
        dur = sum(a.duration for a in videos if a.id in ids)
        if dur:
            scatter.append({"footage_seconds": round(dur, 1), "processing_seconds": round(j.wall_seconds, 1),
                            "project": names.get(j.project_id, "")})

    # ---------------- finder quality
    conf, qual, found, missing = [], [], 0, 0
    for r in runs:
        for s in r.results.get("shots", []):
            if s["status"] == "found" and s.get("best"):
                found += 1
                conf.append(s["best"]["confidence"])
                qual.append(s["best"].get("quality", {}).get("overall", 0))
            else:
                missing += 1
    hist = lambda vals: [{"bucket": f"{b / 10:.1f}", "count": int(sum(1 for v in vals if b / 10 <= v < (b + 1) / 10 or (b == 9 and v == 1)))}
                         for b in range(10)]
    finder = {"found": found, "missing": missing, "confidence_hist": hist(conf), "quality_hist": hist(qual),
              "avg_confidence": round(float(np.mean(conf)), 3) if conf else 0,
              "approaches": dict(Counter(r.approach for r in runs))}

    # ---------------- activity heatmap (weekday x hour) and feed
    heat = [[0] * 24 for _ in range(7)]
    for e in events:
        t = _utc(e.created_at).astimezone()  # server local time
        heat[t.weekday()][t.hour] += 1
    types = Counter(e.type.split(".")[0] for e in events if _utc(e.created_at) >= since)
    feed = [{"id": e.id, "type": e.type, "message": e.message, "project": names.get(e.project_id or "", ""),
             "project_id": e.project_id, "created_at": e.created_at} for e in events[:60]]
    recent_jobs = [{"id": j.id, "kind": j.kind, "status": j.status, "project": names.get(j.project_id, ""),
                    "wall_seconds": j.wall_seconds, "cpu_seconds": j.cpu_seconds, "peak_rss_mb": j.peak_rss_mb,
                    "progress": j.progress, "message": j.message, "created_at": j.created_at}
                   for j in sorted(jobs, key=lambda j: j.created_at, reverse=True)[:25]]

    # ---------------- system & config
    disk = shutil.disk_usage(settings.data_dir)
    vm = psutil.virtual_memory()
    system = {"cpu_percent": psutil.cpu_percent(interval=0.2), "ram_used_gb": round(vm.used / 2**30, 1),
              "ram_total_gb": round(vm.total / 2**30, 1), "disk_free_gb": round(disk.free / 2**30, 1),
              "cpu_count": psutil.cpu_count(), "running_jobs": sum(j.status == "running" for j in jobs),
              "queued_jobs": sum(j.status == "queued" for j in jobs)}
    p = settings.pricing
    config = {"database": "Supabase Postgres" if settings.use_supabase_db else "SQLite (local)",
              "storage": "Supabase Storage" if storage.name == "supabase" else "Local disk",
              "llm": settings.openai_model if settings.use_openai else "rule-based",
              "vision": f"{settings.clip_model} / {settings.clip_pretrained}", "speech": settings.whisper_model,
              "pricing": {"vcpu_hour": p.vcpu_hour, "storage_gb_month": p.storage_gb_month, "egress_gb": p.egress_gb,
                          "llm_input_per_m": p.llm_input_per_m, "llm_output_per_m": p.llm_output_per_m}}

    return {"generated_at": now, "kpis": kpis, "cost_by_category": {k: round(v, 6) for k, v in by_cat.items()},
            "projects": per_project, "series": series, "processing": {"by_kind": by_kind, "steps": steps,
                                                                       "scatter": scatter},
            "finder": finder, "heatmap": heat, "activity_types": dict(types), "activity": feed,
            "recent_jobs": recent_jobs, "system": system, "config": config}
