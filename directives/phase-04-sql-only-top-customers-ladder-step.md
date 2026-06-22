# Phase 04 — Query Ladder Step 1: SQL-only Top Customers

> Macro phase 4 of the NorthwindAI build. Delivers the **first query ladder step
> end-to-end**: answer *"Who are the top 10 customers by net revenue in the last
> 12 months?"* against the Operational Source of Truth (PostgreSQL/Supabase),
> through a **governed, read-only execution path** with a code-level SQL
> validator (ADR 0009) and a structured **`answer_trace`** (ADR 0003). This phase
> builds the *query/governance spine* that every later route (graph, vector,
> Golden Query) reuses. It does **not** touch Neo4j, Qdrant, or an LLM.

---

## Objective

Stand up the SQL-only branch of the agentic query system so that:

- there is a reusable **read-only execution path** to PostgreSQL that no caller
  can use to mutate data (guardrails enforced in code, not prompts — ADR 0009),
- there is a code-level **SQL validator** that accepts read-only `SELECT`/`WITH`
  against an allowlist of schemas/tables and rejects everything else, returning
  **structured validation results** that can appear in `answer_trace`,
- the **Top Customers** ladder question is answered by net revenue over a fixed
  analysis window, **computed at query time** and never stored (ADR 0013),
- every answer returns a structured **`answer_trace`** whose full shape (ADR 0003)
  is defined now, with the SQL-only subset populated,
- the step is exposed both as a **callable service function** (testable) and a
  thin **FastAPI endpoint** that returns an inspectable `answer_trace`,
- the step has a stored **expected answer spec** (behavioral) and can persist its
  **actual `answer_trace`** so failures localize to validation vs. execution vs.
  synthesis.

**Query ladder:** this is **Step 1** of the progressive query ladder
(Step 1 SQL-only → … → Step 5 Golden Query). It is intentionally the simplest
rung: prove the governed SQL layer in isolation before composing graph/vector
routes. The LangGraph router and LLM-generated SQL are **later phases** — here
the route is fixed to `sql_only` and the SQL is built deterministically.

---

## Prerequisites

- **Phase 03 complete and verified.** `erp_core`/`erp_docs` hold the deterministic
  2020–2025 synthetic dataset; the designated top customers are real in the data
  (Phase 03 self-check passed). The `/health` Postgres check returns
  `available: true`.
- `backend.config.get_settings().postgres_dsn` connects (reused here).
- `pip install -e ".[dev]"` works; `pytest` and `ruff check .` are clean.
- The Supabase MCP server targets `northwindai` (used only for **read-back
  verification** here, e.g. comparing the API result against `execute_sql`).

---

## Design decisions (read before implementing)

These mirror the "document the decision" pattern from Phase 03. They are binding
for this phase:

1. **Deterministic SQL, no LLM yet.** Step 1 builds the Top Customers SQL with a
   small parameterized builder, not text-to-SQL. Rationale: the ladder proves one
   layer at a time; Step 1 proves the *governed execution path + validator +
   trace* deterministically and testably. **However**, the validator must treat
   the SQL as if it were untrusted/generated (full allowlist + read-only checks),
   so the exact same path is ready when LLM-generated SQL arrives in a later phase.
