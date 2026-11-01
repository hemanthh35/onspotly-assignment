"""Projects, footage uploads, shot lists, finder runs and exports."""
from __future__ import annotations

import csv
import io
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

import cv2
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Asset, Export, FinderRun, Job, Project, ShotList
from app.db.session import get_db
from app.providers.storage import storage
from app.services import exporter
from app.services.planner import plan_shots
from app.services.tracking import log_activity, record_egress, record_llm, record_storage
from app.workers import jobs
from app.workers.handlers import results_payload

router = APIRouter()

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}


# ---------------------------------------------------------------- serializers
def _asset(a: Asset) -> dict:
    an = a.analysis or {}
    return {"id": a.id, "filename": a.filename, "size_bytes": a.size_bytes, "duration": a.duration,
            "width": a.width, "height": a.height, "fps": a.fps, "has_audio": a.has_audio,
            "analysis_status": a.analysis_status, "scenes": an.get("scenes", []),
            "transcript": an.get("transcript", {}).get("segments", []),
            "kind": "music" if a.filename.startswith("_music") else "video", "created_at": a.created_at}


def _job(j: Job) -> dict:
    return {"id": j.id, "kind": j.kind, "status": j.status, "progress": j.progress, "message": j.message,
            "error": j.error.splitlines()[0] if j.error else "", "result": j.result, "params": j.params,
            "steps": j.steps, "wall_seconds": j.wall_seconds, "cpu_seconds": j.cpu_seconds,
            "peak_rss_mb": j.peak_rss_mb, "created_at": j.created_at, "finished_at": j.finished_at}


def _shot_list(s: ShotList) -> dict:
    return {"id": s.id, "name": s.name, "source": s.source, "shots": s.shots, "meta": s.meta,
            "total_seconds": round(sum(float(x.get("target_seconds", 0)) for x in s.shots), 2),
            "created_at": s.created_at, "updated_at": s.updated_at}


def _run(r: FinderRun) -> dict:
    return {"id": r.id, "shot_list_id": r.shot_list_id, "approach": r.approach, "results": r.results,
            "timeline": r.timeline, "created_at": r.created_at, "updated_at": r.updated_at}


def _export(e: Export) -> dict:
    return {"id": e.id, "run_id": e.run_id, "kind": e.kind, "filename": e.filename, "size_bytes": e.size_bytes,
            "options": e.options, "downloads": e.downloads, "created_at": e.created_at}


def _project(p: Project, full: bool = False) -> dict:
    d = {"id": p.id, "name": p.name, "brief": p.brief, "target_seconds": p.target_seconds,
         "aspect_ratio": p.aspect_ratio, "status": p.status, "created_at": p.created_at,
         "updated_at": p.updated_at, "asset_count": sum(1 for a in p.assets if not a.filename.startswith("_")),
         "footage_seconds": round(sum(a.duration for a in p.assets if not a.filename.startswith("_")), 1)}
    if full:
        d["assets"] = [_asset(a) for a in sorted(p.assets, key=lambda a: a.filename)]
        d["shot_lists"] = [_shot_list(s) for s in sorted(p.shot_lists, key=lambda s: s.created_at)]
        d["runs"] = [_run(r) for r in sorted(p.runs, key=lambda r: r.created_at)]
        d["jobs"] = [_job(j) for j in sorted(p.jobs, key=lambda j: j.created_at, reverse=True)[:20]]
        d["exports"] = [_export(e) for e in sorted(p.exports, key=lambda e: e.created_at, reverse=True)]
    return d


def _get(db: Session, model, id_: str):
    obj = db.get(model, id_)
    if obj is None:
        raise HTTPException(404, f"{model.__name__} not found")
    return obj


# ---------------------------------------------------------------- projects
class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    brief: str = ""
    target_seconds: float = Field(30, ge=5, le=300)
    aspect_ratio: str = "9:16"


class ProjectPatch(BaseModel):
    name: str | None = None
    brief: str | None = None
    target_seconds: float | None = Field(None, ge=5, le=300)
    aspect_ratio: str | None = None


