from __future__ import annotations

import hashlib
from pathlib import Path


def hash_file(path: str | Path, algorithm: str = "sha256", chunk_size: int = 65536) -> str:
    digest = hashlib.new(algorithm)
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def hash_text(text: str, algorithm: str = "sha256") -> str:
    digest = hashlib.new(algorithm)
    digest.update(text.encode("utf-8"))
    return digest.hexdigest()


def make_manifest_id(*parts: str) -> str:
    return hash_text("::".join(parts))