2. **Fixed analysis reference date.** Reuse Phase 03's anchor: `ANALYSIS_AS_OF =
   date(2025, 12, 31)`; "last 12 months" ⇒ `2025-01-01 .. 2025-12-31`. This is
   decoupled from wall-clock time so the answer is stable. The net-revenue formula
   **must byte-for-byte match** Phase 03's definition (and
   `data_generation/scenarios.py::TOP_CUSTOMERS_SQL`).
3. **Full `answer_trace` schema now.** Define all ADR 0003 fields as Pydantic
   models in this phase; populate the SQL-only subset (`route`, `generated_sql`,
   `metrics`, `validation_results`, `provenance`) and leave graph/vector fields
   empty. Later phases fill them without redesigning the contract.
4. **Route is asserted, not classified.** For Step 1 the route is hard-set to
   `sql_only`. Do **not** build the router here; just record the route in the trace
   so the eval harness can later compare expected vs. actual route.

---

## Functional requirements

After this phase the system MUST:

1. Provide a `query_validator` that, given a SQL string and a policy, returns a
   structured result with: `allowed: bool`, `statement_type`, `referenced_schemas`,
   `referenced_tables`, `violations: list[str]`, and the `effective_sql` actually
   sent to the database (e.g. with an enforced row cap).
2. Reject, with explanatory violations: any statement that is not a single
   read-only `SELECT`/`WITH`; any `INSERT/UPDATE/DELETE/MERGE/DROP/ALTER/CREATE/
   TRUNCATE/GRANT/REVOKE/COPY/CALL/DO`; multiple statements (stacked queries);
   references to schemas outside the allowlist (`erp_core`, `erp_docs`); references
   to tables outside the table allowlist.
3. Accept representative read-only analytical queries against the allowlist and
   enforce a maximum returned-row cap (configurable; default 1000).
4. Provide a `executor` that runs only validated SQL inside a **read-only
   transaction** with a **statement timeout**, returning rows + execution metrics
   (`row_count`, `duration_ms`), and that refuses (or fails closed) on any attempt
   to run unvalidated or mutating SQL.
5. Answer **Top Customers**: return the top 10 `customer_id` by net revenue over
   `2025-01-01 .. 2025-12-31`, descending, each with its `net_revenue`, computed at
   query time.
6. Return a structured `answer_trace` (ADR 0003 full shape) for the answer, with
   `route = "sql_only"`, the `generated_sql`, the `validation_results`, `metrics`,
   and `provenance` (the `erp_core` tables/columns and the `rule_name`/version used).
7. Expose the step via FastAPI (`GET /ladder/top-customers`) returning the answer
   **and** its `answer_trace`, plus a callable service function for tests.
8. Store an **expected answer spec** (behavioral) for Step 1 and be able to persist
   the **actual `answer_trace`** to a file for inspection/evaluation.

---

## Technical requirements

### Analysis window & revenue definition
- Add to `backend` a small constants module (e.g. `backend/ladder/constants.py`):
  ```python
  from datetime import date
  ANALYSIS_AS_OF = date(2025, 12, 31)        # must match data_generation.config.AS_OF
  LAST_12M_START = date(2025, 1, 1)
  TOP_CUSTOMERS_LIMIT = 10
  ```
- **Net revenue** = `sum(order_details.unit_price * quantity * (1 - discount))`
  over the window, grouped by `customer_id`, ordered desc. Identical to Phase 03.
  Add a comment cross-referencing Phase 03 so the two never drift.

### SQL validator (ADR 0009 — SQL side)
- Parse with **`sqlglot`** (`dialect="postgres"`) to obtain an AST; do not rely on
  regex alone. Use the AST to determine the statement type and the set of
  referenced schema-qualified tables; apply allowlists on the AST. Keep a
  defense-in-depth string check (reject `;` that separates statements, reject
  comment-only obfuscation) as a secondary guard.
- Policy object holds: allowed schemas (`{"erp_core", "erp_docs"}`), allowed
  tables (explicit set of the Phase 02 tables), `max_rows` (default 1000).
- **Tables must be schema-qualified.** Reject unqualified table references (forces
  the router/builder to be explicit and keeps the allowlist enforceable).
- Enforce the row cap by wrapping/validating `LIMIT` (cap or inject a `LIMIT`).
- The result is a Pydantic model so it serializes directly into `answer_trace`.

### Executor (read-only path)
- One `psycopg.connect(get_settings().postgres_dsn)` per call (or a small pool
  later). Per call:
  - `conn.read_only = True` (psycopg) **and** issue `SET TRANSACTION READ ONLY`
    and `SET LOCAL statement_timeout = <ms>` at the start of the transaction
    (defense in depth — a read-only tx physically cannot mutate).
  - Execute only `validation_result.effective_sql`; never raw caller SQL.
  - Return rows + `metrics` (`row_count`, `duration_ms`). Roll back the (read-only)
    transaction at the end — nothing to commit.
- The executor must refuse to run SQL whose `validation_result.allowed` is `False`.

### `answer_trace` (ADR 0003 — full schema)
- Pydantic models in `backend/query/trace.py`. Fields (full contract):
  `route`, `generated_sql`, `generated_cypher`, `graph_paths`, `retrieved_chunks`,
  `documents_used`, `metrics`, `validation_results`, `provenance`. Use enums for
  `route` covering all ADR 0002 route types
  (`sql_only`, `graph_only`, `vector_only`, `graph_plus_sql`, `graph_plus_vector`,
  `sql_plus_graph_plus_vector`). Graph/vector fields default to empty lists/None.
- `provenance` for SQL = a list of entries carrying at least `source_system =
  "postgresql"`, `source_schema`, `source_table`, and the `rule_name` /
  `rule_version` (e.g. `top_customers`, `v1`) per ADR 0005's "traceable to
  source/rule" requirement.

### API & packaging
- Add `backend/ladder/router.py` and `include_router` it in `backend/main.py`,
  following the existing `backend/health/router.py` pattern (FastAPI `APIRouter`,
  `Depends(get_settings)`).
- Add dependency `sqlglot>=23,<30` to `pyproject.toml` `[project].dependencies`.
- Keep ruff clean (`select = ["E","F","I","UP","B"]`); 88-col lines; `snake_case`.

### Evaluation artifacts
- `evaluation/ladder/step01_top_customers.spec.*` — the **expected answer spec**
  (behavioral; see Acceptance). May be Python or JSON; keep it declarative.
- A way to persist the **actual** trace (e.g. a small CLI `python -m
  backend.ladder.top_customers --emit-trace` or a test fixture) writing
  `evaluation/answer_traces/step01_top_customers.json`. Persisted actual traces
  are regenerable; committing a sample is fine (it is a tiny governance artifact,
  not a data dump).

---

## File structure

```text
test-project/
├─ backend/
│  ├─ main.py                       # include ladder router
│  ├─ query/
│  │  ├─ __init__.py
│  │  ├─ validator.py               # SQL guardrails (ADR 0009) + ValidationResult model
│  │  ├─ executor.py                # read-only execution path (RO tx, timeout, metrics)
│  │  └─ trace.py                   # answer_trace Pydantic models (ADR 0003, full shape)
│  └─ ladder/
│     ├─ __init__.py
│     ├─ constants.py               # ANALYSIS_AS_OF, window, TOP_CUSTOMERS_LIMIT
│     ├─ top_customers.py           # build SQL → validate → execute → assemble trace (+CLI)
│     └─ router.py                  # GET /ladder/top-customers
├─ evaluation/
│  ├─ ladder/
│  │  └─ step01_top_customers.spec.json   # expected answer spec (behavioral)
│  └─ answer_traces/
│     └─ step01_top_customers.json        # persisted actual trace (regenerable sample)
└─ tests/
   ├─ test_query_validator.py       # accepts read-only / rejects mutations & bad schemas
   ├─ test_query_executor.py        # read-only enforcement, timeout, metrics
   └─ test_ladder_top_customers.py  # revenue correctness, route, trace shape, endpoint
