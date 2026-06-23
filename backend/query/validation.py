from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ValidationResult(Protocol):
    """Structural contract shared by SQL and Cypher validation results.

    Consumers that only need the common surface (the executors) depend on this
    Protocol rather than on a concrete dialect type. Dialect-specific details
    (referenced schemas/tables vs labels/relationship types) live on the
    concrete models `SqlValidationResult` and `CypherValidationResult`.
    """

    allowed: bool
    statement_type: str | None
    violations: list[str]

    @property
    def effective_query(self) -> str | None:
        """The validated, execution-ready query text (SQL or Cypher)."""
        ...
