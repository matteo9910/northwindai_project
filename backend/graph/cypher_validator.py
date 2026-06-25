from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from backend.query.validator import DEFAULT_MAX_ROWS

ALLOWED_LABELS = {
    "Supplier",
    "Product",
    "Customer",
    "Order",
    "Shipment",
    "ShipmentDelayEvent",
    "CustomerComplaintEvent",
    "DeliveryDelayComplaintEvent",
    "PackagingQualityComplaintEvent",
    "ProductQualityComplaintEvent",
}
ALLOWED_RELATIONSHIP_TYPES = {
    "SUPPLIES",
    "PLACED",
    "CONTAINS",
    "FULFILLED_BY",
    "HAS_DELAY_EVENT",
    "RAISED_BY",
    "ABOUT_ORDER",
    "ABOUT_PRODUCT",
    "CLASSIFIED_AS",
    "SUPPORTED_BY_DELAY",
}
# `_path_depth_violations` counts the total number of relationship arrows in the
# query (not the longest path), so multi-MATCH traversals accumulate quickly. The
# Step 3 shipment-delay-complaint query already uses 8 arrows; keep headroom above
# that so adding one supporting MATCH does not silently fail validation.
DEFAULT_MAX_DEPTH = 10

BLOCKED_KEYWORDS = (
    "CREATE",
    "MERGE",
    "DELETE",
    "DETACH",
    "SET",
    "REMOVE",
    "LOAD CSV",
    "CREATE INDEX",
    "CREATE CONSTRAINT",
    "DROP",
    "ALTER",
    "CALL",
)

LABEL_PATTERN = re.compile(r"\((?:[A-Za-z_][A-Za-z0-9_]*)?:([A-Za-z][A-Za-z0-9_]*)")
RELATIONSHIP_PATTERN = re.compile(
    r"\[[^\]]*?:([A-Za-z][A-Za-z0-9_]*)(?:\|[A-Za-z][A-Za-z0-9_]*)*[^\]]*\]"
)
RELATIONSHIP_TYPES_PATTERN = re.compile(
    r":([A-Za-z][A-Za-z0-9_]*(?:\|[A-Za-z][A-Za-z0-9_]*)*)"
)
REL_PATTERN = re.compile(r"-\[[^\]]*\]-|-\[[^\]]*\]->|<-\[[^\]]*\]-")
BRACKET_PATTERN = re.compile(r"\[[^\]]*\]")
VARIABLE_LENGTH_PATTERN = re.compile(r"\*\s*(?:(\d+)?\s*\.\.\s*(\d+)?|(\d+))?")
LIMIT_PATTERN = re.compile(r"\bLIMIT\s+(\d+)\b", re.IGNORECASE)


@dataclass(frozen=True)
class CypherPolicy:
    allowed_labels: set[str] = field(default_factory=lambda: set(ALLOWED_LABELS))
    allowed_relationship_types: set[str] = field(
        default_factory=lambda: set(ALLOWED_RELATIONSHIP_TYPES)
    )
    max_rows: int = DEFAULT_MAX_ROWS
    max_depth: int = DEFAULT_MAX_DEPTH


class CypherValidationResult(BaseModel):
    dialect: Literal["cypher"] = "cypher"
    allowed: bool
    statement_type: str | None = None
    referenced_labels: list[str] = Field(default_factory=list)
    referenced_relationship_types: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)
    effective_cypher: str | None = None

    @property
    def effective_query(self) -> str | None:
        return self.effective_cypher


def validate_cypher(
    cypher: str,
    policy: CypherPolicy | None = None,
    max_rows: int | None = None,
) -> CypherValidationResult:
    policy = policy or CypherPolicy()
    if max_rows is not None:
        policy = CypherPolicy(
            allowed_labels=policy.allowed_labels,
            allowed_relationship_types=policy.allowed_relationship_types,
            max_rows=max_rows,
            max_depth=policy.max_depth,
        )

    violations = _string_guardrail_violations(cypher)
    referenced_labels = _referenced_labels(cypher)
    referenced_relationships = _referenced_relationship_types(cypher)

    violations.extend(_blocked_keyword_violations(cypher))
    for label in sorted(referenced_labels - policy.allowed_labels):
        violations.append(f"label_not_allowed:{label}")
    disallowed_relationships = (
        referenced_relationships - policy.allowed_relationship_types
    )
    for rel_type in sorted(disallowed_relationships):
        violations.append(f"relationship_not_allowed:{rel_type}")
    violations.extend(_path_depth_violations(cypher, policy.max_depth))

    effective_cypher = None
    if not violations:
        effective_cypher = _cap_cypher(cypher, policy.max_rows)

    return CypherValidationResult(
        allowed=not violations,
        statement_type="READ",
        referenced_labels=sorted(referenced_labels),
        referenced_relationship_types=sorted(referenced_relationships),
        violations=violations,
        effective_cypher=effective_cypher,
    )


def _string_guardrail_violations(cypher: str) -> list[str]:
    stripped = cypher.strip()
    if not stripped:
        return ["empty_cypher"]
    violations = []
    if ";" in stripped:
        violations.append("semicolon_not_allowed")
    if stripped.startswith("//") or stripped.startswith("/*"):
        violations.append("comment_prefixed_cypher")
    return violations


def _blocked_keyword_violations(cypher: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", cypher.upper())
    violations = []
    for keyword in BLOCKED_KEYWORDS:
        pattern = r"\b" + re.escape(keyword).replace(r"\ ", r"\s+") + r"\b"
        if re.search(pattern, normalized):
            violations.append(f"blocked_keyword:{keyword.lower().replace(' ', '_')}")
    return violations


def _referenced_labels(cypher: str) -> set[str]:
    labels = set()
    for match in LABEL_PATTERN.finditer(cypher):
        labels.add(match.group(1))
    return labels


def _referenced_relationship_types(cypher: str) -> set[str]:
    rel_types = set()
    for rel_match in RELATIONSHIP_PATTERN.finditer(cypher):
        for type_match in RELATIONSHIP_TYPES_PATTERN.finditer(rel_match.group(0)):
            rel_types.update(type_match.group(1).split("|"))
    return rel_types


def _path_depth_violations(cypher: str, max_depth: int) -> list[str]:
    violations = []
    explicit_depth = len(REL_PATTERN.findall(cypher))
    if explicit_depth > max_depth:
        violations.append(f"path_depth_exceeded:{explicit_depth}>{max_depth}")

    # Variable-length quantifiers are only valid inside a relationship bracket
    # (`[:REL*1..5]`, `[*1..5]`). Scanning the whole query would flag a literal
    # `*` in `RETURN count(*)` / `RETURN *` as an unbounded path.
    for bracket in BRACKET_PATTERN.finditer(cypher):
        for match in VARIABLE_LENGTH_PATTERN.finditer(bracket.group(0)):
            upper = match.group(2) or match.group(3)
            if upper is None:
                violations.append("variable_path_unbounded")
                continue
            try:
                depth = int(upper)
            except ValueError:
                violations.append("variable_path_unbounded")
                continue
            if depth > max_depth:
                violations.append(f"path_depth_exceeded:{depth}>{max_depth}")
    return violations


def _cap_cypher(cypher: str, max_rows: int) -> str:
    stripped = cypher.strip()
    match = LIMIT_PATTERN.search(stripped)
    if match is None:
        return f"{stripped}\nLIMIT {max_rows}"

    current_limit = int(match.group(1))
    if current_limit <= max_rows:
        return stripped
    return LIMIT_PATTERN.sub(f"LIMIT {max_rows}", stripped, count=1)
