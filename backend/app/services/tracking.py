"""Cost and activity tracking. Every job step and LLM call is metered here."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import ActivityEvent, CostRecord


def log_activity(db: Session, type_: str, message: str, project_id: str | None = None, **meta) -> None:
    db.add(ActivityEvent(project_id=project_id, type=type_, message=message[:500], meta=meta))


def record_compute(db: Session, project_id: str, job_id: str, cpu_seconds: float, wall_seconds: float,
                   kind: str) -> float:
    p = settings.pricing
    amount = cpu_seconds / 3600 * p.vcpu_hour
    db.add(CostRecord(project_id=project_id, job_id=job_id, category="compute", amount_usd=amount,
                      quantity=round(cpu_seconds, 2), unit="vcpu_seconds",
                      meta={"kind": kind, "wall_seconds": round(wall_seconds, 2), "price_vcpu_hour": p.vcpu_hour}))
    return amount


def record_llm(db: Session, project_id: str | None, job_id: str | None, model: str, input_tokens: int,
               output_tokens: int, purpose: str) -> float:
    p = settings.pricing
    amount = input_tokens / 1e6 * p.llm_input_per_m + output_tokens / 1e6 * p.llm_output_per_m
    db.add(CostRecord(project_id=project_id, job_id=job_id, category="llm", amount_usd=amount,
                      quantity=input_tokens + output_tokens, unit="tokens",
                      meta={"model": model, "input_tokens": input_tokens, "output_tokens": output_tokens,
                            "purpose": purpose}))
    return amount


def record_storage(db: Session, project_id: str, size_bytes: int, what: str) -> float:
    """Storage is billed per GB-month; we book one month for every object written."""
    p = settings.pricing
    gb = size_bytes / 2**30
    amount = gb * p.storage_gb_month
    db.add(CostRecord(project_id=project_id, category="storage", amount_usd=amount, quantity=round(gb, 6),
                      unit="gb_month", meta={"what": what, "bytes": size_bytes}))
    return amount


def record_egress(db: Session, project_id: str, size_bytes: int, what: str) -> float:
    p = settings.pricing
    gb = size_bytes / 2**30
    amount = gb * p.egress_gb
    db.add(CostRecord(project_id=project_id, category="egress", amount_usd=amount, quantity=round(gb, 6),
                      unit="gb", meta={"what": what, "bytes": size_bytes}))
    return amount
