# Phase 05 — Graph Projection & Query Ladder Step 2: graph-only Supplier→Product

> Macro phase 5 of the NorthwindAI build. Delivers the **second query ladder step
> end-to-end**: answer *"Which products does Tokyo Traders supply?"* against the
> **Knowledge Layer (Neo4j)**, through a **governed, read-only Cypher execution
> path** with a code-level Cypher validator (ADR 0009) and a structured
> **`answer_trace`** (ADR 0003) whose graph fields are now populated. This phase
> stands up the first **PostgreSQL→Neo4j projection** (instance-level nodes +
> explicit FK relationships, with mandatory Graph Provenance per ADR 0005) and the
> **Cypher side of the read-only guardrails**, reusing the `ValidationResult`
> contract built for SQL in Phase 04. It does **not** touch Qdrant, Event Nodes, an
> LLM, or the Query Router.

---

## Objective

Stand up the graph-only branch of the agentic query system so that:

- there is a reusable **projection pipeline** that copies trusted ERP facts from
  PostgreSQL into the **ERP Domain Graph** as instance-level nodes and **Explicit
  Graph Relationships** (from foreign keys), attaching **Graph Provenance** to
  every node and relationship (ADR 0005),
- there is a reusable **read-only Cypher execution path** to Neo4j that no caller
  can use to mutate the graph (guardrails enforced in code, not prompts — ADR 0009),
- there is a code-level **Cypher validator** that accepts read-only traversal
  Cypher against an allowlist of node labels and relationship types and rejects
  everything else, returning **structured validation results** that reuse the same
  `ValidationResult` model that appears in `answer_trace`,
- the **Supplier→Product** ladder question is answered by traversing
  `(:Supplier)-[:SUPPLIES]->(:Product)` in Neo4j, **computed at query time**,
- every answer returns the structured **`answer_trace`** (ADR 0003) with the
  graph-only subset populated (`route`, `generated_cypher`, `graph_paths`,
  `metrics`, `validation_results`, `provenance`),
- the step is exposed both as a **callable service function** (testable) and a
  thin **FastAPI endpoint** that returns an inspectable `answer_trace`,
- the step has a stored **expected answer spec** (behavioral) and can persist its
  **actual `answer_trace`** so failures localize to projection vs. validation vs.
  execution vs. synthesis.

**Query ladder:** this is **Step 2** of the progressive query ladder
(Step 1 SQL-only → … → Step 5 Golden Query). It proves the **graph layer in
isolation** before composing it with SQL and vector routes. The LangGraph router
and LLM-generated Cypher are **later phases** — here the route is fixed to
`graph_only` and the Cypher is built deterministically.

**Issue coverage:** this phase deliberately combines `docs/ISSUES.md` **Issue 4**
(Neo4j supplier-to-product traversal ladder step) with the **Cypher side** of
**Issue 5** (read-only Cypher guardrails). Phase 04 already delivered the SQL
side of Issue 5. Keeping the Cypher guardrails in this phase ensures Step 2 uses
the same governed validation -> execution -> `answer_trace` path that later
LLM-generated Cypher must use, instead of introducing an ungoverned graph
execution shortcut.

---

## Prerequisites

- **Phase 04 complete and verified.** `backend/query/` holds the SQL validator,
  executor, and the full `answer_trace` schema (`backend/query/trace.py`); the
  SQL-only Top Customers step works and `pytest` / `ruff check .` are clean.
- **Phase 02/03 complete.** `erp_core.suppliers` and `erp_core.products` hold the
  base Northwind suppliers and products, with the foreign key
  `erp_core.products.supplier_id → erp_core.suppliers(supplier_id)`. **Tokyo
  Traders** exists (`supplier_id = 4`).
- `backend.config.get_settings()` exposes `neo4j_uri`, `neo4j_user`,
  `neo4j_password` and `postgres_dsn` (both reused here).
- **Neo4j is running** via `docker compose up -d neo4j` (Neo4j 5 Community,
  bolt on `7687`, Browser on `http://localhost:7474`), and `NEO4J_PASSWORD` is set
  in `.env`. The `/health` Neo4j check returns `available: true`.
