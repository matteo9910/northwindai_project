from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class VectorValidationResult(BaseModel):
    dialect: Literal["vector"] = "vector"
    allowed: bool
    collection_name: str
    top_k: int
    filters: dict[str, Any] = Field(default_factory=dict)
    violations: list[str] = Field(default_factory=list)

    @property
    def effective_query(self) -> None:
        return None