```

---

## Implementation guidance

### Validator (`backend/query/validator.py`)

```python
from __future__ import annotations

import sqlglot
from sqlglot import exp
from pydantic import BaseModel

ALLOWED_SCHEMAS = {"erp_core", "erp_docs"}
ALLOWED_TABLES = {
    "erp_core.customers", "erp_core.orders", "erp_core.order_details",
    "erp_core.products", "erp_core.suppliers", "erp_core.categories",
    "erp_core.employees", "erp_core.shippers", "erp_core.warehouses",
    "erp_core.shipments", "erp_core.invoices", "erp_core.inventory_movements",
    "erp_core.price_history",
    "erp_docs.documents", "erp_docs.document_entities",
    "erp_docs.customer_communications", "erp_docs.supplier_contracts",
    "erp_docs.product_specifications",
}
DEFAULT_MAX_ROWS = 1000


class ValidationResult(BaseModel):
    allowed: bool
    statement_type: str | None = None
    referenced_schemas: list[str] = []
    referenced_tables: list[str] = []
    violations: list[str] = []
    effective_sql: str | None = None


def validate_sql(sql: str, max_rows: int = DEFAULT_MAX_ROWS) -> ValidationResult:
    violations: list[str] = []
    try:
        statements = sqlglot.parse(sql, read="postgres")
    except Exception as exc:  # noqa: BLE001 - surface as a violation, never raise
        return ValidationResult(allowed=False, violations=[f"parse_error: {exc}"])
    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        return ValidationResult(allowed=False, violations=["multiple_statements"])

    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.With)):
        return ValidationResult(
            allowed=False,
            statement_type=type(tree).__name__,
            violations=["not_read_only"],
        )

    schemas, tables = set(), set()
    for table in tree.find_all(exp.Table):
        if not table.db:
            violations.append(f"unqualified_table:{table.name}")
            continue
        schemas.add(table.db)
        tables.add(f"{table.db}.{table.name}")

    for schema in schemas - ALLOWED_SCHEMAS:
        violations.append(f"schema_not_allowed:{schema}")
    for tbl in tables - ALLOWED_TABLES:
        violations.append(f"table_not_allowed:{tbl}")

    # Enforce the row cap (cap an existing LIMIT or inject one).
    capped = tree.copy()
    limit = capped.args.get("limit")
    if limit is None:
        capped = capped.limit(max_rows)
    else:
        current = limit.expression
        if isinstance(current, exp.Literal) and int(current.name) > max_rows:
            capped = capped.limit(max_rows)
    effective_sql = capped.sql(dialect="postgres")

    return ValidationResult(
        allowed=not violations,
        statement_type="SELECT",
        referenced_schemas=sorted(schemas),
        referenced_tables=sorted(tables),
        violations=violations,
        effective_sql=effective_sql if not violations else None,
    )