- `neo4j>=5.20` is already in `pyproject.toml` dependencies (no new dependency
  required for this phase).

---

## Design decisions (read before implementing)

These are binding for this phase. They mirror the "document the decision" pattern
from earlier phases.

1. **Deterministic Cypher, no LLM yet.** Step 2 builds the Supplier→Product Cypher
   with a small parameterized builder, not text-to-Cypher. Rationale: the ladder
   proves one layer at a time; Step 2 proves the *projection + governed Cypher path
   + validator + trace* deterministically and testably. **However**, the validator
   must treat the Cypher as if it were untrusted/generated (full allowlist +
   read-only checks), so the exact same path is ready when LLM-generated Cypher
   arrives in a later phase. (Same stance as Phase 04's deterministic SQL.)

2. **Minimal projection scope, extensible engine.** Project **only** `Supplier`,
   `Product`, and the `SUPPLIES` relationship — the entities Step 2 actually
   queries. Do **not** project Customer/Order/Shipment/Contract here; later phases
   (06+) register them. The projection module must be structured so adding an
   entity later is *adding a projector function*, not rewriting the engine. There
   is no separate "massive projection" event — the graph grows with the ladder.

   For Phase 05, each node carries only the business properties needed by Step 2
   plus identity and Graph Provenance. This is a ladder-scope constraint, not the
   final production shape: a later dedicated graph-enrichment phase should expand
   the ERP Domain Graph toward **Full Graph Projection**: projecting all relevant
   instance-level entities, explicit foreign-key relationships, and business
   properties from the Operational Source of Truth into Neo4j. Use **business
   properties**, not "features", for instance attributes in graph documentation to
   avoid confusion with ML feature engineering.

3. **Explicit relationships only, from foreign keys.** `SUPPLIES` is an **Explicit
   Graph Relationship** copied directly from the trusted FK
   `products.supplier_id`. **No derived relationships, no inference, no LLM
   guesses** in this phase (ADR 0012 / CONTEXT.md). Derived relationships and Event
   Nodes are Phase 06.

4. **Graph Provenance is mandatory on every node and relationship** (ADR 0005).
   Direct projections record at least: `source_system`, `source_schema`,
   `source_table`, `source_pk`, `projection_version`, `rule_name`, and
   `rule_version`. Use `supplier_projection` / `v1` for `Supplier`,
   `product_projection` / `v1` for `Product`, and
   `supplier_to_product_projection` / `v1` for `SUPPLIES`. The `SUPPLIES`
   relationship also records the source table/column it was derived from. No node
   or relationship may be created without provenance.
   `projection_version` is the version of the Neo4j projection contract
   (labels, relationship types, property mapping, and required provenance shape).
   `rule_version` is the version of the specific projection or derivation rule
   named by `rule_name`. In Phase 05 both are `v1`, but they are intentionally
   distinct.
   For `SUPPLIES`, `source_pk` is the `product_id` of the `erp_core.products`
   row that contains the `supplier_id` foreign key, and `source_column` is
   `supplier_id`.

5. **Idempotent projection.** Use `MERGE` (not `CREATE`) keyed on the natural
   instance id (`supplier_id`, `product_id`) so re-running the projection updates
   in place and never duplicates. The projection is the **only** code allowed to
   write to Neo4j; everything else is read-only.

6. **Cypher guardrails via code allowlist + engine parser + server read-mode.**
   There is no mature `sqlglot` equivalent for Cypher in Python. Enforce read-only
   with **defense in depth**: (a) a code-level keyword/structure check
   (block `CREATE/MERGE/DELETE/SET/REMOVE/DETACH` and all `CALL` usage in Phase
   05; label and
   relationship allowlist; path-depth and row caps), (b) `EXPLAIN <cypher>` so
   Neo4j's **own parser/planner** validates the query without executing it, and
   (c) run the actual query in a **READ access-mode** transaction so the **server**
   physically refuses writes. Do **not** add a third-party Cypher parser dependency
   in this phase. `validate_cypher()` is an offline/static validator and must not
   require a live Neo4j connection; `run_validated_cypher()` performs the
   mandatory `EXPLAIN` immediately before execution and fails closed if Neo4j
   rejects the query.

7. **Reuse the `ValidationResult` contract.** The Cypher validator returns the same
   `backend.query.validator.ValidationResult` model used for SQL (with
   `statement_type`, `referenced_*`, `violations`, `effective_sql` holding the
   effective Cypher). This keeps `answer_trace.validation_results` uniform across
   routes. Reuse `QueryMetrics` from `backend/query/executor.py` for metrics.

8. **Route is asserted, not classified.** For Step 2 the route is hard-set to
   `graph_only`. Do **not** build the router here; just record the route in the
   trace so the eval harness can later compare expected vs. actual route.

---

## Functional requirements

After this phase the system MUST:

1. Provide a **projection pipeline** that reads `erp_core.suppliers` and
   `erp_core.products` from PostgreSQL and creates, in Neo4j: `(:Supplier)` and
   `(:Product)` instance nodes and `(:Supplier)-[:SUPPLIES]->(:Product)`
   relationships, each carrying Graph Provenance. Re-running it is idempotent.
2. Provide a `cypher_validator` that, given a Cypher string and a policy, returns a
   structured `ValidationResult` with: `allowed: bool`, `statement_type`,
   `referenced_schemas` (graph: node labels), `referenced_tables` (graph:
   relationship types), `violations: list[str]`, and the `effective_sql` actually
   sent to the database (here the effective Cypher, e.g. with an enforced row cap).
3. Reject, with explanatory violations: any Cypher containing a write clause
   (`CREATE`, `MERGE`, `DELETE`, `DETACH DELETE`, `SET`, `REMOVE`, `CALL {…}`
   subqueries that write, `LOAD CSV`, schema/index/constraint commands); any
   reference to a node label outside the label allowlist (`Supplier`, `Product`);
   any reference to a relationship type outside the relationship allowlist
   (`SUPPLIES`); path traversals deeper than the configured depth limit; queries
   that fail Neo4j `EXPLAIN`.
4. Accept representative read-only traversal queries against the allowlist and
   enforce a maximum returned-row cap (configurable; default 1000).
5. Provide a `cypher_executor` that runs only validated Cypher inside a **READ
   access-mode transaction** with a **transaction timeout**, returning records +
   execution metrics (`row_count`, `duration_ms`) and the traversed `graph_paths`,
   and that refuses (or fails closed) on any attempt to run unvalidated or mutating
   Cypher.
6. Answer **Supplier→Product**: return the products supplied by **Tokyo Traders**
   by traversing `(:Supplier {company_name})-[:SUPPLIES]->(:Product)`, computed at
   query time. The set MUST match a direct PostgreSQL read-back of
   `products WHERE supplier_id = (suppliers WHERE company_name = 'Tokyo Traders')`.
7. Return a structured `answer_trace` (ADR 0003 full shape) for the answer, with
   `route = "graph_only"`, the `generated_cypher`, the `validation_results`,
   `metrics` (keyed `"neo4j"`), `graph_paths`, and `provenance` (the source ERP
   tables and the `rule_name`/`rule_version` used). SQL/vector fields stay empty.
8. Expose the step via FastAPI (`GET /ladder/supplier-products`) returning the
   answer **and** its `answer_trace`, plus a callable service function for tests.
9. Store an **expected answer spec** (behavioral) for Step 2 and be able to persist
   the **actual `answer_trace`** to a file for inspection/evaluation.

---

## Technical requirements

### Projection (PostgreSQL → Neo4j)
- New package `backend/graph/`. A `connection.py` opens a Neo4j driver from
  `get_settings()` (reusing the same config as the health check), with a small
  context-managed helper.
- `projection.py` exposes one projector function per entity plus a single
  `project_all(settings)` entrypoint that, for Phase 05, wires **only** suppliers,
  products, and the `SUPPLIES` relationship. Read source rows with `psycopg`
  (reuse `postgres_dsn`); write nodes/relationships with the Neo4j driver.
- **Node identity:** `MERGE (:Supplier {supplier_id})` and
  `MERGE (:Product {product_id})`; set descriptive properties (`company_name`,
  `product_name`, …) and provenance on create/update.
- **Relationship:** `MATCH` the two endpoints by id, then
  `MERGE (s)-[r:SUPPLIES]->(p)` and set provenance on `r`.
- Keep `supplier_id` on `Product` as a source/debug business property in Phase 05,
  while treating `(:Supplier)-[:SUPPLIES]->(:Product)` as the authoritative graph
  traversal. The Supplier->Product ladder answer must not be implemented by
  filtering on `Product.supplier_id`.
- **Provenance properties** (ADR 0005) on every node and relationship:
  `source_system = "postgresql"`, `source_schema = "erp_core"`,
  `source_table` (`"suppliers"` / `"products"`), `source_pk` (the id),
  `projection_version` (e.g. `"v1"`), `rule_name`, and `rule_version`. Use
  `supplier_projection` / `v1` for `Supplier`, `product_projection` / `v1` for
  `Product`, and `supplier_to_product_projection` / `v1` for `SUPPLIES`. The
  `SUPPLIES` relationship additionally records that it derives from
  `products.supplier_id`, with `source_pk = product_id` and
  `source_column = "supplier_id"`.
- Idempotent: `MERGE` keyed on the id; re-running must not duplicate.
- Exposed as a CLI: `python -m backend.graph.projection` (optionally
  `--reset` to clear the Phase 05 projection first, guarded so it only deletes
  allowlisted graph elements: `(:Supplier)-[:SUPPLIES]->(:Product)`,
  `(:Supplier)`, and `(:Product)`. Do not implement a global
  `MATCH (n) DETACH DELETE n` reset.

### Cypher validator (ADR 0009 — Cypher side)
- `backend/graph/cypher_validator.py`. Reuse
  `backend.query.validator.ValidationResult`. A `CypherPolicy` (frozen dataclass)
  holds: allowed labels (`{"Supplier", "Product"}`), allowed relationship types
  (`{"SUPPLIES"}`), `max_rows` (default 1000), `max_depth` (default e.g. 4).
- Layer 1 — **code guardrail:** reject any write keyword
  (`CREATE|MERGE|DELETE|SET|REMOVE|DETACH|LOAD CSV|CREATE INDEX|DROP|CALL { … }`
  that writes). Extract referenced labels (`:Label`) and relationship types
  (`[:REL]`) and enforce the allowlists. Reject variable-length paths exceeding
  `max_depth`. Cap/inject a trailing `LIMIT` ≤ `max_rows` into the effective
  Cypher (mirror the SQL `_cap_sql` approach).
- Layer 2 — **engine parse:** the executor (or the validator) runs
  `EXPLAIN <effective_cypher>` so Neo4j parses/plans without executing; a parse
  failure becomes a `violation` (`explain_failed: …`), never an exception.
- Result is the Pydantic `ValidationResult` so it serializes directly into
  `answer_trace.validation_results`. Map graph concepts onto the existing fields:
  `referenced_schemas` = node labels, `referenced_tables` = relationship types,
  `statement_type` = `"READ"`.

Clarification: despite the wording above, Phase 05 keeps `validate_cypher()`
offline/static. `EXPLAIN` belongs to `run_validated_cypher()` and is mandatory
immediately before live execution. Validator unit tests must not require Neo4j;
executor/integration tests cover Neo4j parse/planning failures and must surface
them as controlled failures.

Phase 05 also blocks all `CALL` usage, including read-only-looking procedures.
Procedure allowlisting is deferred until a later phase has a concrete need for it.

### Cypher executor (read-only path)
- `backend/graph/cypher_executor.py`. One driver session per call. Per call:
  - Refuse to run when `validation_result.allowed` is `False` or `effective_sql`
    is empty (fail closed — same guard as the SQL executor).
  - Run inside a **READ access-mode** managed transaction
    (`session.execute_read(...)` / `default_access_mode=READ`) with a
    **transaction timeout** (default 5000 ms) — defense in depth: a READ
    transaction physically cannot mutate the graph.
  - Run `EXPLAIN` first (Layer 2), then execute the query.
  - Return records + `metrics` (`QueryMetrics(row_count, duration_ms)`) + the
    `graph_paths` (a serializable list of dicts describing the concrete traversed
    supplier node, `SUPPLIES` relationship, and product node). Each path entry
    must include business identity/display fields plus essential Graph Provenance
    for the supplier node, relationship, and product node, so each answer row is
    auditable back to the exact graph elements used.
- Define a small `GraphExecutionResult` (Pydantic) analogous to
  `QueryExecutionResult`: `records: list[dict]`, `graph_paths: list[dict]`,
  `metrics: QueryMetrics`.
- Define a small application exception, `CypherExecutionError`, for controlled
  executor failures. If Neo4j rejects `EXPLAIN <effective_cypher>`, raise
  `CypherExecutionError("explain_failed:<message>")` instead of leaking a raw
  driver exception. The executor still raises `ValueError` when asked to run a
  failed or empty `ValidationResult`.

### Ladder Step 2 (`backend/ladder/supplier_products.py`)
- Mirror `backend/ladder/top_customers.py` in shape. A deterministic Cypher
  template, parameterized by company name:
  ```cypher
  MATCH (s:Supplier {company_name: $company_name})-[r:SUPPLIES]->(p:Product)
  RETURN
    s.supplier_id AS supplier_id,
    s.company_name AS supplier_name,
    properties(s) AS supplier_properties,
    type(r) AS relationship_type,
    properties(r) AS relationship_properties,
    p.product_id AS product_id,
    p.product_name AS product_name,
    properties(p) AS product_properties
  ORDER BY p.product_name
  ```
  Default `$company_name = "Tokyo Traders"`.
- Flow: `build_supplier_products_cypher()` → `validate_cypher()` →
  `run_validated_cypher()` → assemble `AnswerTrace`. Note the Cypher is assembled
  from **trusted constants/parameters** (no user input) and still passed through
  the validator — the governed path is identical to the future LLM-generated case.
- The query must return supplier fields, relationship type/properties, and product
  fields explicitly so `graph_paths` is built from the actual traversal result,
  not inferred from product-only rows or fetched through a second query.
- `answer_trace`: `route = QueryRoute.GRAPH_ONLY`, `generated_cypher` =
  effective Cypher, `metrics = {"neo4j": metrics}`, `validation_results =
  [validation]`, `graph_paths` populated, and `provenance` = entries for the
  `erp_core.suppliers` and `erp_core.products` source tables with
  `rule_name = "supplier_to_product_projection"`, `rule_version = "v1"`.
- The public `answer` contains only business product rows
  (`product_id`, `product_name`). Supplier details, relationship metadata,
  provenance, generated Cypher, validation, and metrics belong in
  `answer_trace`, not in the top-level answer.
- `answer_supplier_products()` must not call `project_all()` or perform any graph
  writes. Projection is an explicit setup/update step (`python -m
  backend.graph.projection`); the ladder answer path is read-only and assumes the
  Knowledge Layer has already been projected.
- If the Cypher validates and executes successfully but returns no rows, the API
  may return `200` with an empty `answer`. For the Step 2 ladder evaluation,
  however, an empty Tokyo Traders result is a failure because it does not match
  the PostgreSQL read-back for `supplier_id = 4`.
- CLI `--emit-trace` writing
  `evaluation/answer_traces/step02_supplier_products.json` (like Step 1).

### API & packaging
- Add `GET /ladder/supplier-products` to `backend/ladder/router.py` (reuse the
  existing `APIRouter(prefix="/ladder")`, `Depends(get_settings)`); it returns
  `{"answer": [...], "answer_trace": {...}}`.
- No `main.py` change needed beyond the already-mounted ladder router.
- Keep ruff clean (`select = ["E","F","I","UP","B"]`); 88-col lines; `snake_case`
  for modules/functions, `PascalCase` for node labels.
- Update `README.md` with the Phase 05 run path, including starting Neo4j,
  running the explicit graph projection command, and emitting the Step 2 trace:
  `docker compose up -d neo4j`, `python -m backend.graph.projection`, and
  `python -m backend.ladder.supplier_products --emit-trace`.

### Evaluation artifacts
- `evaluation/ladder/step02_supplier_products.spec.json` — the **expected answer
  spec** (behavioral; see Acceptance). Declarative, not a pinned product list.
- Persist the **actual** trace to
  `evaluation/answer_traces/step02_supplier_products.json` (regenerable sample).

---

## File structure

```text
test-project/
├─ backend/
│  ├─ graph/                          # NEW: Neo4j / Cypher governance spine
│  │  ├─ __init__.py
│  │  ├─ connection.py                # Neo4j driver helper from get_settings()
│  │  ├─ projection.py                # PG→Neo4j projection (+CLI), provenance, idempotent
│  │  ├─ cypher_validator.py          # Cypher guardrails (ADR 0009) → ValidationResult
│  │  └─ cypher_executor.py           # read-only Cypher path (READ tx, timeout, metrics)
│  ├─ query/                          # (from Phase 04) ValidationResult, QueryMetrics, trace
│  └─ ladder/
│     ├─ constants.py                 # (optional) add TOP_SUPPLIER company default
│     ├─ supplier_products.py         # build Cypher → validate → execute → assemble trace (+CLI)
│     └─ router.py                    # + GET /ladder/supplier-products
├─ evaluation/
│  ├─ ladder/
│  │  └─ step02_supplier_products.spec.json   # expected answer spec (behavioral)
│  └─ answer_traces/
│     └─ step02_supplier_products.json        # persisted actual trace (regenerable sample)
└─ tests/
   ├─ test_graph_projection.py        # idempotent projection, nodes/rels + provenance present
   ├─ test_cypher_validator.py        # accepts read-only / rejects mutations & bad labels/rels
   └─ test_ladder_supplier_products.py # traversal correctness, route, trace shape, endpoint
```

---

## Implementation guidance

### Neo4j connection (`backend/graph/connection.py`)

```python
from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator

from neo4j import Driver, GraphDatabase

from backend.config import Settings, get_settings


@contextmanager
def neo4j_driver(settings: Settings | None = None) -> Iterator[Driver]:
    settings = settings or get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        yield driver
    finally:
        driver.close()
```

### Projection (`backend/graph/projection.py`)

```python
PROJECTION_VERSION = "v1"

SUPPLIER_MERGE = """
MERGE (s:Supplier {supplier_id: $supplier_id})
SET s.company_name = $company_name,
    s.source_system = 'postgresql', s.source_schema = 'erp_core',
    s.source_table = 'suppliers', s.source_pk = $supplier_id,
    s.projection_version = $version
"""

PRODUCT_MERGE = """
MERGE (p:Product {product_id: $product_id})
SET p.product_name = $product_name,
    p.source_system = 'postgresql', p.source_schema = 'erp_core',
    p.source_table = 'products', p.source_pk = $product_id,
    p.projection_version = $version
"""

SUPPLIES_MERGE = """
MATCH (s:Supplier {supplier_id: $supplier_id})
MATCH (p:Product {product_id: $product_id})
MERGE (s)-[r:SUPPLIES]->(p)
SET r.source_system = 'postgresql', r.source_schema = 'erp_core',
    r.source_table = 'products', r.source_column = 'supplier_id',
    r.source_pk = $product_id,
    r.rule_name = 'supplier_to_product_projection',
    r.rule_version = $version, r.projection_version = $version
"""
# project_suppliers / project_products / project_supplies read rows via psycopg
# and run the MERGEs; project_all(settings) wires the three for Phase 05.
```

> Provenance is set on **every** node and relationship (ADR 0005). `MERGE` keeps it
> idempotent. Adding `Order`/`Shipment` later = adding more projector functions and
> wiring them into `project_all` — the engine does not change.

### Cypher validator (`backend/graph/cypher_validator.py`)

```python
from backend.query.validator import ValidationResult
# CypherPolicy(frozen): allowed_labels={"Supplier","Product"},
#   allowed_rels={"SUPPLIES"}, max_rows=1000, max_depth=4
#
# validate_cypher(cypher, policy=None, max_rows=None) -> ValidationResult:
#   - reject write keywords (CREATE/MERGE/DELETE/SET/REMOVE/DETACH/LOAD CSV/…)
#   - extract :Labels and [:REL_TYPES]; enforce allowlists
#   - reject variable-length paths deeper than max_depth
#   - cap/inject a trailing LIMIT <= max_rows into effective cypher
#   - returns ValidationResult(allowed, statement_type="READ",
#       referenced_schemas=sorted(labels), referenced_tables=sorted(rels),
#       violations=[...], effective_sql=effective_cypher if not violations else None)
```

### Cypher executor (`backend/graph/cypher_executor.py`)

```python
import time
import neo4j
from pydantic import BaseModel, Field

from backend.query.executor import QueryMetrics
from backend.query.validator import ValidationResult
from backend.graph.connection import neo4j_driver

DEFAULT_TIMEOUT_MS = 5000


class GraphExecutionResult(BaseModel):
    records: list[dict] = Field(default_factory=list)
    graph_paths: list[dict] = Field(default_factory=list)
    metrics: QueryMetrics


def run_validated_cypher(validation, params=None, settings=None,
                         timeout_ms=DEFAULT_TIMEOUT_MS) -> GraphExecutionResult:
    if not validation.allowed or not validation.effective_sql:
        raise ValueError("refusing to execute Cypher that failed validation")
    cypher = validation.effective_sql
    with neo4j_driver(settings) as driver:
        with driver.session(default_access_mode=neo4j.READ_ACCESS) as session:
            session.run(f"EXPLAIN {cypher}", params or {}).consume()  # engine parse
            start = time.perf_counter()
            result = session.run(cypher, params or {})
            records = [r.data() for r in result]
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
    # assemble graph_paths from records; build QueryMetrics(row_count, duration_ms)
```

> READ access mode is the Neo4j equivalent of Phase 04's read-only transaction:
> the **server** refuses writes regardless of our code. `EXPLAIN` uses Neo4j's own
> parser as the reliable syntax/structure oracle. (Use a transaction timeout per
> the driver API; keep the read-only guarantee.)

### Endpoint (`backend/ladder/router.py`)
- Add `GET /ladder/supplier-products` calling `answer_supplier_products(settings)`
  and returning the `{answer, answer_trace}` response model.

### Verification via Neo4j Browser + read-back
After projecting, open `http://localhost:7474` and run
`MATCH (s:Supplier)-[:SUPPLIES]->(p:Product) RETURN s,p` to visually confirm the
graph. Then compare the API/function output against a direct PostgreSQL
`SELECT product_id, product_name FROM erp_core.products WHERE supplier_id = 4` —
the product sets must match exactly.

---

## Acceptance criteria

This phase is complete when **all** of the following hold:

- [ ] `docker compose up -d neo4j` is running; `/health` Neo4j check returns
      `available: true`. No new dependency added to `pyproject.toml`.
- [ ] **Projection** creates `(:Supplier)` and `(:Product)` nodes and
      `(:Supplier)-[:SUPPLIES]->(:Product)` relationships for the base ERP data;
      **every** projected node and relationship carries Graph Provenance
      (`source_system`, `source_schema`, `source_table`, `source_pk`/`source_column`,
      `projection_version`). Tokyo Traders (`supplier_id = 4`) is present.
- [ ] **Projection is idempotent**: running it twice yields the same node/rel
      counts (a test asserts no duplication).
- [ ] **Cypher validator accepts** a representative read-only traversal over the
      allowlist and returns `allowed: True` with an `effective_sql` (effective
      Cypher) carrying an enforced `LIMIT`.
- [ ] **Cypher validator rejects** (with explanatory `violations`): `CREATE`,
      `MERGE`, `DELETE`, `DETACH DELETE`, `SET`, `REMOVE`, a non-allowlisted label
      (e.g. `:Customer`), a non-allowlisted relationship type, and a path deeper
      than the depth limit.
- [ ] **Cypher executor** runs only validated Cypher inside a READ access-mode
      transaction with a timeout, returns records + `metrics`, and raises/refuses
      on unvalidated input. A test proves a mutation cannot pass through
      (validation fails closed and/or the READ transaction rejects a write).
- [ ] **Supplier→Product** returns the products supplied by Tokyo Traders, ordered
      by product name. The set **matches the PostgreSQL read-back**
      (`products WHERE supplier_id = 4`) exactly.
- [ ] **`answer_trace`** validates against the full Pydantic schema with
      `route == "graph_only"`, populated `generated_cypher`, `validation_results`,
      `metrics` (keyed `"neo4j"`), `graph_paths`, and `provenance`; SQL/vector
      fields present but empty.
- [ ] `GET /ladder/supplier-products` returns `200` with `answer` + `answer_trace`
      (test may skip if Neo4j is unconfigured, like the Phase 03/04 fixtures).
- [ ] Unit tests for `validate_cypher()` run without Neo4j. Live projection,
      executor, and ladder tests skip with a clear reason when Neo4j is
      unconfigured or unreachable, and run normally when the dev stack is
      available.
- [ ] The **expected answer spec** for Step 2 is stored under `evaluation/ladder/`
      and encodes behavioral expectations (route, non-empty product set, ordering,
      read-only validation passed, provenance present) — **not** a pinned product
      list.
- [ ] The step can **persist its actual `answer_trace`** to
      `evaluation/answer_traces/step02_supplier_products.json`.
- [ ] `pytest` and `ruff check .` are clean. All new code is committed.

---

## Out of scope (do NOT do in this phase)

- **Event Nodes** (`ShipmentDelayEvent`, `CustomerComplaintEvent`, …) and any
  **derived / plausible relationships** (`POSSIBLY_RELATED_TO`) — **Phase 06**.
  Only the explicit FK-based `SUPPLIES` relationship ships here.
- **Projecting Customer/Order/Shipment/Contract or any other entity** — later
  phases register them; the engine is built extensible but stays minimal now.
- **Qdrant**, embeddings, chunking, document retrieval — **Phase 07**. The
  `answer_trace` vector fields stay empty.
- **LangGraph Query Router / route classification** — **Phase 08**. Here the route
  is hard-set to `graph_only`.
- **LLM text-to-Cypher** or any LLM/OpenRouter/HF/Ollama call — later. The Cypher
  is built from trusted constants/parameters and still validated.
- **A third-party Cypher parser dependency** — use `EXPLAIN` + code guardrails +
  READ mode instead.
- **Schema changes / migrations / new PostgreSQL data** — Phase 05 reads the
  existing Phase 02/03 database. If a need reveals a schema gap, stop and raise it.
- **Auth / deployment hardening / polished frontend** — out of scope for Milestone 1.

---

## References

- `CLAUDE.md` → invariants #1 (data/knowledge boundary; Neo4j = Knowledge Layer,
  instance-level nodes), #2 (Graph Provenance mandatory), #3 (explicit vs derived
  relationships; explicit from FKs here), #5 (guardrails in code, not prompts), #6
  (`answer_trace` mandatory), #7 (routing explicit; GraphRAG for traversal).
