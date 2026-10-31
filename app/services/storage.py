"""Photo / asset storage (C2). Local disk for development, Google Cloud Storage in production.

For GCS, also set a lifecycle rule on the bucket so originals are removed even if the
app's own cleanup job never runs:  gsutil lifecycle set deploy/gcs-lifecycle.json gs://BUCKET
"""
import time
from pathlib import Path

from app.config import settings


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _full(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("invalid storage key")
        return path

    def save(self, key: str, data: bytes) -> str:
        path = self._full(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def read(self, key: str) -> bytes:
        return self._full(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._full(key).exists()

    def delete(self, key: str) -> None:
        self._full(key).unlink(missing_ok=True)

    def purge(self, prefix: str, older_than_s: int) -> int:
        """Delete files under prefix last written more than older_than_s seconds ago."""
        base, cutoff, removed = self._full(prefix), time.time() - older_than_s, 0
        if not base.is_dir():
            return 0
        for path in base.rglob("*"):
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        for folder in sorted((d for d in base.rglob("*") if d.is_dir()), reverse=True):
            if not any(folder.iterdir()):
                folder.rmdir()
        return removed


class GCSStorage:
    def __init__(self, bucket: str):
        from google.cloud import storage  # pip install google-cloud-storage

        self.bucket = storage.Client().bucket(bucket)

    def save(self, key: str, data: bytes) -> str:
        self.bucket.blob(key).upload_from_string(data)
        return key

    def read(self, key: str) -> bytes:
        return self.bucket.blob(key).download_as_bytes()

    def exists(self, key: str) -> bool:
        return self.bucket.blob(key).exists()

    def delete(self, key: str) -> None:
        blob = self.bucket.blob(key)
        if blob.exists():
            blob.delete()

    def purge(self, prefix: str, older_than_s: int) -> int:
        cutoff, removed = time.time() - older_than_s, 0
        for blob in self.bucket.list_blobs(prefix=prefix):
            if blob.updated and blob.updated.timestamp() < cutoff:
                blob.delete()
                removed += 1
        return removed


def _make_storage():
    if settings.storage_backend == "gcs":
        return GCSStorage(settings.gcs_bucket)
    return LocalStorage(settings.data_dir / "storage")


storage = _make_storage()
