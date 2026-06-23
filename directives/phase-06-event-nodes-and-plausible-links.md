# Phase 06 — Event Nodes & Plausible Links / Query Ladder Step 3: graph-only Shipment Delays

> Macro phase 6 of the NorthwindAI build. Delivers the **third query ladder step
> end-to-end**: answer *"Which Tokyo Traders orders had delays?"* against the
> **Knowledge Layer (Neo4j)** by traversing the readable multi-hop path
> `Supplier → Product → Order → Shipment → ShipmentDelayEvent`, through the same
> **governed, read-only Cypher path** (validator → executor → `answer_trace`) built in
> Phase 05. This phase also stands up the **core of the Knowledge Layer**: the first
> **Event Nodes** (`ShipmentDelayEvent`, `CustomerComplaintEvent`) — born **only in
> Neo4j** (ADR 0004) — and the first **Derived / Plausible Relationship**
> (`POSSIBLY_RELATED_TO`) linking shipment delays to customer complaints **without
> claiming causality** (ADR 0012). It extends the PostgreSQL→Neo4j projection to the
> entities the path needs (Customer, Order, Shipment) and the Cypher allowlist to the
> new labels/relationships. It does **not** touch Qdrant, ContractTermEvents, an LLM, or
> the Query Router.

---

## Objective

Grow the graph-only branch of the agentic query system from a single explicit
relationship (Phase 05) into the **event-aware Knowledge Layer** the Golden Query
depends on, so that:

- the projection pipeline is **extended** with the explicit, FK-based instance nodes and
  relationships the delay path needs — `Customer`, `Order`, `Shipment`, and the explicit
  links `PLACED`, `CONTAINS`, `FULFILLED_BY` — each carrying **Graph Provenance**
  (ADR 0005), built by **adding projector functions**, not rewriting the engine
  (the extensibility promised in Phase 05),
- a new class of pipeline — **derivers** — produces **derived knowledge born in Neo4j**:
  `ShipmentDelayEvent` nodes (from the `shipments.delay_days` fact) and
  `CustomerComplaintEvent` nodes (from `erp_docs.customer_communications`), **never
  materialized in PostgreSQL** (ADR 0004),
- a controlled, rule-based pipeline creates the **Plausible Relationship**
  `(:ShipmentDelayEvent)-[:POSSIBLY_RELATED_TO]->(:CustomerComplaintEvent)` carrying
  `confidence`, `matching_reason`, `time_window_days`, and `evidence` — **never** a
  causal relationship name (ADR 0012),
- the **Shipment Delays** ladder question is answered by traversing
  `(:Supplier)-[:SUPPLIES]->(:Product)<-[:CONTAINS]-(:Order)-[:FULFILLED_BY]->(:Shipment)-[:HAS_DELAY_EVENT]->(:ShipmentDelayEvent)`
  in Neo4j, **computed at query time**,
- every answer returns the structured **`answer_trace`** (ADR 0003) with the graph-only
  subset populated (`route`, `generated_cypher`, `graph_paths`, `metrics`,
  `validation_results`, `provenance`),
- the step is exposed both as a **callable service function** (testable) and a thin
  **FastAPI endpoint** that returns an inspectable `answer_trace`,
- the step has a stored **expected answer spec** (behavioral) and can persist its actual
  `answer_trace`, and the new event/link knowledge is proven against the **Controlled
  Scenarios** (positive case + false-positive traps) seeded in Phase 03.

**Query ladder:** this is **Step 3** of the progressive query ladder
(Step 1 SQL-only → Step 2 graph-only traversal → **Step 3 graph-only events** → Step 4
graph+vector → Step 5 Golden Query). It proves **derived knowledge and plausible
relationships in isolation** before composing them with vector retrieval and routing. The
LangGraph router and LLM-generated Cypher remain later phases — here the route is fixed to
`graph_only` and the Cypher is built deterministically.

**Issue coverage:** this phase deliberately combines `docs/ISSUES.md` **Issue 6**
(shipment delay Event Node ladder step) and **Issue 7** (CustomerComplaintEvent +
plausible delay-to-complaint links). They are one coherent theme — *Event Nodes and
derived/plausible relationships* — and Issue 7 is `Blocked by` Issue 6, so building them
together delivers the full event core in a single governed pass instead of splitting a
tightly-coupled concern across two phases.

---

## Prerequisites