@router.get("/projects")
def list_projects(db: Session = Depends(get_db)):
    return [_project(p) for p in db.scalars(select(Project).order_by(Project.created_at.desc()))]


@router.post("/projects")
def create_project(body: ProjectIn, db: Session = Depends(get_db)):
    p = Project(**body.model_dump())
    db.add(p)
    db.flush()
    log_activity(db, "project.created", f"Project “{p.name}” created", p.id)
    db.commit()
    return _project(p, full=True)


@router.get("/projects/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)):
    return _project(_get(db, Project, project_id), full=True)


@router.patch("/projects/{project_id}")
def update_project(project_id: str, body: ProjectPatch, db: Session = Depends(get_db)):
    p = _get(db, Project, project_id)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    db.commit()
    return _project(p, full=True)


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)):
    p = _get(db, Project, project_id)
    for a in p.assets:
        storage.delete(a.storage_key)
    for e in p.exports:
        storage.delete(e.storage_key)
    log_activity(db, "project.deleted", f"Project “{p.name}” deleted", None)
    db.delete(p)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- uploads
def _store_file(db: Session, project: Project, src: Path, filename: str) -> Asset:
    from app.pipeline.analyze import probe

    key = f"projects/{project.id}/footage/{filename}"
    storage.put(key, src)
    size = src.stat().st_size
    a = Asset(project_id=project.id, filename=filename, storage_key=key, size_bytes=size)
    try:
        meta = probe(src)
        a.duration, a.width, a.height, a.fps, a.has_audio = (meta["duration"], meta["width"], meta["height"],
                                                             meta["fps"], meta["has_audio"])
    except Exception:
        pass
    db.add(a)
    db.flush()
    record_storage(db, project.id, size, "footage")
    return a


