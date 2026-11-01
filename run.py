"""One-command launcher: builds the web apps if needed, then serves everything on :8000.

    python run.py            # app at http://localhost:8000, admin at http://localhost:8000/admin
    python run.py --rebuild  # force a rebuild of the web apps
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APPS = [ROOT / "frontend", ROOT / "admin"]


def build(app: Path, force: bool) -> None:
    if not (app / "package.json").exists():
        return
    if (app / "dist" / "index.html").exists() and not force:
        return
    npm = shutil.which("npm")
    if not npm:
        print(f"[run] npm not found: skipping build of {app.name} (install Node.js 20+)")
        return
    print(f"[run] building {app.name} ...")
    if not (app / "node_modules").exists():
        subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=app, check=True)
    subprocess.run([npm, "run", "build"], cwd=app, check=True)


def main() -> None:
    force = "--rebuild" in sys.argv
    for app in APPS:
        build(app, force)
    port = sys.argv[sys.argv.index("--port") + 1] if "--port" in sys.argv else os.getenv("PORT", "8000")
    print(f"[run] OnSpotly Studio  ->  http://localhost:{port}   (admin: http://localhost:{port}/admin)")
    os.chdir(ROOT / "backend")
    sys.path.insert(0, str(ROOT / "backend"))
    import uvicorn

    uvicorn.run("app.main:app", host=os.getenv("HOST", "127.0.0.1"), port=int(port), log_level="info")


if __name__ == "__main__":
    main()