- `CONTEXT.md` → `ERP Domain Graph`, `Knowledge Layer`, `Graph Provenance`,
  `Explicit Graph Relationship` (use these exact terms; avoid the rejected synonyms).
- `docs/adr/0002-*` — route types (the `graph_only` route).
- `docs/adr/0003-*` — the `answer_trace` contract (graph fields populated here).
- `docs/adr/0004-*` — Event Nodes live only in Neo4j (relevant to what is deferred).
- `docs/adr/0005-*` — graph/provenance traceability (provenance on nodes/rels).
- `docs/adr/0009-*` — code-level query guardrails (Cypher read-only, label/rel
  allowlists, depth/row limits; validation results returnable in `answer_trace`).
- `docs/ISSUES.md` → **Issue 4** (Neo4j supplier-to-product traversal ladder step)
  and **Issue 5 (Cypher side)** (read-only Cypher guardrails) — both delivered here.
- `docs/PRD.md` → user stories 4, 12, 13, 14, 18, 27, 30, 31, 32, 36; testing
  decisions (ladder expected-answer specs + persisted actual `answer_trace`;
  validator rejects mutation Cypher / accepts read-only; provenance traceable).
- `Project_Idea.md` §6 Step 2 ("Which products does Tokyo Traders supply?") and
  §11 (instance-level projection from PostgreSQL to Neo4j).
- `directives/phase-04-sql-only-top-customers-ladder-step.md` — the governed-path
  pattern (validator → executor → trace) this phase mirrors for Cypher, and the
  `ValidationResult` / `QueryMetrics` / `AnswerTrace` contracts it reuses.
```