@router.post("/projects/{project_id}/assets")
def upload_footage(project_id: str, files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    """Upload videos and/or zip archives of videos. Analysis starts automatically."""
    p = _get(db, Project, project_id)
    existing = {a.filename for a in p.assets}
    created: list[Asset] = []
    skipped: list[str] = []
    with tempfile.TemporaryDirectory(dir=settings.work_dir) as tmp:
        tmpdir = Path(tmp)
        for up in files:
            name = Path(up.filename or "upload").name
            dest = tmpdir / name
            with open(dest, "wb") as f:
                shutil.copyfileobj(up.file, f)
            candidates: list[tuple[Path, str]] = []
            if dest.suffix.lower() == ".zip":
                with zipfile.ZipFile(dest) as z:
                    for info in z.infolist():
                        inner = Path(info.filename)
                        if info.is_dir() or inner.suffix.lower() not in VIDEO_EXT or "__MACOSX" in inner.parts:
                            continue
                        out = tmpdir / "unzipped" / inner.name  # flatten; never trust archive paths
                        out.parent.mkdir(exist_ok=True)
                        with z.open(info) as zsrc, open(out, "wb") as zdst:
                            shutil.copyfileobj(zsrc, zdst)
                        candidates.append((out, inner.name))
            elif dest.suffix.lower() in VIDEO_EXT:
                candidates.append((dest, name))
            else:
                skipped.append(name)
            for path, fname in candidates:
                if fname in existing:
                    skipped.append(f"{fname} (already uploaded)")
                    continue
                created.append(_store_file(db, p, path, fname))
                existing.add(fname)
    if not created:
        db.commit()
        raise HTTPException(400, f"No new video files found. Skipped: {', '.join(skipped) or 'none'}")
    p.status = "analyzing"
    log_activity(db, "assets.uploaded", f"Uploaded {len(created)} video(s)", p.id,
                 files=[a.filename for a in created], bytes=sum(a.size_bytes for a in created))
    db.commit()
    job_id = jobs.submit(p.id, "analyze", {"asset_ids": [a.id for a in created]})
    return {"assets": [_asset(a) for a in created], "skipped": skipped, "job_id": job_id}


@router.post("/projects/{project_id}/music")
def upload_music(project_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    p = _get(db, Project, project_id)
    ext = Path(file.filename or "music.mp3").suffix.lower()
    if ext not in AUDIO_EXT:
        raise HTTPException(400, "Upload an audio file (mp3, wav, m4a, aac, ogg)")
    with tempfile.TemporaryDirectory(dir=settings.work_dir) as tmp:
        dest = Path(tmp) / f"music{ext}"
        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)
        key = f"projects/{p.id}/music/{Path(file.filename).name}"
        storage.put(key, dest)
        a = Asset(project_id=p.id, filename=f"_music_{Path(file.filename).name}", storage_key=key,
                  size_bytes=dest.stat().st_size, analysis_status="skip")
        db.add(a)
        db.flush()
        record_storage(db, p.id, a.size_bytes, "music")
    db.commit()
    return _asset(a)


@router.delete("/assets/{asset_id}")
def delete_asset(asset_id: str, db: Session = Depends(get_db)):
    a = _get(db, Asset, asset_id)
    storage.delete(a.storage_key)
    db.delete(a)
    db.commit()
    return {"ok": True}


@router.post("/projects/{project_id}/analyze")
def reanalyze(project_id: str, db: Session = Depends(get_db)):
    p = _get(db, Project, project_id)
    ids = [a.id for a in p.assets if not a.filename.startswith("_")]
    return {"job_id": jobs.submit(p.id, "analyze", {"asset_ids": ids})}


@router.get("/assets/{asset_id}/stream")
def stream_asset(asset_id: str, db: Session = Depends(get_db)):
    """Video preview (Starlette's FileResponse supports HTTP range requests for seeking)."""
    a = _get(db, Asset, asset_id)
    return FileResponse(storage.local_path(a.storage_key), media_type="video/mp4")


@router.get("/assets/{asset_id}/thumb")
def thumbnail(asset_id: str, t: float = 0.0, w: int = 480, db: Session = Depends(get_db)):
    a = _get(db, Asset, asset_id)
    cache = settings.cache_dir / "thumbs" / f"{asset_id}_{t:.1f}_{w}.jpg"
    if not cache.exists():
        cap = cv2.VideoCapture(str(storage.local_path(a.storage_key)))
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            raise HTTPException(404, "Frame not available")
        h, wd = frame.shape[:2]
        frame = cv2.resize(frame, (w, int(w * h / wd)), interpolation=cv2.INTER_AREA)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(cache), frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
    return FileResponse(cache, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


# ---------------------------------------------------------------- shot lists
class ShotIn(BaseModel):
    shot_id: str
    name: str
    description: str = ""
    target_seconds: float = Field(3, gt=0, le=60)
    order: int = 0
    needs_audio: bool = False
    visual_queries: list[str] = []
    negative_queries: list[str] = []
    audio_keywords: list[str] = []
    brief_quote: str = ""
    grounded: bool | None = None


class ShotListIn(BaseModel):
    name: str = "Shot list"
    source: str = "manual"
    shots: list[ShotIn]


@router.post("/projects/{project_id}/shot-lists/plan")
def plan(project_id: str, db: Session = Depends(get_db)):
    """AI shot planner: the project's brief -> a new editable shot list."""
    p = _get(db, Project, project_id)
    if not p.brief.strip():
        raise HTTPException(400, "Write a brief first")
    result, llm = plan_shots(p.brief, p.target_seconds)
    label = "AI shot list" if result["source"] == "ai" else "Rule-based shot list"
    sl = ShotList(project_id=p.id, name=label, source=result["source"], shots=result["shots"],
                  meta={"model": result["model"], "style": result.get("style", "")})
    db.add(sl)
    db.flush()
    if llm:
        record_llm(db, p.id, None, llm.model, llm.input_tokens, llm.output_tokens, "shot_planning")
    log_activity(db, "shotlist.planned", f"{label} with {len(sl.shots)} shots ({result['model']})", p.id,
                 shot_list_id=sl.id, model=result["model"])
    db.commit()
    return _shot_list(sl)


@router.post("/projects/{project_id}/shot-lists")
def create_shot_list(project_id: str, body: ShotListIn, db: Session = Depends(get_db)):
    p = _get(db, Project, project_id)
    sl = ShotList(project_id=p.id, name=body.name, source=body.source, shots=[s.model_dump() for s in body.shots])
    db.add(sl)
    db.flush()
    log_activity(db, "shotlist.created", f"Shot list “{sl.name}” added", p.id, shot_list_id=sl.id)
    db.commit()
    return _shot_list(sl)


def _parse_shot_file(name: str, raw: bytes) -> list[dict]:
    text = raw.decode("utf-8-sig")
    if name.lower().endswith(".json"):
        data = json.loads(text)
        shots = data.get("shots", data) if isinstance(data, dict) else data
    else:
        shots = list(csv.DictReader(io.StringIO(text)))
    out = []
    for i, s in enumerate(shots, start=1):
        na = s.get("needs_audio", False)
        out.append({"shot_id": str(s.get("shot_id") or f"S{i}"), "name": s.get("name", f"Shot {i}"),
                    "description": s.get("description", ""), "target_seconds": float(s.get("target_seconds") or 3),
                    "order": int(s.get("order") or i),
                    "needs_audio": na if isinstance(na, bool) else str(na).lower() in ("1", "true", "yes"),
                    "visual_queries": s.get("visual_queries") or [], "negative_queries": s.get("negative_queries") or [],
                    "audio_keywords": s.get("audio_keywords") or []})
    return out


@router.post("/projects/{project_id}/shot-lists/import")
def import_shot_list(project_id: str, file: UploadFile = File(...), name: str = Form("Imported shot list"),
                     db: Session = Depends(get_db)):
    """Load any shot list (JSON or CSV), e.g. OnSpotly's reference list."""
    p = _get(db, Project, project_id)
    try:
        shots = _parse_shot_file(file.filename or "", file.file.read())
    except Exception as exc:
        raise HTTPException(400, f"Could not read shot list: {exc}")
    sl = ShotList(project_id=p.id, name=name, source="reference", shots=shots)
    db.add(sl)
    db.flush()
    log_activity(db, "shotlist.imported", f"Imported “{name}” ({len(shots)} shots)", p.id, shot_list_id=sl.id)
    db.commit()
    return _shot_list(sl)


@router.put("/shot-lists/{shot_list_id}")
def update_shot_list(shot_list_id: str, body: ShotListIn, db: Session = Depends(get_db)):
    sl = _get(db, ShotList, shot_list_id)
    old = {s["shot_id"]: s for s in sl.shots}
    shots = []
    for i, s in enumerate(body.shots, start=1):
        d = s.model_dump()
        d["order"] = i
        prev = old.get(d["shot_id"])
        # Text edited -> old search hints no longer describe the shot; regenerate them on next search.
        if prev and (prev.get("name"), prev.get("description")) != (d["name"], d["description"]) \
                and d["visual_queries"] == prev.get("visual_queries", []):
            d["visual_queries"], d["negative_queries"] = [], []
            if d["needs_audio"]:
                d["audio_keywords"] = []
        shots.append(d)
    sl.name, sl.shots = body.name, shots
    db.commit()
    return _shot_list(sl)


@router.delete("/shot-lists/{shot_list_id}")
def delete_shot_list(shot_list_id: str, db: Session = Depends(get_db)):
    db.delete(_get(db, ShotList, shot_list_id))
    db.commit()
    return {"ok": True}


class FindIn(BaseModel):
    approach: str = "hybrid"


@router.post("/shot-lists/{shot_list_id}/find")
def start_find(shot_list_id: str, body: FindIn, db: Session = Depends(get_db)):
    sl = _get(db, ShotList, shot_list_id)
    if body.approach not in ("hybrid", "baseline"):
        raise HTTPException(400, "approach must be hybrid or baseline")
    return {"job_id": jobs.submit(sl.project_id, "find", {"shot_list_id": sl.id, "approach": body.approach})}


# ---------------------------------------------------------------- runs & exports
class TimelineItem(BaseModel):
    shot_id: str
    name: str = ""
    file: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    needs_audio: bool = False


class TimelineIn(BaseModel):
    timeline: list[TimelineItem]


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)):
    return _run(_get(db, FinderRun, run_id))