- **Phase 05 complete and verified.** `backend/graph/` holds `connection.py`,
  `projection.py` (suppliers/products/`SUPPLIES`), `cypher_validator.py`, and
  `cypher_executor.py`; the graph-only Supplier→Product step works and
  `pytest` / `ruff check .` are clean. The validation contract is the post-refactor
  split: `SqlValidationResult` / `CypherValidationResult` behind the `ValidationResult`
  Protocol (`backend/query/validation.py`), held in `answer_trace.validation_results` as a
  `dialect`-discriminated union.
- **Phase 02/03 complete.** The Operational Source of Truth already contains everything
  this phase reads (no schema or data work here):
  - `erp_core.orders`, `erp_core.order_details`, `erp_core.customers`, `erp_core.products`,
    `erp_core.suppliers`.
  - `erp_core.shipments` with `order_id`, `expected_delivery_date`,
    `actual_delivery_date`, and the generated `delay_days` column (the source fact for
    `ShipmentDelayEvent`).
  - `erp_docs.customer_communications` with `customer_id`, `order_id`, `product_id`,
    `contact_reason`, `body`, `sentiment`, `occurred_at` (the source for
    `CustomerComplaintEvent`).
  - The **Controlled Scenarios** asserted by `data_generation/scenarios.py`:
    **A** — Tokyo Traders (`supplier_id = 4`) shipment delays to **top customers** in Q4
    2025 **with** delay-related complaints (the positive Golden-Query case);
    **B** — `supplier_id = 1` delays to **non-top** customers (delay-but-not-top trap);
    **C** — `supplier_id = 7` to top customers with **no delays** and complaints
    **unrelated** to delays (complaint-but-not-from-delay trap).
- **Neo4j is running** (`docker compose up -d neo4j`) and the Phase 05 projection has been
  applied; `/health` Neo4j check returns `available: true`. No new Python dependency is
  required for this phase.

---

## Design decisions (read before implementing)

These are binding for this phase. They continue the "document the decision" pattern.

1. **Deterministic Cypher, no LLM yet.** Step 3 builds its Cypher with a small
   parameterized builder, not text-to-Cypher. The validator must still treat the Cypher as
   if it were untrusted/generated (full allowlist + read-only checks), so the exact same
   governed path is ready when LLM-generated Cypher arrives later. (Same stance as Phases
   04/05.)

