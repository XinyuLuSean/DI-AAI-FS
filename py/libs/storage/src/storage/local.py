"""Local filesystem storage adapter.

Implements the same interface that a future S3 adapter would, so the rest
of the codebase never references the filesystem directly.

MVP: save uploaded files to a local directory, return the path.
Future: swap to boto3 S3 client behind the same interface.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path


class LocalStorage:
    """Store and retrieve files from a local directory."""

    def __init__(self, base_dir: str = "./uploads") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, filename: str, source_path: str) -> str:
        """Copy a file into managed storage, return the storage path."""
        unique = uuid.uuid4().hex[:8]
        dest = self.base_dir / f"{unique}_{filename}"
        shutil.copy2(source_path, dest)
        return str(dest)

    def save_bytes(self, filename: str, data: bytes) -> str:
        unique = uuid.uuid4().hex[:8]
        dest = self.base_dir / f"{unique}_{filename}"
        dest.write_bytes(data)
        return str(dest)

    def read_bytes(self, path: str) -> bytes:
        return Path(path).read_bytes()

    def exists(self, path: str) -> bool:
        return Path(path).exists()