@router.put("/runs/{run_id}/timeline")
def update_timeline(run_id: str, body: TimelineIn, db: Session = Depends(get_db)):
    """The editor's working cut: order, trims and swapped alternatives."""
    run = _get(db, FinderRun, run_id)
    tl = []
    for i, c in enumerate(body.timeline, start=1):
        if c.end <= c.start:
            raise HTTPException(400, f"{c.shot_id}: end must be after start")
        tl.append({"order": i, **c.model_dump()})
    run.timeline = tl
    db.commit()
    return _run(run)


class RenderIn(BaseModel):
    aspect: str | None = None
    crossfade: float = Field(0.0, ge=0, le=1.0)
    title: str = ""
    music_asset_id: str | None = None
    music_volume: float = Field(0.5, ge=0, le=1.5)


@router.post("/runs/{run_id}/render")
def start_render(run_id: str, body: RenderIn, db: Session = Depends(get_db)):
    run = _get(db, FinderRun, run_id)
    if not run.timeline:
        raise HTTPException(400, "The timeline is empty")
    return {"job_id": jobs.submit(run.project_id, "render", {"run_id": run.id, "options": body.model_dump()})}


def _sources(run: FinderRun) -> dict[str, Path]:
    return {a.filename: storage.local_path(a.storage_key) for a in run.project.assets
            if any(c["file"] == a.filename for c in run.timeline)}


