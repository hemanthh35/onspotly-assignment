"""Storage providers: Supabase Storage bucket or local disk, same interface.

Processing always works on a local copy (`local_path`), so the AI pipeline never cares where
the bytes really live.
"""
from __future__ import annotations

import mimetypes
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from app.core.config import settings


class StorageProvider(ABC):
    name = "base"

    @abstractmethod
    def put(self, key: str, src: Path) -> None: ...

    @abstractmethod
    def _download(self, key: str, dest: Path) -> None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    def local_path(self, key: str) -> Path:
        """Local copy of an object, downloaded once and cached."""
        dest = settings.cache_dir / "objects" / key
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            self._download(key, dest)
        return dest


class LocalStorage(StorageProvider):
    name = "local"

    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, src: Path) -> None:
        dest = self.root / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.resolve() != dest.resolve():
            shutil.copyfile(src, dest)

    def _download(self, key: str, dest: Path) -> None:
        shutil.copyfile(self.root / key, dest)

    def local_path(self, key: str) -> Path:
        return self.root / key

    def delete(self, key: str) -> None:
        (self.root / key).unlink(missing_ok=True)


class SupabaseStorage(StorageProvider):
    name = "supabase"

    def __init__(self, url: str, key: str, bucket: str):
        from supabase import create_client

        self.client = create_client(url, key)
        self.bucket = bucket
        existing = {b.name for b in self.client.storage.list_buckets()}
        if bucket not in existing:
            self.client.storage.create_bucket(bucket, options={"public": False})

    @property
    def _b(self):
        return self.client.storage.from_(self.bucket)

    def put(self, key: str, src: Path) -> None:
        ctype = mimetypes.guess_type(src.name)[0] or "application/octet-stream"
        with open(src, "rb") as f:
            self._b.upload(key, f, file_options={"content-type": ctype, "upsert": "true"})
        # Keep the local copy as cache so we don't download what we just uploaded.
        cached = settings.cache_dir / "objects" / key
        if not cached.exists():
            cached.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, cached)

    def _download(self, key: str, dest: Path) -> None:
        dest.write_bytes(self._b.download(key))

    def delete(self, key: str) -> None:
        self._b.remove([key])
        (settings.cache_dir / "objects" / key).unlink(missing_ok=True)


def _build() -> StorageProvider:
    if settings.use_supabase_storage:
        try:
            return SupabaseStorage(settings.supabase_url, settings.supabase_service_key, settings.storage_bucket)
        except Exception as exc:  # network / auth problems: keep the platform usable
            print(f"[storage] Supabase unavailable ({exc}); falling back to local disk")
    return LocalStorage(settings.data_dir / "storage")


storage: StorageProvider = _build()
