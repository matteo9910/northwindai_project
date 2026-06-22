from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from pydantic import BaseModel, Field
from sqlglot import exp

ALLOWED_SCHEMAS = {"erp_core", "erp_docs"}
ALLOWED_TABLES = {
    "erp_core.categories",
    "erp_core.customer_customer_demo",
    "erp_core.customer_demographics",
    "erp_core.customers",
    "erp_core.employees",
    "erp_core.employee_territories",
    "erp_core.order_details",
    "erp_core.orders",
    "erp_core.products",
    "erp_core.region",
    "erp_core.shippers",
    "erp_core.suppliers",
    "erp_core.territories",
    "erp_core.us_states",
    "erp_core.warehouses",
    "erp_core.shipments",
    "erp_core.invoices",
    "erp_core.inventory_movements",
    "erp_core.price_history",
    "erp_docs.documents",
    "erp_docs.document_entities",
    "erp_docs.customer_communications",
    "erp_docs.supplier_contracts",
    "erp_docs.product_specifications",
}
DEFAULT_MAX_ROWS = 1000
BLOCKED_STATEMENT_NAMES = {
    "ALTER",
    "CALL",
    "COPY",
    "CREATE",
    "DELETE",
    "DO",
    "DROP",
    "GRANT",
    "INSERT",
    "MERGE",
    "REVOKE",
    "TRUNCATE",
    "UPDATE",
}


class ValidationResult(BaseModel):
    allowed: bool
    statement_type: str | None = None
    referenced_schemas: list[str] = Field(default_factory=list)
    referenced_tables: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)
    effective_sql: str | None = None


@dataclass(frozen=True)
class QueryPolicy:
    allowed_schemas: set[str] = field(default_factory=lambda: set(ALLOWED_SCHEMAS))
    allowed_tables: set[str] = field(default_factory=lambda: set(ALLOWED_TABLES))
    max_rows: int = DEFAULT_MAX_ROWS


def validate_sql(
    sql: str,
    policy: QueryPolicy | None = None,
    max_rows: int | None = None,
) -> ValidationResult:
    policy = policy or QueryPolicy()
    if max_rows is not None:
        policy = QueryPolicy(
            allowed_schemas=policy.allowed_schemas,
            allowed_tables=policy.allowed_tables,
            max_rows=max_rows,
        )

    violations = _string_guardrail_violations(sql)
    try:
        statements = [stmt for stmt in sqlglot.parse(sql, read="postgres") if stmt]
    except Exception as exc:  # noqa: BLE001 - validation must fail closed.
        return ValidationResult(
            allowed=False,
            violations=[*violations, f"parse_error:{exc}"],
        )

    if len(statements) != 1:
        return ValidationResult(
            allowed=False,
            violations=[*violations, "multiple_statements"],
        )

    tree = statements[0]
    statement_type = _statement_type(tree)
    if statement_type in BLOCKED_STATEMENT_NAMES:
        violations.append(f"blocked_statement:{statement_type.lower()}")
    # Scan the whole AST: a data-modifying statement can hide inside a CTE
    # (e.g. `with x as (insert ... returning ...) select ...`), whose top-level
    # node is a read-only Select. The top-level check alone would miss it.
    for nested in _nested_dml_violations(tree):
        if nested not in violations:
            violations.append(nested)
    if not _is_read_only_select(tree):
        violations.append("not_read_only")

    cte_names = _cte_names(tree)
    schemas, tables = _referenced_tables(tree, cte_names)
    for schema in sorted(schemas - policy.allowed_schemas):
        violations.append(f"schema_not_allowed:{schema}")
    for table_name in sorted(tables - policy.allowed_tables):
        violations.append(f"table_not_allowed:{table_name}")

    for table in tree.find_all(exp.Table):
        if table.name in cte_names:
            continue
        if not table.db:
            violations.append(f"unqualified_table:{table.name}")

    effective_sql = None
    if not violations:
        effective_sql = _cap_sql(tree, policy.max_rows)

    return ValidationResult(
        allowed=not violations,
        statement_type=statement_type,
        referenced_schemas=sorted(schemas),
        referenced_tables=sorted(tables),
        violations=violations,
        effective_sql=effective_sql,
    )


def _string_guardrail_violations(sql: str) -> list[str]:
    stripped = sql.strip()
    violations = []
    if not stripped:
        return ["empty_sql"]
    if stripped.count(";") > 0:
        tail = stripped.split(";", 1)[1].strip()
        if tail:
            violations.append("multiple_statements")
        else:
            violations.append("trailing_semicolon")
    if stripped.startswith("--") or stripped.startswith("/*"):
        violations.append("comment_prefixed_sql")
    return violations


_NESTED_DML = (
    (exp.Insert, "insert"),
    (exp.Update, "update"),
    (exp.Delete, "delete"),
    (exp.Merge, "merge"),
)


def _nested_dml_violations(tree: exp.Expression) -> list[str]:
    found = []
    for node_type, label in _NESTED_DML:
        if next(iter(tree.find_all(node_type)), None) is not None:
            found.append(f"blocked_statement:{label}")
    return found


def _statement_type(tree: exp.Expression) -> str:
    if isinstance(tree, exp.Select):
        return "SELECT"
    if isinstance(tree, exp.Union):
        return "SELECT"
    return tree.key.upper()


def _is_read_only_select(tree: exp.Expression) -> bool:
    if isinstance(tree, (exp.Select, exp.Union)):
        return True
    return False


def _cte_names(tree: exp.Expression) -> set[str]:
    names = set()
    for cte in tree.find_all(exp.CTE):
        alias = cte.alias
        if alias:
            names.add(alias)
    return names


def _referenced_tables(
    tree: exp.Expression,
    cte_names: set[str],
) -> tuple[set[str], set[str]]:
    schemas: set[str] = set()
    tables: set[str] = set()
    for table in tree.find_all(exp.Table):
        if table.name in cte_names:
            continue
        if table.db:
            schema = str(table.db)
            name = str(table.name)
            schemas.add(schema)
            tables.add(f"{schema}.{name}")
    return schemas, tables


def _cap_sql(tree: exp.Expression, max_rows: int) -> str:
    capped = tree.copy()
    limit = capped.args.get("limit")
    if limit is None:
        capped = capped.limit(max_rows)
        return capped.sql(dialect="postgres")

    expression = limit.expression
    if isinstance(expression, exp.Literal):
        try:
            if int(expression.name) > max_rows:
                capped = capped.limit(max_rows)
        except ValueError:
            capped = capped.limit(max_rows)
    else:
        capped = capped.limit(max_rows)
    return capped.sql(dialect="postgres")
