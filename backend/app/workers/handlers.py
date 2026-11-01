"""Job handlers: analyze footage, find shots, render the edit."""
from __future__ import annotations

import json
from pathlib import Path

from app.core.config import settings
from app.db.models import Asset, Export, FinderRun, Project, ShotList
from app.db.session import session_scope
from app.pipeline.analyze import analyze_video, load_arrays
from app.providers.storage import storage
from app.services import exporter
from app.services.finder import FootageFile, build_timeline, find_shots
from app.services.planner import enrich_shots
from app.services.tracking import log_activity, record_llm, record_storage
from app.workers.jobs import JobContext, handler, heavy_lock


def slug(text: str, limit: int = 40) -> str:
    """'Bean & Bloom grand opening' -> 'Bean-and-Bloom-grand-opening' (safe, readable file names)."""
    import re

    text = text.replace("&", " and ")
    words = re.findall(r"[A-Za-z0-9]+", text)
    return "-".join(words)[:limit].strip("-") or "untitled"


def _analyze_asset(ctx: JobContext, asset_id: str, lo: float, hi: float) -> None:
    with session_scope() as db:
        a = db.get(Asset, asset_id)
        key, name = a.storage_key, a.filename
        a.analysis_status = "running"
    try:
        path = storage.local_path(key)
        with heavy_lock:
            summary = analyze_video(asset_id, path, lambda p, m: ctx.progress(lo + (hi - lo) * p, f"{name}: {m}"))
    except Exception:
        with session_scope() as db:
            db.get(Asset, asset_id).analysis_status = "failed"
        raise
    with session_scope() as db:
        a = db.get(Asset, asset_id)
        a.analysis, a.analysis_status = summary, "done"
        a.duration, a.width, a.height = summary["duration"], summary["width"], summary["height"]
        a.fps, a.has_audio = summary["fps"], summary["has_audio"]
        log_activity(db, "asset.analyzed", f"Analysed {name} ({summary['duration']:.0f}s, "
                     f"{len(summary['scenes'])} scenes)", a.project_id, asset_id=asset_id)


@handler("analyze")
def analyze(ctx: JobContext) -> dict:
    ids = ctx.params["asset_ids"]
    for k, asset_id in enumerate(ids):
        ctx.step(f"analyze:{asset_id[:6]}")
        _analyze_asset(ctx, asset_id, k / len(ids), (k + 1) / len(ids))
    with session_scope() as db:
        p = db.get(Project, ctx.project_id)
        if p.status in ("created", "uploading", "analyzing"):
            p.status = "ready"
    return {"analyzed": len(ids)}


def load_footage(project_id: str, ctx: JobContext | None = None, lo: float = 0, hi: float = 0) -> list[FootageFile]:
    """All analysed footage of a project; analyses anything still pending first."""
    with session_scope() as db:
        assets = [(a.id, a.filename, a.analysis_status, dict(a.analysis or {}))
                  for a in db.get(Project, project_id).assets if a.storage_key and not a.filename.startswith("_")]
    pending = [a for a in assets if a[2] != "done" or load_arrays(a[0]) is None]
    for k, (aid, *_rest) in enumerate(pending):
        if ctx:
            ctx.step(f"analyze:{aid[:6]}")
            _analyze_asset(ctx, aid, lo + (hi - lo) * k / len(pending), lo + (hi - lo) * (k + 1) / len(pending))
    if pending:
        with session_scope() as db:
            assets = [(a.id, a.filename, a.analysis_status, dict(a.analysis or {}))
                      for a in db.get(Project, project_id).assets if a.storage_key and not a.filename.startswith("_")]
    out = [FootageFile.load(aid, name, an) for aid, name, _s, an in assets]
    return [f for f in out if f is not None]


@handler("find")
def find(ctx: JobContext) -> dict:
    approach = ctx.params.get("approach", "hybrid")
    with session_scope() as db:
        sl = db.get(ShotList, ctx.params["shot_list_id"])
        shots, sl_id, project_name = list(sl.shots), sl.id, sl.project.name
        sl.project.status = "finding"

    ctx.step("analysis")
    ctx.progress(0.02, "Checking footage analysis", force=True)
    footage = load_footage(ctx.project_id, ctx, 0.02, 0.6)
    if not footage:
        raise ValueError("No footage uploaded for this project")

    ctx.step("search_hints")
    ctx.progress(0.6, "Preparing search hints", force=True)
    shots, llm_res = enrich_shots(shots)
    with session_scope() as db:
        sl = db.get(ShotList, sl_id)
        sl.shots = shots  # keep the hints so future runs are reproducible
        if llm_res:
            record_llm(db, ctx.project_id, ctx.job_id, llm_res.model, llm_res.input_tokens,
                       llm_res.output_tokens, "search_hints")

    ctx.step("shot_search")
    with heavy_lock:
        results = find_shots(shots, footage, approach, lambda p, m: ctx.progress(0.62 + 0.36 * p, m))
    timeline = build_timeline(shots, results)
    with session_scope() as db:
        run = FinderRun(project_id=ctx.project_id, shot_list_id=sl_id, approach=approach,
                        results={"shots": results, "source_files": [f.filename for f in footage]},
                        timeline=timeline)
        db.add(run)
        db.flush()
        run_id = run.id
        db.get(Project, ctx.project_id).status = "review"
        found = sum(r["status"] == "found" for r in results)
        log_activity(db, "run.completed", f"Found {found}/{len(results)} shots ({approach})",
                     ctx.project_id, run_id=run_id, found=found, total=len(results), approach=approach)
    return {"run_id": run_id, "found": found, "total": len(results), "project": project_name}


