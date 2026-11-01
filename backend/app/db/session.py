from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


_engine_kwargs: dict = {}
if settings.use_supabase_db:
    # No pre-ping: it costs a full network round trip per request on a remote database.
    # Connections are recycled before Supabase's pooler would drop them instead.
    _engine_kwargs.update(pool_size=5, max_overflow=5, pool_recycle=240)
else:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.sqlalchemy_url, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    from app.db import models  # noqa: F401  (registers tables)

    Base.metadata.create_all(engine)
