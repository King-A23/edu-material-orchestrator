from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict


ModelT = TypeVar("ModelT", bound="SerializableModel")


class SerializableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    def to_json_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def to_json_text(self, indent: int = 2) -> str:
        return self.model_dump_json(indent=indent)

    def write_json(self, path: str | Path, indent: int = 2) -> Path:
        output_path = Path(path)
        output_path.write_text(self.to_json_text(indent=indent), encoding="utf-8")
        return output_path

    @classmethod
    def from_json_text(cls: type[ModelT], payload: str) -> ModelT:
        return cls.model_validate_json(payload)

    @classmethod
    def from_json_file(cls: type[ModelT], path: str | Path) -> ModelT:
        return cls.from_json_text(Path(path).read_text(encoding="utf-8"))