2. **Two families of pipeline: projectors vs derivers.** Keep the data/knowledge boundary
   explicit in code structure (invariant #1, #3):
   - **Projectors** copy *trusted ERP facts* into the graph as instance nodes and
     **Explicit Graph Relationships** straight from foreign keys (Customer, Order,
     Shipment; `PLACED`, `CONTAINS`, `FULFILLED_BY`). No inference.
   - **Derivers** produce *derived knowledge born in Neo4j* via controlled rules
     (`ShipmentDelayEvent`, `CustomerComplaintEvent`, `POSSIBLY_RELATED_TO`). They read
     PostgreSQL facts but the resulting nodes/links exist **only in Neo4j** and must
     **never** be written back to PostgreSQL (ADR 0004).

3. **Event Nodes live only in Neo4j (ADR 0004).** `ShipmentDelayEvent` and
   `CustomerComplaintEvent` are derived in Neo4j from operational facts. Do not add event
   tables/columns to PostgreSQL. A test must assert the event types do not exist as PG
   tables.

4. **Plausible, not causal (ADR 0012).** The delay→complaint link is named
   `POSSIBLY_RELATED_TO` and carries `confidence`, `matching_reason`, `time_window_days`,
   and `evidence`. No relationship name may imply proven cause (`CAUSED`, `CAUSED_BY`,
   `BECAUSE_OF`, …). The link is created by a **controlled rule**, never a raw LLM/heuristic
   guess (invariant #3).

5. **Readable multi-hop path, no shortcut edges (invariant #3).** The delay answer
   traverses `Supplier → Product → Order → Shipment → ShipmentDelayEvent`. Do **not**
   introduce a shortcut edge such as `(:Supplier)-[:HAD_DELAY]->(:ShipmentDelayEvent)`.
   The path is the auditable explanation.

6. **Graph Provenance mandatory on every new node and relationship (ADR 0005).**
   Projectors record `source_system`, `source_schema`, `source_table`, `source_pk`,
   `projection_version`, `rule_name`, `rule_version`. Derivers additionally record
   `derived_from` (the source fact/rows) and, for `POSSIBLY_RELATED_TO`, `confidence`.
   `projection_version` stays `"v1"` (the contract grows by adding labels/rules, tracked
   via new `rule_name`s; bumping the version would needlessly ripple Phase 05 artifacts).
   Each new rule uses its own `rule_name` with `rule_version = "v1"`.

7. **Idempotent projection and derivation.** Use `MERGE` (not `CREATE`) keyed on the
   natural instance id so re-running updates in place and never duplicates:
   `Order {order_id}`, `Shipment {shipment_id}`, `Customer {customer_id}`,
   `ShipmentDelayEvent {shipment_id}`, `CustomerComplaintEvent {communication_id}`.
   `POSSIBLY_RELATED_TO` is `MERGE`d on the ordered pair of event identities. Projection /
   derivation is the **only** code allowed to write to Neo4j; everything else is read-only.

8. **Validator allowlist grows with the ladder, not ahead of it.** Add **only** the labels
   and relationship types this phase actually queries/creates (see Technical
   requirements). The validator stays the untrusted-input gate (still rejects mutations,
   `CALL`, non-allowlisted labels/relationships, over-depth paths, and over-row results).

9. **Route is asserted, not classified.** Step 3 route is hard-set to `graph_only`. Do
   not build the router here; record the route in the trace for later eval.

10. **Controlled Scenarios are the oracle (ADR 0011).** Correctness of the derived events
    and plausible links is proven against Scenarios A/B/C from Phase 03 — a positive case
    that **must** produce a link and two traps that **must not** — not against random data.

---

## Functional requirements

After this phase the system MUST:

1. **Extend the projection** so that, in addition to Phase 05's
   `(:Supplier)-[:SUPPLIES]->(:Product)`, it creates instance nodes `(:Customer)`,
   `(:Order)`, `(:Shipment)` and the explicit relationships
   `(:Customer)-[:PLACED]->(:Order)`, `(:Order)-[:CONTAINS]->(:Product)`, and
   `(:Order)-[:FULFILLED_BY]->(:Shipment)`, each carrying Graph Provenance. Re-running is
   idempotent.
2. **Derive `ShipmentDelayEvent` nodes** in Neo4j from `erp_core.shipments` rows where
   `delay_days > 0`, each linked `(:Shipment)-[:HAS_DELAY_EVENT]->(:ShipmentDelayEvent)`,
   carrying the delay facts (`delay_days`, `expected_delivery_date`,
   `actual_delivery_date`) and provenance (`rule_name = "shipment_delay_event"`,
   `derived_from` = the shipment). The event type MUST NOT be materialized in PostgreSQL.
3. **Derive `CustomerComplaintEvent` nodes** in Neo4j from
   `erp_docs.customer_communications` where `contact_reason = 'complaint'`, with context
   links `(:CustomerComplaintEvent)-[:RAISED_BY]->(:Customer)`,
   `-[:ABOUT_ORDER]->(:Order)` (when `order_id` present),
   `-[:ABOUT_PRODUCT]->(:Product)` (when `product_id` present), carrying
   `occurred_at`/`sentiment`/`channel` and provenance
   (`rule_name = "customer_complaint_event"`).
4. **Create the plausible link** `(:ShipmentDelayEvent)-[:POSSIBLY_RELATED_TO]->(:CustomerComplaintEvent)`
   via a controlled rule (same `order_id`; complaint `occurred_at` within
   `time_window_days` after `actual_delivery_date`; complaint body matches a delay/late
   keyword), carrying `confidence`, `matching_reason`, `time_window_days`, `evidence`
   (`shipment_id` + `communication_id`), and provenance
   (`rule_name = "delay_complaint_possibly_related"`). The graph MUST NOT contain any
   causal-named relationship for this.
5. Provide a `cypher_validator` whose allowlists now include the new labels and
   relationship types and that still **rejects** mutations, `CALL`, non-allowlisted
   labels/relationships, and paths deeper than the configured depth limit, returning a
   structured `CypherValidationResult`.
6. Answer **Shipment Delays**: return Tokyo Traders' orders that had delays by traversing
   `Supplier → Product → Order → Shipment → ShipmentDelayEvent`, computed at query time,
   ordered by `delay_days` descending. The result MUST match a direct PostgreSQL read-back
   of supplier 4's orders whose shipments have `delay_days > 0`.
7. Return a structured `answer_trace` (ADR 0003) with `route = "graph_only"`, the
   `generated_cypher`, `validation_results`, `metrics` (keyed `"neo4j"`), the traversed
   `graph_paths`, and `provenance` (source ERP tables + the rule names used). SQL/vector
   fields stay empty.
8. Expose the step via FastAPI (`GET /ladder/shipment-delays`) returning the answer **and**
   its `answer_trace`, plus a callable service function for tests.
9. Store an **expected answer spec** (behavioral) for Step 3 and persist the actual
   `answer_trace`. Prove the event/link knowledge against Controlled Scenarios A (link
   present) and B/C (no link).

---

## Technical requirements

### Projection & derivation (PostgreSQL → Neo4j) — `backend/graph/projection.py`
- **Projectors (explicit, FK-based).** Add one projector function per new entity and per
  new explicit relationship, each reading source rows with `psycopg` (reuse
  `postgres_dsn`) and writing with idempotent `MERGE`:
  - `(:Customer {customer_id})` ← `erp_core.customers` (set `company_name`, provenance;
    `rule_name = "customer_projection"`).
  - `(:Order {order_id})` ← `erp_core.orders` (set `customer_id`, `order_date`,
    provenance; `rule_name = "order_projection"`).
  - `(:Shipment {shipment_id})` ← `erp_core.shipments` (set `order_id`,
    `expected_delivery_date`, `actual_delivery_date`, `delay_days`, `status`, provenance;
    `rule_name = "shipment_projection"`).
  - `(:Customer)-[:PLACED]->(:Order)` from `orders.customer_id`
    (`rule_name = "customer_placed_order_projection"`).
  - `(:Order)-[:CONTAINS]->(:Product)` from `order_details(order_id, product_id)`
    (`rule_name = "order_contains_product_projection"`; `source_pk` = the
    `order_details` row identity).
  - `(:Order)-[:FULFILLED_BY]->(:Shipment)` from `shipments.order_id`
    (`rule_name = "order_fulfilled_by_shipment_projection"`).
- **Derivers (derived knowledge, Neo4j-born).** Add one deriver per event type and one for
  the plausible link:
  - `derive_shipment_delay_events`: for each `shipments` row with `delay_days > 0`,
    `MERGE (e:ShipmentDelayEvent {shipment_id})` with delay facts + provenance
    (`rule_name = "shipment_delay_event"`, `derived_from = "erp_core.shipments"`,
    `source_pk = shipment_id`), then `MERGE (sh)-[:HAS_DELAY_EVENT]->(e)`.
  - `derive_customer_complaint_events`: for each complaint communication,
    `MERGE (e:CustomerComplaintEvent {communication_id})` with `occurred_at`/`sentiment`/
    `channel` + provenance (`rule_name = "customer_complaint_event"`,
    `derived_from = "erp_docs.customer_communications"`), then context links
    `RAISED_BY` / `ABOUT_ORDER` / `ABOUT_PRODUCT` where the FKs are present.
  - `derive_plausible_delay_complaint_links`: for each (`ShipmentDelayEvent`,
    `CustomerComplaintEvent`) pair on the **same order** where the complaint
    `occurred_at` falls within `time_window_days` after the shipment
    `actual_delivery_date` and the complaint body matches a delay/late keyword,
    `MERGE (d)-[r:POSSIBLY_RELATED_TO]->(c)` and set `confidence`, `matching_reason`,
    `time_window_days`, `evidence`, and provenance
    (`rule_name = "delay_complaint_possibly_related"`). Make `time_window_days` a named
    constant.
- **Orchestration.** `project_all(settings)` wires everything in dependency order:
  nodes (Supplier, Product, Customer, Order, Shipment) → explicit relationships
  (`SUPPLIES`, `PLACED`, `CONTAINS`, `FULFILLED_BY`) → event derivers
  (`ShipmentDelayEvent`, `CustomerComplaintEvent` + context links) → plausible link
  deriver. Keep each step a small function so future entities are *added*, not rewired.
- **Scoped reset.** Extend `--reset` to delete only the new allowlisted elements (the new
  relationships first, then the new nodes), preserving the no-global-`DETACH DELETE` rule.
- **CLI** unchanged in shape: `python -m backend.graph.projection [--reset]` now also runs
  the new projectors/derivers.

### Cypher validator — `backend/graph/cypher_validator.py`
- `ALLOWED_LABELS` += `{"Order", "Shipment", "Customer", "ShipmentDelayEvent",
  "CustomerComplaintEvent"}`.
- `ALLOWED_RELATIONSHIP_TYPES` += `{"PLACED", "CONTAINS", "FULFILLED_BY",
  "HAS_DELAY_EVENT", "RAISED_BY", "ABOUT_ORDER", "ABOUT_PRODUCT", "POSSIBLY_RELATED_TO"}`.
- Bump `DEFAULT_MAX_DEPTH` from 4 to **6** (event paths are deeper; Step 3 is a 4-hop
  path and the Golden Query will be deeper). The existing depth tests pass an explicit
  `CypherPolicy(max_depth=4)`, so the default bump does not weaken those assertions.
- No change to the read-only guarantees: still rejects write keywords, all `CALL`,
  non-allowlisted labels/relationships, over-depth paths, and injects/caps `LIMIT`.

### Cypher executor — `backend/graph/cypher_executor.py`
- **Generalize `graph_paths` construction.** Phase 05's `_graph_path_from_record` is
  hard-coded to the supplier/relationship/product shape. Step 3 has a different path
  shape, so move per-step path shaping **out of the shared executor**: the executor
  returns the generic `records` (already JSON-ready) and a generic graph-element
  extraction, and **each ladder step builds its own `graph_paths`** in its module (or a
  small step-local helper). Keep `_essential_provenance` and `_json_ready` (reused).
  Preserve Phase 05 Step 2 output equivalence; regenerate
  `evaluation/answer_traces/step02_supplier_products.json` if the shape changes at all.
- The READ access-mode transaction, mandatory `EXPLAIN`, transaction timeout,
  `CypherExecutionError` wrapping, and fail-closed guard on unvalidated/empty input all
  stay exactly as in Phase 05.

### Ladder Step 3 — `backend/ladder/shipment_delays.py` (mirrors `supplier_products.py`)
- Deterministic Cypher template, parameterized by company name (default
  `"Tokyo Traders"`, from `backend/ladder/constants.py`):
  ```cypher
  MATCH (s:Supplier {company_name: $company_name})-[:SUPPLIES]->(p:Product)
        <-[:CONTAINS]-(o:Order)-[:FULFILLED_BY]->(sh:Shipment)
        -[:HAS_DELAY_EVENT]->(e:ShipmentDelayEvent)
  RETURN
    o.order_id          AS order_id,
    e.delay_days        AS delay_days,
    p.product_id        AS product_id,
    p.product_name      AS product_name,
    properties(o)       AS order_properties,
    properties(sh)      AS shipment_properties,
    properties(e)       AS event_properties
  ORDER BY e.delay_days DESC
  ```
- Flow: `build_shipment_delays_cypher()` → `validate_cypher()` → `run_validated_cypher()`
  → assemble `AnswerTrace`. The Cypher is built from trusted constants/parameters and
  still passed through the validator (the governed path is identical to the future
  LLM-generated case).
- `answer_trace`: `route = QueryRoute.GRAPH_ONLY`, `generated_cypher` = effective Cypher,
  `metrics = {"neo4j": metrics}`, `validation_results = [validation]`, `graph_paths`
  populated with the full traversed path (supplier → product → order → shipment → event,
  each with essential provenance), and `provenance` = entries for `erp_core.orders`,
  `erp_core.order_details`/`erp_core.products`, and `erp_core.shipments` with the
  derivation `rule_name = "shipment_delay_event"`.
- Public `answer` contains only business rows (e.g. `order_id`, `delay_days`); supplier
  details, relationship metadata, provenance, generated Cypher, validation, and metrics
  belong in `answer_trace`, not the top-level answer.
- `answer_shipment_delays()` must not call `project_all()` or perform any graph writes —
  projection/derivation is an explicit setup step.
- Correctness: the returned order set MUST match a direct PostgreSQL read-back —
  supplier 4's products → their orders → shipments with `delay_days > 0`. An empty Tokyo
  Traders result is a Step-3 evaluation failure.
- CLI `--emit-trace` writing
  `evaluation/answer_traces/step03_shipment_delays.json` (like Steps 1–2).

### API & packaging
- Add `GET /ladder/shipment-delays` to `backend/ladder/router.py` (reuse the existing
  `APIRouter(prefix="/ladder")`, `Depends(get_settings)`); returns
  `{"answer": [...], "answer_trace": {...}}`.
- Keep ruff clean (`select = ["E","F","I","UP","B"]`); 88-col lines; `snake_case` for
  modules/functions; `PascalCase` for node labels; `SCREAMING_SNAKE_CASE` for
  relationship types.
- Update `README.md` with the Phase 06 run path: `docker compose up -d neo4j`,
  `python -m backend.graph.projection` (now also derives events/links), and
  `python -m backend.ladder.shipment_delays --emit-trace`.

### Evaluation artifacts
- `evaluation/ladder/step03_shipment_delays.spec.json` — behavioral expected answer spec:
  route `graph_only`; non-empty Tokyo Traders delayed-order set; ordered by `delay_days`
  desc; validation allowed; node labels
  `{Supplier, Product, Order, Shipment, ShipmentDelayEvent}`; relationship types
  `{SUPPLIES, CONTAINS, FULFILLED_BY, HAS_DELAY_EVENT}`; `graph_paths` populated with
  provenance; matches PostgreSQL read-back for `supplier_id = 4`. Declarative, **not** a
  pinned order-id list.
- `evaluation/answer_traces/step03_shipment_delays.json` — persisted actual trace
  (regenerable sample).

---

## File structure

```text
test-project/
├─ backend/
│  ├─ graph/
│  │  ├─ projection.py                # + Customer/Order/Shipment projectors,
│  │  │                               #   event & plausible-link derivers, wiring, reset
│  │  ├─ cypher_validator.py          # + new labels/relationships; DEFAULT_MAX_DEPTH 4→6
│  │  └─ cypher_executor.py           # generalize graph_paths construction (path shaping
│  │                                  #   moves to ladder steps)
│  └─ ladder/
│     ├─ constants.py                 # + shipment-delays company default (Tokyo Traders)
│     ├─ shipment_delays.py           # NEW: build Cypher → validate → execute → trace (+CLI)
│     └─ router.py                    # + GET /ladder/shipment-delays
├─ evaluation/
│  ├─ ladder/
│  │  └─ step03_shipment_delays.spec.json     # expected answer spec (behavioral)
│  └─ answer_traces/
│     └─ step03_shipment_delays.json          # persisted actual trace (regenerable)
└─ tests/
   ├─ test_graph_projection.py        # extend: new nodes/rels + provenance, idempotent
   ├─ test_event_derivation.py        # NEW: events only where warranted; not in Postgres
   ├─ test_plausible_links.py         # NEW: Scenario A link present; B/C traps absent
   ├─ test_cypher_validator.py        # extend: new labels/rels accepted; mutations rejected
   └─ test_ladder_shipment_delays.py  # NEW: traversal vs PG read-back, route, trace, endpoint
```

---

## Implementation guidance

### Derivation (`backend/graph/projection.py`)

```python
# Named constants for the plausible-link rule.
PLAUSIBLE_LINK_TIME_WINDOW_DAYS = 14
DELAY_KEYWORDS = ("delay", "late")

SHIPMENT_DELAY_EVENT_MERGE = """
MATCH (sh:Shipment {shipment_id: $shipment_id})
MERGE (e:ShipmentDelayEvent {shipment_id: $shipment_id})
SET e.delay_days = $delay_days,
    e.expected_delivery_date = $expected_delivery_date,
    e.actual_delivery_date = $actual_delivery_date,
    e.source_system = 'postgresql', e.source_schema = 'erp_core',
    e.source_table = 'shipments', e.source_pk = $shipment_id,
    e.derived_from = 'erp_core.shipments',
    e.rule_name = 'shipment_delay_event', e.rule_version = $version,
    e.projection_version = $version
MERGE (sh)-[r:HAS_DELAY_EVENT]->(e)
SET r.rule_name = 'shipment_delay_event', r.rule_version = $version,
    r.projection_version = $version
"""

POSSIBLY_RELATED_MERGE = """
MATCH (d:ShipmentDelayEvent {shipment_id: $shipment_id})
MATCH (c:CustomerComplaintEvent {communication_id: $communication_id})
MERGE (d)-[r:POSSIBLY_RELATED_TO]->(c)
SET r.confidence = $confidence,
    r.matching_reason = $matching_reason,
    r.time_window_days = $time_window_days,
    r.evidence = $evidence,
    r.rule_name = 'delay_complaint_possibly_related', r.rule_version = $version,
    r.projection_version = $version, r.derived_from = 'erp_core.shipments+erp_docs.customer_communications'
"""
# Derivers only created in Neo4j (ADR 0004). MERGE keeps them idempotent.
# The candidate pairs for POSSIBLY_RELATED_TO are computed by a controlled SQL/code rule
# (same order_id; complaint within PLAUSIBLE_LINK_TIME_WINDOW_DAYS of delivery; delay
# keyword in body), NOT by an LLM guess (invariant #3 / ADR 0012).
```

> The plausible-link rule is deliberately conservative so the Controlled Scenarios behave:
> Scenario A produces a link (Tokyo delay + delay-keyword complaint, same order, in
> window); Scenario C does **not** (complaint exists but is unrelated to a delay / no
> delay keyword); Scenario B does **not** (delays exist but the trap is about non-top
> customers and need not produce a qualifying complaint link).

### Ladder Step 3 (`backend/ladder/shipment_delays.py`)
- Mirror `backend/ladder/top_customers.py` / `supplier_products.py` in shape:
  `build_shipment_delays_cypher()` → `validate_cypher()` → `run_validated_cypher()` →
  `build_answer_trace()` → optional `persist_answer_trace()`; `parse_args()` + `main()`
  with `--emit-trace` / `--trace-path`.
- Build `graph_paths` here (executor no longer hard-codes the shape): one entry per
  result row describing supplier → product → order → shipment → event, each block carrying
  identity/display fields plus essential Graph Provenance, so every answer row is auditable
  back to the exact graph elements used.

### Verification via Neo4j Browser + read-back
After projecting+deriving, open `http://localhost:7474` and run, e.g.,
`MATCH p=(:Supplier {company_name:'Tokyo Traders'})-[:SUPPLIES]->(:Product)<-[:CONTAINS]-(:Order)-[:FULFILLED_BY]->(:Shipment)-[:HAS_DELAY_EVENT]->(:ShipmentDelayEvent) RETURN p`
to visually confirm the path, and
`MATCH (:ShipmentDelayEvent)-[r:POSSIBLY_RELATED_TO]->(:CustomerComplaintEvent) RETURN r`
to confirm the plausible links and their properties. Then compare the API/function output
against a direct PostgreSQL read-back of supplier 4's orders whose shipments have
`delay_days > 0` — the order sets must match.

---

## Acceptance criteria

This phase is complete when **all** of the following hold:

- [ ] `docker compose up -d neo4j` is running; `/health` Neo4j check returns
      `available: true`. No new dependency added to `pyproject.toml`.
- [ ] **Projection** now also creates `(:Customer)`, `(:Order)`, `(:Shipment)` nodes and
      `PLACED` / `CONTAINS` / `FULFILLED_BY` relationships, **every** new node and
      relationship carrying Graph Provenance. Tokyo Traders' orders/shipments are present.
- [ ] **`ShipmentDelayEvent`** nodes exist in Neo4j for shipments with `delay_days > 0`,
      linked via `HAS_DELAY_EVENT`, with provenance + `derived_from`; **none** for
      non-delayed shipments. The event type is **not** materialized in PostgreSQL.
- [ ] **`CustomerComplaintEvent`** nodes exist for complaint communications, with
      `RAISED_BY` / `ABOUT_ORDER` / `ABOUT_PRODUCT` context links where the FKs exist, and
      provenance.
- [ ] **`POSSIBLY_RELATED_TO`** links exist for Scenario A (Tokyo delay ↔ delay-related
      complaint on the same order, in window), carrying `confidence`, `matching_reason`,
      `time_window_days`, `evidence`. **No** such link is created for Scenario B or
      Scenario C. **No** causal-named relationship exists in the graph.
- [ ] **Projection/derivation is idempotent**: running it twice yields the same
      node/relationship counts (a test asserts no duplication).
- [ ] **Cypher validator accepts** the Step 3 traversal over the extended allowlist and
      returns `allowed: True` with an `effective_cypher` carrying an enforced `LIMIT`; it
      still **rejects** mutations, `CALL`, a non-allowlisted label/relationship, and an
      over-depth path.
- [ ] **Shipment Delays** returns Tokyo Traders' delayed orders ordered by `delay_days`
      desc; the set **matches the PostgreSQL read-back** (supplier 4 → orders → shipments
      with `delay_days > 0`) exactly.
- [ ] **`answer_trace`** validates against the schema with `route == "graph_only"`,
      populated `generated_cypher`, `validation_results`, `metrics` (keyed `"neo4j"`),
      `graph_paths` (full path with provenance), and `provenance`; SQL/vector fields
      present but empty.
- [ ] `GET /ladder/shipment-delays` returns `200` with `answer` + `answer_trace` (test may
      skip if Neo4j is unconfigured, like the Phase 05 fixtures).
- [ ] Unit tests for `validate_cypher()` run without Neo4j. Live projection/derivation,
      executor, and ladder tests skip with a clear reason when Neo4j is unconfigured or
      unreachable, and run normally when the dev stack is available.
- [ ] The **expected answer spec** for Step 3 is stored under `evaluation/ladder/` and
      encodes behavioral expectations (route, non-empty delayed-order set, ordering,
      read-only validation passed, labels/relationships used, provenance present) — not a
      pinned order-id list.
- [ ] The step can **persist its actual `answer_trace`** to
      `evaluation/answer_traces/step03_shipment_delays.json`; if the executor's
      `graph_paths` generalization changes Step 2's shape, its persisted trace is
      regenerated too.
- [ ] `pytest` and `ruff check .` are clean. All new code is committed.

---

## Out of scope (do NOT do in this phase)

- **ContractTermEvents / `supplier_contracts`** and **Qdrant / embeddings / chunking /
  document retrieval** — **Phase 07**. The `answer_trace` vector fields stay empty.
- **LangGraph Query Router / route classification** — **Phase 08**. Here the route is
  hard-set to `graph_only`.
- **LLM text-to-Cypher** or any LLM/OpenRouter/HF/Ollama call — later. The Cypher is built
  from trusted constants/parameters and still validated.
- **Other Event Nodes** (`StockOutEvent`, `InvoiceOverdueEvent`) and other derived
  relationships beyond `POSSIBLY_RELATED_TO` — later phases register them.
- **Schema changes / migrations / new PostgreSQL data** — Phase 06 reads the existing
  Phase 02/03 database. If a need reveals a schema gap, stop and raise it.
- **Writing any event back to PostgreSQL** — events live only in Neo4j (ADR 0004).
- **Auth / deployment hardening / polished frontend** — out of scope for Milestone 1.

---

## References

- `CLAUDE.md` → invariants #1 (data/knowledge boundary; events born in Neo4j), #2 (Graph
  Provenance mandatory), #3 (explicit vs derived relationships; readable multi-hop paths,
  no shortcut edges), #4 (plausible relationships, not causality), #5 (guardrails in code),
  #6 (`answer_trace` mandatory), #7 (routing explicit; GraphRAG for multi-hop/events).
- `CONTEXT.md` → `Event Node`, `ShipmentDelayEvent`, `CustomerComplaintEvent`,
  `Derived Graph Relationship`, `Plausible Relationship`, `Knowledge Layer`,
  `Controlled Scenario` (use these exact terms; avoid the rejected synonyms).
- `docs/adr/0002-*` — route types (`graph_only`).
- `docs/adr/0003-*` — the `answer_trace` contract (graph fields populated).
- `docs/adr/0004-*` — Event Nodes live only in Neo4j (binding here).
- `docs/adr/0005-*` — Graph Provenance on every node/relationship (incl. derived).
- `docs/adr/0009-*` — code-level query guardrails (Cypher read-only, allowlists, limits).
- `docs/adr/0011-*` — Controlled Scenarios as the evaluation oracle.
- `docs/adr/0012-*` — plausible relationships, not causality (`POSSIBLY_RELATED_TO`).
- `docs/ISSUES.md` → **Issue 6** (shipment delay Event Node ladder step) and **Issue 7**
  (CustomerComplaintEvent + plausible delay-to-complaint links) — both delivered here.
- `docs/PRD.md` → user stories 9, 10, 12–19, 24, 37; testing decisions (ladder
  expected-answer specs + persisted actual `answer_trace`; validator rejects mutation
  Cypher; provenance traceable; controlled positive/false-positive scenarios).
- `Project_Idea.md` → ladder Step 3 (shipment delays) and the ERP Domain Graph event model.
- `directives/phase-05-neo4j-projection-supplier-products-ladder-step.md` — the governed
  graph path (projection → validator → executor → trace) this phase extends, and the
  projector pattern it grows with derivers.
```