@handler("render")
def render(ctx: JobContext) -> dict:
    opts = ctx.params.get("options", {})
    with session_scope() as db:
        run = db.get(FinderRun, ctx.params["run_id"])
        clips = list(run.timeline)
        project = run.project
        pname, aspect = project.name, opts.get("aspect") or project.aspect_ratio
        sl = db.get(ShotList, run.shot_list_id)
        cut_label = sl.name if sl else "Cut"
        version = 1 + sum(1 for e in project.exports if e.kind == "mp4")
        files = {a.filename: a.storage_key for a in project.assets}
        music_key = None
        if opts.get("music_asset_id"):
            m = db.get(Asset, opts["music_asset_id"])
            music_key = m.storage_key if m else None
    ctx.step("fetch_sources")
    sources = {name: storage.local_path(key) for name, key in files.items() if any(c["file"] == name for c in clips)}
    music = storage.local_path(music_key) if music_key else None

    ctx.step("render")
    out = settings.work_dir / f"{ctx.job_id}.mp4"
    info = exporter.render_mp4(clips, sources, out, aspect=aspect, crossfade=float(opts.get("crossfade", 0)),
                               title=opts.get("title", ""), title_seconds=float(opts.get("title_seconds", 3)),
                               music=music, music_volume=float(opts.get("music_volume", 0.5)),
                               music_offset=float(opts.get("music_offset", 0)), duck=bool(opts.get("duck", True)),
                               progress=lambda p, m: ctx.progress(0.02 + 0.9 * p, m))
    ctx.step("upload")
    ctx.progress(0.95, "Saving video", force=True)
    from datetime import date

    filename = (f"{slug(pname, 40)}_{slug(cut_label, 30)}_{aspect.replace(':', 'x')}_"
                f"v{version}_{date.today().isoformat()}.mp4")
    key = f"projects/{ctx.project_id}/exports/v{version}_{ctx.job_id[:8]}.mp4"
    storage.put(key, out)
    music_name = None
    if music_key:
        music_name = Path(music_key).name
    with session_scope() as db:
        exp = Export(project_id=ctx.project_id, run_id=ctx.params["run_id"], kind="mp4",
                     filename=filename, storage_key=key, size_bytes=info["size_bytes"],
                     options={**opts, "aspect": aspect, "duration": info["duration"], "version": version,
                              "cut": cut_label, "clips": len(clips), "music_name": music_name})
        db.add(exp)
        db.flush()
        record_storage(db, ctx.project_id, info["size_bytes"], "render")
        log_activity(db, "export.rendered", f"Rendered {info['duration']:.1f}s {aspect} video", ctx.project_id,
                     export_id=exp.id)
        export_id = exp.id
    if storage.name != "local":
        out.unlink(missing_ok=True)
    return {"export_id": export_id, **info}


def results_payload(run_id: str) -> tuple[str, str]:
    """(project name, results JSON in the requested output format)."""
    from app.db.models import Job

    with session_scope() as db:
        run = db.get(FinderRun, run_id)
        p = run.project
        jobs = [j for j in p.jobs if j.status == "done" and j.kind in ("analyze", "find")]
        seconds = round(sum(j.wall_seconds for j in jobs), 1)
        models = sorted({m for a in p.assets for m in (a.analysis or {}).get("models", {}).values() if m})
        sl = db.get(ShotList, run.shot_list_id)
        llm = (sl.meta or {}).get("model")
        processing = {"seconds": seconds, "machine": exporter.machine_info(),
                      "models": models + ([f"{llm} (shot planning / search hints)"] if llm else []),
                      "approach": run.approach, "shot_list": sl.name}
        doc = exporter.results_document(p.name, run.results.get("source_files", []), run.results.get("shots", []),
                                        run.timeline, processing)
        return p.name, doc


__all__ = ["results_payload", "load_footage", "json", "Path"]
