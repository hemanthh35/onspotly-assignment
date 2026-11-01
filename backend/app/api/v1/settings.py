"""Platform settings: where video analysis runs (local CPU or a remote GPU worker such as Colab)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.providers.compute import get_compute, set_compute, test_remote

router = APIRouter(prefix="/settings")


def _public(cfg: dict) -> dict:
    tok = cfg.get("remote_token", "")
    return {**cfg, "remote_token": "", "has_token": bool(tok),
            "token_hint": f"…{tok[-4:]}" if len(tok) >= 4 else ""}


class ComputeIn(BaseModel):
    mode: str = "local"  # local | remote
    remote_url: str = ""
    remote_token: str | None = None  # None/empty = keep the saved token
    fallback_to_local: bool = True


@router.get("/compute")
def read_compute():
    return _public(get_compute())


@router.put("/compute")
def write_compute(body: ComputeIn):
    if body.mode not in ("local", "remote"):
        raise HTTPException(400, "mode must be local or remote")
    data = body.model_dump()
    if not data["remote_token"]:
        data.pop("remote_token")
    if body.mode == "remote" and not body.remote_url.strip():
        raise HTTPException(400, "Paste the worker URL from the Colab notebook")
    return _public(set_compute(data))


@router.post("/compute/test")
def test_compute(body: ComputeIn):
    cfg = {**get_compute(), **{k: v for k, v in body.model_dump().items() if v not in (None, "")}}
    cfg["remote_url"] = cfg["remote_url"].strip().rstrip("/")
    try:
        return {"ok": True, **test_remote(cfg)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(400, f"Worker error: {exc}")