```

### Executor (`backend/query/executor.py`)

```python
from __future__ import annotations

import time
import psycopg

from backend.config import get_settings
from backend.query.validator import ValidationResult

DEFAULT_TIMEOUT_MS = 5000


def run_validated(result: ValidationResult, timeout_ms: int = DEFAULT_TIMEOUT_MS):
    if not result.allowed or not result.effective_sql:
        raise ValueError("refusing to execute SQL that failed validation")
    with psycopg.connect(get_settings().postgres_dsn) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(f"set local statement_timeout = {int(timeout_ms)}")
            start = time.perf_counter()
            cur.execute(result.effective_sql)
            rows = cur.fetchall()
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
        conn.rollback()  # read-only; nothing to commit
    return rows, {"row_count": len(rows), "duration_ms": duration_ms}
```

### Top Customers step (`backend/ladder/top_customers.py`)

```python
from backend.ladder.constants import LAST_12M_START, ANALYSIS_AS_OF, TOP_CUSTOMERS_LIMIT
from backend.query.validator import validate_sql
from backend.query.executor import run_validated
from backend.query.trace import AnswerTrace, ProvenanceEntry

# Net revenue — MUST match Phase 03 (data_generation/scenarios.py TOP_CUSTOMERS_SQL).
TOP_CUSTOMERS_SQL = """
select o.customer_id,
       sum(od.unit_price * od.quantity * (1 - od.discount)) as net_revenue
from erp_core.orders o
join erp_core.order_details od on od.order_id = o.order_id
where o.order_date >= date '{start}' and o.order_date <= date '{end}'
group by o.customer_id
order by net_revenue desc
limit {limit}
"""


def answer_top_customers() -> tuple[list[dict], AnswerTrace]:
    sql = TOP_CUSTOMERS_SQL.format(
        start=LAST_12M_START, end=ANALYSIS_AS_OF, limit=TOP_CUSTOMERS_LIMIT
    )
    validation = validate_sql(sql)
    rows, metrics = run_validated(validation)
    answer = [{"customer_id": c, "net_revenue": float(r)} for c, r in rows]
    trace = AnswerTrace(
        route="sql_only",
        generated_sql=validation.effective_sql,
        metrics=metrics,
        validation_results=[validation],
        provenance=[
            ProvenanceEntry(
                source_system="postgresql", source_schema="erp_core",
                source_table="orders", rule_name="top_customers", rule_version="v1",
            ),
            ProvenanceEntry(
                source_system="postgresql", source_schema="erp_core",
                source_table="order_details", rule_name="top_customers",
                rule_version="v1",
            ),
        ],
    )
    return answer, trace
```

> Note the SQL is assembled from **trusted constants** (no user input), then still
> passed through `validate_sql` — the governed path is identical to the future
> LLM-generated case.

### Endpoint (`backend/ladder/router.py`)
- `APIRouter`; `GET /ladder/top-customers` calls `answer_top_customers()` and
  returns `{"answer": [...], "answer_trace": {...}}`. Register in `backend/main.py`.

### Verification via MCP
After implementing, compare the API/function output against a direct
`execute_sql` of `TOP_CUSTOMERS_SQL` on `northwindai` — the 10 ids and revenues
must match exactly.

---

## Acceptance criteria

This phase is complete when **all** of the following hold:

- [ ] `pyproject.toml` includes `sqlglot`; `pip install -e ".[dev]"` succeeds.
- [ ] **Validator accepts** a representative read-only `SELECT`/`WITH` over the
      allowlist and returns `allowed: True` with an `effective_sql` carrying an
      enforced `LIMIT`.
- [ ] **Validator rejects** (with explanatory `violations`): `INSERT`, `UPDATE`,
      `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `GRANT`, stacked
      multi-statements, a query against a non-allowlisted schema (e.g. `public`,
      `pg_catalog`), and an unqualified table reference.
