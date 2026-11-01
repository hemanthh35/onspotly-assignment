"""FastAPI application: API under /api/v1, built web apps served at / and /admin."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import admin, projects
from app.core.config import ROOT_DIR, settings
from app.db.session import init_db
from app.providers.storage import storage
from app.workers import handlers  # noqa: F401  (registers job handlers)

app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(projects.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")


@app.on_event("startup")
def _startup() -> None:
    init_db()
    # Jobs interrupted by a restart can never finish; mark them so the UI doesn't spin forever.
    from app.db.models import Job
    from app.db.session import session_scope

    with session_scope() as db:
        for j in db.query(Job).filter(Job.status.in_(["queued", "running"])):
            j.status, j.message = "failed", "Interrupted by server restart"

    # Warm the CLIP model in the background so the first search doesn't pay ~30 s of loading.
    import threading

    from app.providers.vision import get_clip

    threading.Thread(target=get_clip, daemon=True, name="warm-clip").start()


@app.get("/api/v1/health")
def health():
    return {"ok": True, "database": "supabase" if settings.use_supabase_db else "sqlite",
            "storage": storage.name, "llm": settings.openai_model if settings.use_openai else "rule-based",
            "vision": settings.clip_model, "speech": settings.whisper_model}


def _spa(mount: str, dist: Path) -> None:
    """Serve a built single-page app, falling back to index.html for client-side routes."""
    if not (dist / "index.html").exists():
        return
    app.mount(f"{mount.rstrip('/')}/assets", StaticFiles(directory=dist / "assets"), name=f"{mount}-assets")

    if mount != "/":
        app.add_api_route(mount, lambda: FileResponse(dist / "index.html"), include_in_schema=False)

    @app.get(mount.rstrip("/") + "/{path:path}" if mount != "/" else "/{path:path}", include_in_schema=False)
    def spa(path: str = ""):
        f = dist / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(dist / "index.html")


_spa("/admin", ROOT_DIR / "admin" / "dist")
_spa("/", ROOT_DIR / "frontend" / "dist")
