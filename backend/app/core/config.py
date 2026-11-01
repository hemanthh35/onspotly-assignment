"""Central configuration. Everything tunable lives here and can be overridden from .env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[3]
load_dotenv(ROOT_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


@dataclass
class Pricing:
    """Unit prices used by the cost tracker. All in USD; override from .env."""
    # Compute: equivalent cloud price of one vCPU-hour (e.g. a general-purpose VM).
    vcpu_hour: float = field(default_factory=lambda: _float("PRICE_VCPU_HOUR", 0.048))
    # Storage: Supabase Storage price per GB-month.
    storage_gb_month: float = field(default_factory=lambda: _float("PRICE_STORAGE_GB_MONTH", 0.021))
    # Egress per GB (downloads of rendered reels).
    egress_gb: float = field(default_factory=lambda: _float("PRICE_EGRESS_GB", 0.09))
    # LLM token prices per 1M tokens (gpt-4.1 defaults).
    llm_input_per_m: float = field(default_factory=lambda: _float("PRICE_LLM_INPUT_PER_M", 2.00))
    llm_output_per_m: float = field(default_factory=lambda: _float("PRICE_LLM_OUTPUT_PER_M", 8.00))


@dataclass
class Settings:
    app_name: str = "OnSpotly Smart Rough Cut"
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", str(ROOT_DIR / "data"))))

    # Database: Supabase Postgres when DATABASE_URL is set, local SQLite otherwise.
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL"))

    # Storage: Supabase Storage when both values are set, local disk otherwise.
    supabase_url: str = field(default_factory=lambda: _env("SUPABASE_URL"))
    supabase_service_key: str = field(default_factory=lambda: _env("SUPABASE_SERVICE_KEY"))
    storage_bucket: str = field(default_factory=lambda: _env("STORAGE_BUCKET", "media"))

    # LLM: OpenAI when a key is set, rule-based planner otherwise.
    openai_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY"))
    openai_model: str = field(default_factory=lambda: _env("OPENAI_MODEL", "gpt-4.1"))

    admin_password: str = field(default_factory=lambda: _env("ADMIN_PASSWORD"))
    secret_key: str = field(default_factory=lambda: _env("SECRET_KEY", "onspotly-dev-secret"))

    # Vision / speech models.
    clip_model: str = field(default_factory=lambda: _env("CLIP_MODEL", "ViT-B-16"))
    clip_pretrained: str = field(default_factory=lambda: _env("CLIP_PRETRAINED", "laion2b_s34b_b88k"))
    whisper_model: str = field(default_factory=lambda: _env("WHISPER_MODEL", "small"))

    # Analysis sampling.
    clip_fps: float = field(default_factory=lambda: _float("CLIP_FPS", 2.0))
    quality_fps: float = field(default_factory=lambda: _float("QUALITY_FPS", 6.0))

    # Shot finder thresholds.
    missing_threshold: float = field(default_factory=lambda: _float("MISSING_THRESHOLD", 0.25))
    min_quality: float = field(default_factory=lambda: _float("MIN_QUALITY", 0.35))

    pricing: Pricing = field(default_factory=Pricing)

    @property
    def use_supabase_db(self) -> bool:
        return self.database_url.startswith("postgres")

    @property
    def use_supabase_storage(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key)

    @property
    def use_openai(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def sqlalchemy_url(self) -> str:
        if self.use_supabase_db:
            return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return f"sqlite:///{(self.data_dir / 'onspotly.db').as_posix()}"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def work_dir(self) -> Path:
        return self.data_dir / "work"


def _find_binary(name: str) -> str:
    """FFmpeg tools: explicit env var, then PATH, then the conda env's Library/bin."""
    import shutil
    import sys

    explicit = _env(name.upper() + "_PATH")
    if explicit:
        return explicit
    found = shutil.which(name)
    if found:
        return found
    for cand in (Path(sys.prefix) / "Library" / "bin" / f"{name}.exe", Path(sys.prefix) / "bin" / name):
        if cand.exists():
            return str(cand)
    return name


FFMPEG = _find_binary("ffmpeg")
FFPROBE = _find_binary("ffprobe")

settings = Settings()
for _d in (settings.data_dir, settings.cache_dir, settings.work_dir):
    _d.mkdir(parents=True, exist_ok=True)