@router.get("/runs/{run_id}/download/{kind}")
def download_run_file(run_id: str, kind: str, db: Session = Depends(get_db)):
    """Editor files generated from the current timeline: json, csv, edl, fcpxml, results."""
    run = _get(db, FinderRun, run_id)
    p = run.project
    safe = "".join(ch if ch.isalnum() else "_" for ch in p.name).strip("_")[:40] or "project"
    aspect = p.aspect_ratio
    if kind == "json":
        body, mime, fname = exporter.clip_list_json(p.name, run.timeline, aspect), "application/json", f"{safe}_clips.json"
    elif kind == "csv":
        body, mime, fname = exporter.clip_list_csv(run.timeline), "text/csv", f"{safe}_clips.csv"
    elif kind == "edl":
        body, mime, fname = exporter.edl(p.name, run.timeline), "text/plain", f"{safe}.edl"
    elif kind == "fcpxml":
        durs = {a.filename: a.duration for a in p.assets}
        body, mime, fname = (exporter.fcpxml(p.name, run.timeline, _sources(run), durs),
                             "application/xml", f"{safe}.fcpxml")
    elif kind == "results":
        _, body = results_payload(run_id)
        mime, fname = "application/json", f"{safe}_shot_finder_results.json"
    else:
        raise HTTPException(404, "Unknown export kind")
    data = body.encode("utf-8")
    db.add(Export(project_id=p.id, run_id=run.id, kind=kind, filename=fname, storage_key="", size_bytes=len(data),
                  downloads=1))
    record_egress(db, p.id, len(data), kind)
    log_activity(db, "export.downloaded", f"Downloaded {kind.upper()} ({fname})", p.id, kind=kind)
    db.commit()
    return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/exports/{export_id}/download")
def download_export(export_id: str, inline: bool = False, db: Session = Depends(get_db)):
    e = _get(db, Export, export_id)
    if not e.storage_key:
        raise HTTPException(404, "This export is generated on demand")
    path = storage.local_path(e.storage_key)
    if not inline:
        e.downloads += 1
        record_egress(db, e.project_id, e.size_bytes, e.kind)
        log_activity(db, "export.downloaded", f"Downloaded video ({e.filename})", e.project_id, kind=e.kind)
        db.commit()
    return FileResponse(path, media_type="video/mp4", filename=None if inline else e.filename)


# ---------------------------------------------------------------- jobs
@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    return _job(_get(db, Job, job_id))
