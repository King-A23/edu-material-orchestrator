from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .files import ensure_directory
from .hashing import hash_text


class CacheStore:
    def __init__(self, root: str | Path, enabled: bool = True) -> None:
        self.root = Path(root)
        self.enabled = enabled
        if self.enabled:
            ensure_directory(self.root)

    def key_for(self, *parts: str) -> str:
        return hash_text("::".join(parts))

    def entry_dir(self, namespace: str, key: str) -> Path:
        return self.root / namespace / key

    def has_json(self, namespace: str, key: str, filename: str = "payload.json") -> bool:
        if not self.enabled:
            return False
        return (self.entry_dir(namespace, key) / filename).exists()

    def read_json(self, namespace: str, key: str, filename: str = "payload.json") -> Any:
        path = self.entry_dir(namespace, key) / filename
        return json.loads(path.read_text(encoding="utf-8"))

    def write_json(self, namespace: str, key: str, payload: Any, filename: str = "payload.json") -> Path:
        entry = ensure_directory(self.entry_dir(namespace, key))
        path = entry / filename
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def write_text(self, namespace: str, key: str, payload: str, filename: str) -> Path:
        entry = ensure_directory(self.entry_dir(namespace, key))
        path = entry / filename
        path.write_text(payload, encoding="utf-8")
        return path

    def snapshot_directory(self, namespace: str, key: str, source_dir: str | Path, target_name: str = "assets") -> Path:
        entry = ensure_directory(self.entry_dir(namespace, key))
        target_dir = entry / target_name
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(source_dir, target_dir)
        return target_dir

    def restore_directory(self, namespace: str, key: str, destination_dir: str | Path, source_name: str = "assets") -> Path:
        source_dir = self.entry_dir(namespace, key) / source_name
        destination = Path(destination_dir)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source_dir, destination)
        return destination
