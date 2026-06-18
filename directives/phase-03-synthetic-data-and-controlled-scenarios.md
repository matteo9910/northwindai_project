# Phase 03 — Synthetic Data & Controlled Scenarios

> Macro phase 3 of the NorthwindAI build. Replaces the original Northwind
> transactional history with **deterministic** synthetic `orders` and
> `order_details` over the **January 2020 – December 2025** horizon, populates
> the currently empty custom ERP tables, and injects the four **Controlled
> Scenarios** (ADR 0011) that make the query ladder and the Golden Query
> testable. This phase produces *data only* — no schema changes, no Neo4j, no
> Qdrant. Data is still *born in PostgreSQL* (`CLAUDE.md` invariant #1).

---

## Objective

Turn the empty Operational Source of Truth from Phase 02 into a realistic,
reproducible mini-ERP dataset so that:

- the original Northwind master data (`customers`, `products`, `suppliers`,
  `categories`, `employees`, `shippers`, etc.) remains available as the mini-ERP
  master-data baseline,
- the original Northwind transactional seed (`orders`, `order_details`, dated
  1996–1998) is removed from the final analytical dataset and replaced by
  deterministic 2020–2025 transactional data,
- the custom `erp_core` tables (`shipments`, `invoices`, `inventory_movements`,
  `price_history`, plus a small fixed `warehouses` master set) are populated with
  statistically plausible volume over 2020-01 → 2025-12,
- the `erp_docs` tables (`customer_communications`, `supplier_contracts`,
  `product_specifications`, `documents`, `document_entities`) carry the structured
  records the later ladder steps depend on (structured-first contract terms per
  ADR 0010 — **no PDFs yet**),
- the dataset embeds the four **Controlled Scenarios** (A–D below) anchored to
  the real Northwind suppliers, so reasoning paths, the top-customer filter, and
  false-positive traps are all exercisable,
- everything is **deterministic** (single fixed seed) and **re-runnable** (a
  reset routine restores the intended Phase-03 baseline: Northwind master data
  kept, all transactional/custom generated data removed, then regenerated).

**Query ladder:** this phase delivers the *data substrate* for the whole ladder.
After it, **Ladder Step 1 (SQL-only Top Customers / "Which products does Tokyo
Traders supply?")** becomes answerable against meaningful data — but the Step 1
*query code* itself is Phase 04. Do **not** build query/router/validator code here.

---

## Prerequisites

- **Phase 02 complete and verified.** `erp_core` + `erp_docs` exist; base
  Northwind is loaded (customers ≈ 91, orders ≈ 830, products = 77, suppliers = 29);
  all custom tables exist and are **empty**. The Phase 02 `orders` and
  `order_details` rows are treated as legacy seed data used only to bootstrap the
  schema and statistical shape; they will be deleted and replaced during Phase 03.
- `.env` is populated and `/health` reports Postgres `available: true`.
- `backend.config.get_settings().postgres_dsn` connects (reused by the generator).
- The Supabase MCP server targets `northwindai` (used only for **read-back
  verification** here, e.g. `execute_sql` row counts — **not** for loading data).

---

## Functional requirements

After this phase the database MUST:

1. Contain a small fixed set of `erp_core.warehouses` (3–5 rows) used by inventory.
2. Contain synthetic `erp_core.orders` + `erp_core.order_details` over
   2020-01-01 → 2025-12-31 reaching the indicative volume (≈ 15,000–18,000 total
   synthetic orders), with **no remaining operational orders before 2020**.
3. Contain `erp_core.shipments` for (most) orders, with coherent
   `expected_delivery_date` / `shipped_date` / `actual_delivery_date` so the stored
   `delay_days` generated column reflects real lateness.
4. Contain `erp_core.invoices` derived from orders (amounts consistent with
   `order_details`), with realistic `status` / `payment_date` distributions.
5. Contain `erp_core.inventory_movements` and `erp_core.price_history` coherent
   with products and the time horizon.
6. Contain `erp_docs.supplier_contracts` for the scenario suppliers (at minimum),
   with `lead_time_days` set per scenario (structured-first, ADR 0010).
7. Contain `erp_docs.customer_communications` including complaints, wired per the
   scenarios (delay-related vs. unrelated).
8. Contain `erp_docs.product_specifications` for a reasonable subset of products,
   and `erp_docs.documents` (+ optional `document_entities`) registry rows
   referencing the generated contracts/communications (**`file_path` NULL — no
   PDFs in M1**).
9. Embed **Controlled Scenarios A–D** (see [Controlled Scenarios](#controlled-scenarios)),
   each verifiable by a SQL probe.
10. Be **deterministic**: a clean run from a fixed seed reproduces identical data
    (same counts, same scenario anchoring).
11. Be **idempotent / re-runnable**: re-running the generator first resets to the
    Phase-03 generation baseline (truncate custom tables; delete **all**
    `orders` and `order_details`) and regenerates from scratch — never duplicating
    and never preserving the original 1996–1998 operational order history.

---

## Technical requirements

### Determinism & the analysis reference date
- **Single fixed seed** drives Faker **and** numpy (`SEED = 42`). All randomness
  flows from seeded generators; no calls to `random`/`datetime.now()` for data values.
- Define a fixed **analysis reference date** constant `AS_OF = date(2025, 12, 31)`.
  - "last 12 months" (Top Customers definition, ADR 0013) ⇒ `2025-01-01 .. 2025-12-31`.
  - "last 3 months" (Scenario A delay window) ⇒ `2025-10-01 .. 2025-12-31`.
  - This is intentionally decoupled from wall-clock time so the dataset stays valid
    regardless of when it is generated. Document the constant prominently.

### Volume & distributions (statistical realism, `Project_Idea.md` §7.1)
- ≈ 2,500–3,000 orders/year × 6 years ⇒ ≈ 15,000–18,000 synthetic orders.
  **Hard ceiling:** `orders.order_id` is `smallint` (mirrors pthom). Base orders
  occupy ids up to ~11077; synthetic ids continue from `max(order_id)+1` and MUST
  stay ≤ 32767. 18k synthetic + 830 base ≈ 29k — fits, but do **not** exceed the
  upper target. Let identity/sequence-free explicit ids be assigned by the generator.
- Reuse existing master data (customers, products, suppliers, employees, shippers,
  categories). Do **not** invent new customers/products in this phase — the
  91-customer base keeps the Top-Customer ranking meaningful and the scenarios anchored.
- Do **not** reuse the original Northwind `orders` / `order_details` as final
  operational history. Use them only as optional statistical inspiration; the final
  mini-ERP transactional horizon is 2020-01-01 → 2025-12-31.
- Apply: per-category **seasonality**, **Pareto-like** customer concentration
  (a minority of customers drive most revenue), product popularity derived from the
  base data, and mild **price/demand trends** over the horizon. Add modest noise.
- **Net revenue** (the Top-Customer metric, ADR 0013) is defined as
  `sum(order_details.unit_price * quantity * (1 - discount))` over the period.
  The generator must use this exact definition when it anchors scenarios, so Phase 04's
  SQL agrees.

### Loading mechanism
- A deterministic **Python generator** writes directly to PostgreSQL via
  **psycopg 3** using `backend.config.get_settings().postgres_dsn`.
- Bulk-load with `cursor.executemany(...)` or `COPY` (`cursor.copy(...)`) per table,
  inside explicit transactions, in FK-dependency order
  (warehouses → orders → order_details → shipments → invoices → inventory_movements
  → price_history → supplier_contracts → customer_communications →
  product_specifications → documents → document_entities).
- **Do not** use Supabase MCP `apply_migration` to load data (MCP is for DDL; the
  volume here would not fit). MCP/`execute_sql` is used only for read-back checks.
- Reproducibility comes from the **committed generator code + fixed seed**, not from a
  giant committed SQL dump (ADR 0011). Do not commit generated `.sql`/`.csv` data dumps.

### New dependencies & packaging
- Add to `pyproject.toml` `[project].dependencies`:
  `faker>=25,<40`, `numpy>=1.26,<3.0`, `pandas>=2.2,<3.0`, `scipy>=1.13,<2.0`.
  (Pin within the installed Python 3.11 range; verify resolution with `pip install -e .`.)
- Add the new package to `[tool.setuptools.packages.find]`:
  `include = ["backend*", "data_generation*"]` (otherwise the package won't install).
- Keep ruff clean (`select = ["E","F","I","UP","B"]`).

### Identifiers & conventions
- `snake_case` everywhere; reuse the column names/types created in Phase 02.
- Money → values consistent with the existing `real`/`numeric` columns; dates → `date`;
  event timestamps → `timestamptz`.
- `invoices.invoice_number` and `supplier_contracts.contract_number` must be unique
  and deterministically generated (e.g. `INV-{year}-{seq}`, `CT-{supplier_id}-{seq}`).

---

## File structure

```text
test-project/
├─ data_generation/
│  ├─ __init__.py
│  ├─ config.py            # SEED, AS_OF, horizon bounds, volume targets, scenario constants
│  ├─ reset.py             # restore generation baseline (truncate custom + delete all orders)
│  ├─ masters.py           # warehouses + (re)used master-data helpers
│  ├─ orders.py            # synthetic orders + order_details (seasonality, Pareto, trends)
│  ├─ logistics.py         # shipments (+ delay_days inputs), inventory_movements
│  ├─ finance.py           # invoices, price_history
│  ├─ docs.py              # supplier_contracts, customer_communications,
│  │                       #   product_specifications, documents, document_entities
│  ├─ scenarios.py         # Controlled Scenarios A–D injection + post-hoc assertions
│  ├─ loader.py            # psycopg bulk-load helpers (executemany / COPY, tx, FK order)
│  └─ generate.py          # CLI entrypoint: reset → generate → load → self-check
├─ tests/
│  └─ test_controlled_scenarios.py   # SQL probes proving A–D exist (see Acceptance)
└─ data_generation/README.md          # how to run, seed, AS_OF, re-run semantics
```

Run with: `python -m data_generation.generate` (optionally `--reset-only`,
`--seed N`, `--dry-run`).

---

## Controlled Scenarios

Anchored to the real Northwind suppliers (ids from the loaded base data):

| Supplier | `supplier_id` | Scenario | Tests |
|---|---|---|---|
| **Tokyo Traders** | 4 | **A** — supplies products ordered by **top customers**; in the last 3 months (`2025-10..12`) several of those orders are **delayed**; some top-customer complaints **mention delays**; contract `lead_time_days = 14` but **actual avg delivery ≈ 22 days**. | Positive multi-hop path Supplier→Product→Order→ShipmentDelayEvent + complaint correlation + contract-vs-actual gap. |
| **Exotic Liquids** | 1 | **B** — similar delays but toward **non-top** customers. | The top-customer filter (delays must be excluded when customer isn't top). |
| **Pavlova, Ltd.** | 7 | **C** — products ordered by **top customers** who **do complain**, but complaints are **not** delay-related (e.g. quality/packaging) **and** their Pavlova orders are **not** delayed. | False-positive avoidance for `POSSIBLY_RELATED_TO` (ADR 0012). |
| **Grandma Kelly's Homestead** | 3 | **D** — **worse contract terms** (higher `lead_time_days`, e.g. 30) but **fewer complaints**. | Qualitative contract comparison. |

Requirements for the scenario layer (`scenarios.py`):

1. **Deterministically designate the top customers.** Boost order volume/value for a
   fixed, seeded set of customers in the last-12-months window so that, under the
   net-revenue definition above, a known set lands in the **top 10**. Then anchor
   Scenarios A and C to those customers, and Scenario B explicitly to customers
   **outside** the top 10.
2. **Self-check (assertion).** After loading, recompute top-10 customers by net
   revenue over `2025-01-01..2025-12-31` and **assert** the intended scenario
   customers actually rank in the top 10 (and the Scenario-B customer does not).
   Fail loudly if the design and the data disagree — a silently invalid controlled
   scenario is worse than none.
3. **Scenario A delay shape.** For Tokyo Traders' product orders by top customers in
   `2025-10..12`, set shipment dates so `delay_days` averages ≈ 8 (actual ≈ 22 vs
   contract lead 14). Generate a handful of `customer_communications` with
   `contact_reason='complaint'`, negative `sentiment`, body text mentioning delay/late
   delivery, linked to those orders.
4. **Scenario C trap.** Pavlova top-customer orders are **on time** (`delay_days <= 0`
   or null), yet those customers have complaints with `contact_reason='complaint'`
   about quality/packaging (not delay) — not linkable to any delay.
5. Keep scenario rows **inside** the realistic background so they are not trivially
   separable (no magic flags in the data); identification is via the business pattern,
   not a marker column.

---

## Implementation guidance

### Seed & reference date (`data_generation/config.py`)

```python
from datetime import date

SEED = 42
HORIZON_START = date(2020, 1, 1)
HORIZON_END = date(2025, 12, 31)
AS_OF = date(2025, 12, 31)              # anchors "last 12 / 3 months"
LAST_12M_START = date(2025, 1, 1)
LAST_3M_START = date(2025, 10, 1)

ORDERS_PER_YEAR = (2500, 3000)          # inclusive target band

# Scenario supplier ids (from loaded base Northwind data)
TOKYO_TRADERS = 4
EXOTIC_LIQUIDS = 1
PAVLOVA = 7
GRANDMA_KELLYS = 3
```

```python
# Single seeded source of randomness — pass these around; never use bare random/now().
import numpy as np
from faker import Faker

def make_rng(seed: int = SEED) -> tuple[np.random.Generator, Faker]:
    fake = Faker()
    Faker.seed(seed)
    return np.random.default_rng(seed), fake
```

### Reset / idempotency (`data_generation/reset.py`)

```sql
-- custom tables are 100% synthetic → truncate (RESTART IDENTITY, CASCADE within erp_docs)
truncate erp_docs.document_entities, erp_docs.documents,
         erp_docs.customer_communications, erp_docs.supplier_contracts,
         erp_docs.product_specifications restart identity cascade;
truncate erp_core.inventory_movements, erp_core.price_history,
         erp_core.invoices, erp_core.shipments restart identity cascade;
truncate erp_core.warehouses restart identity cascade;

-- Replace the original Northwind transactional seed with one coherent
-- analytical horizon. Keep Northwind master data, but remove all operational
-- orders/order_details before regenerating 2020-2025 history.
delete from erp_core.order_details;
delete from erp_core.orders;
```

> Run reset inside the generator before each full run so `python -m
> data_generation.generate` is safely repeatable. Provide `--reset-only` to restore
> the generation baseline: master data kept, custom/generated tables empty, and
> no operational orders present.

### Net-revenue helper (must match Phase 04's SQL)

```sql
select o.customer_id,
       sum(od.unit_price * od.quantity * (1 - od.discount)) as net_revenue
from erp_core.orders o
join erp_core.order_details od on od.order_id = o.order_id
where o.order_date >= date '2025-01-01' and o.order_date <= date '2025-12-31'
group by o.customer_id
order by net_revenue desc
limit 10;
```

### Loading (`data_generation/loader.py`)
- Open one `psycopg.connect(get_settings().postgres_dsn)`; load each table in FK order
  within a transaction; commit once at the end (or per-table with savepoints).
- Prefer `with cur.copy("COPY erp_core.orders (...) FROM STDIN") as cp: cp.write_row(...)`
  for the high-volume tables; `executemany` is acceptable for smaller tables.
- Let `bigint generated always as identity` PKs autogenerate; supply only the
  business/explicit columns. For `orders.order_id` (no identity), assign explicit ids
  starting at `max(order_id)+1` from the base data.

### Verification via MCP
After generation, read back counts and scenario probes with `execute_sql` against
`northwindai` (see Acceptance).

---

## Acceptance criteria

This phase is complete when **all** of the following hold:

- [ ] `pyproject.toml` includes faker/numpy/pandas/scipy and
      `packages.find.include` lists `data_generation*`; `pip install -e ".[dev]"` succeeds.
- [ ] `python -m data_generation.generate` runs end-to-end with no errors and is
      **idempotent**: running it twice yields identical row counts (spot-check a few tables).
- [ ] Synthetic orders exist in the horizon:
      `select count(*) from erp_core.orders where order_date between '2020-01-01' and '2025-12-31'`
      is within ≈ 15,000–18,000, and `order_id` max ≤ 32767.
- [ ] No pre-2020 operational orders remain:
      `select count(*) from erp_core.orders where order_date < '2020-01-01'` = 0.
- [ ] Northwind master data is preserved:
      customers ≈ 91, products = 77, suppliers = 29, categories = 8.
- [ ] `shipments`, `invoices`, `inventory_movements`, `price_history`, `warehouses`
      are populated and internally coherent (e.g. every `shipments.order_id` exists;
      `invoices.total_amount` ≈ order line totals within tax tolerance).
- [ ] `supplier_contracts` exist for suppliers 1, 3, 4, 7 with the scenario
      `lead_time_days` (Tokyo Traders = 14, Grandma Kelly's = 30).
- [ ] **Top-customer self-check passes**: the generator's post-load assertion confirms
      the designated Scenario-A/C customers are in the top-10 by net revenue
      (`2025-01-01..2025-12-31`) and the Scenario-B customer is not.
- [ ] **Scenario A probe**: Tokyo Traders products ordered by top customers in
      `2025-10..12` show `avg(delay_days) > 0` (≈ 8), and ≥ 1 delay-related complaint
      links to those orders.
- [ ] **Scenario B probe**: Exotic Liquids delays exist but the affected customers are
      **not** in the top-10 list.
- [ ] **Scenario C probe**: Pavlova top-customer orders have `delay_days <= 0`/null,
      yet those customers have non-delay complaints.
- [ ] **Scenario D probe**: Grandma Kelly's `lead_time_days` > Tokyo Traders' and its
      complaint count is lower than Tokyo Traders'.
- [ ] `tests/test_controlled_scenarios.py` encodes the four probes as behavioral
      assertions (querying the live DB via psycopg using the configured DSN) and passes;
      `pytest` and `ruff check .` are clean.
- [ ] `data_generation/README.md` documents the seed, `AS_OF`, volume targets, the
      re-run/reset semantics, and how to run the CLI.
- [ ] All generator code is committed; **no** generated data dumps are committed.

### Suggested verification block (for `data_generation/README.md`)

```sql
-- volumes
select
  (select count(*) from erp_core.orders where order_date >= '2020-01-01') as synth_orders,
  (select count(*) from erp_core.shipments) as shipments,
  (select count(*) from erp_core.invoices) as invoices,
  (select count(*) from erp_docs.customer_communications) as comms,
  (select count(*) from erp_docs.supplier_contracts) as contracts;

-- Scenario A: Tokyo Traders delay in last 3 months toward top customers
-- (join orders→order_details→products[supplier_id=4]→shipments, filter top-10 customers)
```

---

## Out of scope (do NOT do in this phase)

- **Any Neo4j work**: projection, nodes, relationships, Event Nodes
  (`ShipmentDelayEvent`, `CustomerComplaintEvent`, `StockOutEvent`,
  `InvoiceOverdueEvent`, `ContractTermEvent`) — **Phase 05+**. Phase 03 only creates
  the PostgreSQL *facts* those events will later be derived from.
- **Any Qdrant work**: collections, chunking, embeddings — **Phase 07**.
- **Query code**: router, query validators/guardrails, SQL/Cypher generation, the SQL
  executor, `answer_trace`, Top-Customer *query* — **Phase 04+**. (Phase 03 may compute
  net revenue internally for scenario anchoring, but ships **no** queryable API.)
- **PDF / document files**: no contract PDFs, OCR, OpenDataLoader, or
  structured-vs-PDF discrepancy detection. `documents.file_path` stays NULL;
  contract terms are structured-first (ADR 0010). Clean PDFs arrive later.
- **Schema changes / migrations**: no new tables or columns. If the data reveals a
  genuine schema gap, stop and raise it — do not silently `ALTER`. All DDL belongs to
  Phase 02 migrations.
- **New customers/products/suppliers**: reuse the base master data.
- RLS / auth / deployment hardening — out of scope for Milestone 1.

---

## References

- `Project_Idea.md` §3.3 (custom-table semantics), §7 (synthetic data: §7.1 statistical
  realism + horizon/volume, §7.2 Controlled Scenarios A–D), §13 Phase 1 (roadmap).
- `CLAUDE.md` → invariant #1 (data born in PostgreSQL), #9 (Top Customers = net revenue,
  computed not stored), #10 (deterministic data + Controlled Scenarios).
- `docs/adr/0011-controlled-scenarios-for-synthetic-data.md` — deterministic data with
  intentional positive/negative/false-positive cases.
- `docs/adr/0013-top-customers-by-net-revenue.md` — the stable Top-Customer definition.
- `docs/adr/0012-use-plausible-relationships-for-event-links.md` — why Scenario C
  (false-positive trap) matters.
- `docs/adr/0010-contract-term-events-from-structured-source-first.md` — structured
  contract fields first, PDFs later.
- `docs/PRD.md` → user stories 20–24 (Top Customers + controlled scenarios), Assumptions
  (Jan 2020–Dec 2025 horizon, top-10 by revenue last 12 months), Testing decisions
  (Controlled Scenario tests, Top-Customer computed-not-stored).
- `directives/phase-02-database-schema-foundation.md` — the schema this phase fills.
