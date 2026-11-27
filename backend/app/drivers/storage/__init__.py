"""BackupStorageBackend abstraction & LocalDiskStorageBackend implementation."""
from __future__ import annotations

import hashlib
import shutil
from abc import ABC, abstractmethod
from pathlib import Path


class BackupStorageBackend(ABC):
    """Storage abstraction enabling future S3/SFTP backends without changing backup orchestration."""

    @property
    @abstractmethod
    def backend_name(self) -> str: ...

    @abstractmethod
    async def store(self, local_artifact: Path, remote_key: str) -> tuple[str, int, str]:
        """Store artifact and return (stored_uri_or_path, size_bytes, sha256_hex)."""

    @abstractmethod
    async def retrieve(self, stored_uri: str, destination: Path) -> Path:
        """Retrieve artifact to local destination for restore."""

    @abstractmethod
    async def delete(self, stored_uri: str) -> None:
        """Delete stored artifact."""


class LocalDiskStorageBackend(BackupStorageBackend):
    """Stores backup archives under a managed local directory."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def backend_name(self) -> str:
        return "local"

    @staticmethod
    def _sha256_file(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    async def store(self, local_artifact: Path, remote_key: str) -> tuple[str, int, str]:
        target = self._base_dir / remote_key
        target.parent.mkdir(parents=True, exist_ok=True)
        if local_artifact.resolve() != target.resolve():
            shutil.copy2(local_artifact, target)
        size_bytes = target.stat().st_size
        checksum = self._sha256_file(target)
        return str(target), size_bytes, checksum

    async def retrieve(self, stored_uri: str, destination: Path) -> Path:
        src = Path(stored_uri)
        if not src.exists():
            raise FileNotFoundError(f"Backup artifact not found: {stored_uri}")
        shutil.copy2(src, destination)
        return destination

    async def delete(self, stored_uri: str) -> None:
        src = Path(stored_uri)
        if src.exists():
            src.unlink()