- [ ] **Executor** runs only validated SQL inside a read-only transaction with a
      statement timeout, returns rows + `metrics`, and raises/refuses on
      unvalidated input. A test proves a mutation cannot pass through (validation
      fails closed; and/or the read-only tx rejects a write).
- [ ] **Top Customers** returns exactly 10 rows, each `{customer_id, net_revenue}`,
      strictly ordered by `net_revenue` desc, all `net_revenue > 0`.
- [ ] The result **matches the MCP read-back** (`execute_sql` of the same query):
      identical 10 `customer_id`s and revenues; and matches the deterministic
      designated top customers from Phase 03.
- [ ] **Net-revenue parity**: a test recomputes net revenue independently (e.g.
      in Python from raw rows, or via an alternate SQL) and matches the answer
      within float tolerance — proving the formula equals Phase 03's.
- [ ] **`answer_trace`** validates against the full Pydantic schema with
      `route == "sql_only"`, populated `generated_sql`, `validation_results`,
      `metrics`, and `provenance`; graph/vector fields present but empty.
- [ ] `GET /ladder/top-customers` returns `200` with `answer` + `answer_trace`
      (test may skip if the DSN is unconfigured, like the Phase 03 fixture).
- [ ] The **expected answer spec** for Step 1 is stored under `evaluation/ladder/`
      and encodes behavioral expectations (route, row count, ordering, positivity,
      read-only validation passed) — **not** a pinned result string.
- [ ] The step can **persist its actual `answer_trace`** to
      `evaluation/answer_traces/step01_top_customers.json`.
- [ ] `pytest` and `ruff check .` are clean. All new code is committed.

---

## Out of scope (do NOT do in this phase)

- **LangGraph Query Router / route classification** — Phase with the router
  (Issue 10). Here the route is hard-set to `sql_only`.
- **LLM text-to-SQL** or any LLM/OpenRouter/HF/Ollama call — later. The SQL is
  built from trusted constants and still validated.
- **Any Neo4j or Qdrant work** — graph projection, Event Nodes, Cypher validator,
  chunking, embeddings. The `answer_trace` graph/vector fields stay empty.
  (The **Cypher** side of the validator arrives with the Neo4j phases, built on
  this same `ValidationResult` contract.)
- **Other ladder steps** (supplier→product traversal, delay events, contract
  retrieval, Golden Query) — Phases 05+.
- **Schema changes / migrations / new data** — Phase 04 is read-only over the
  Phase 02/03 database. If a query need reveals a schema gap, stop and raise it.
- **Auth / RLS / deployment hardening** — out of scope for Milestone 1.
- **A polished frontend** — the FastAPI endpoint + JSON `answer_trace` is the only
  surface here.

---

## References

- `CLAUDE.md` → invariant #5 (guardrails in code, not prompts), #6 (`answer_trace`
  is mandatory), #7 (routing is explicit; SQL-first for point/aggregate), #9
  (Top Customers = net revenue, computed not stored).
- `docs/adr/0002-*` — route types for the Query Router (the `route` enum).
- `docs/adr/0003-*` — the `answer_trace` contract.
- `docs/adr/0005-*` — graph/provenance traceability (provenance fields).
- `docs/adr/0009-*` — code-level query guardrails (SQL `SELECT`-only, allowlists,
  limits; validation results returnable in `answer_trace`).
- `docs/adr/0013-*` — Top Customers by net revenue, top 10 over last 12 months,
  computed at query time.
- `docs/ISSUES.md` → Issue 2 (Deliver the SQL-only Top Customers ladder step),
  Issue 5 (read-only guardrails — SQL side delivered here), Issue 11 (answer-trace
  evaluation — the spec/trace persistence seeded here).
- `docs/PRD.md` → user stories 2, 3, 6, 7, 20, 26, 30, 31, 35, 40; Testing
  decisions (ladder expected-answer specs + persisted actual `answer_trace`).
- `directives/phase-03-synthetic-data-and-controlled-scenarios.md` — the data this
  step queries, and the net-revenue / `AS_OF` definitions it must match.
```