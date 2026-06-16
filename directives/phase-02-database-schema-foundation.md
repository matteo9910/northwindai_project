# Phase 02 — Database Schema & Northwind Foundation

> Macro phase 2 of the NorthwindAI build. Creates the two logical PostgreSQL
> schemas (`erp_core`, `erp_docs`) inside the single Supabase project
> `northwindai`, loads the base Northwind dataset into `erp_core`, and defines
> **all** custom ERP tables (empty). This phase builds the *structure* of the
> Operational Source of Truth. It does **not** generate the extended synthetic
> data — that is Phase 03.

---

## Objective

Establish the complete relational foundation of the Operational Source of Truth so that:

- the `erp_core` and `erp_docs` schemas exist in the `northwindai` Supabase database,
- the base Northwind tables and their original seed data live in `erp_core`,
- every custom ERP table defined in `Project_Idea.md` §3.3 exists with correct columns, primary keys, and foreign keys,
- all DDL is delivered as versioned, idempotent migrations applied through the **Supabase MCP server**,
- the schema is verifiable via `list_tables` and a structural verification query.

All work in this phase is performed by the coding agent through Supabase MCP tools (`apply_migration`, `execute_sql`, `list_tables`). There are **no manual dashboard steps** beyond what Phase 01 already did (the `northwindai` project must already exist and the MCP server must target it).

**Query ladder:** no ladder step runs end-to-end yet. This phase delivers the *schema* that Ladder Step 1 (SQL-only Top Customers, Phase 04) depends on. The base Northwind seed alone is too small/old for a meaningful "last 12 months" revenue answer; the extended data arrives in Phase 03.

---

## Prerequisites

- **Phase 01 complete.** The repo baseline, `.env`, Docker services, and `/health` exist.
- The Supabase project **`northwindai`** exists and is reachable (verified by Phase 01's `/health` Postgres check returning `available: true`).
- The Supabase MCP server is configured and targets `northwindai`. Confirm with `list_projects` / `list_tables` before applying any migration.

---

## Functional requirements

After this phase the database MUST:

1. Contain two schemas: `erp_core` and `erp_docs`.
2. Contain all base Northwind tables in `erp_core`, populated with the original Northwind seed data.
3. Contain all custom `erp_core` tables: `warehouses`, `shipments`, `invoices`, `inventory_movements`, `price_history` — created empty.
4. Contain all custom `erp_docs` tables: `documents`, `document_entities`, `customer_communications`, `supplier_contracts`, `product_specifications` — created empty.
5. Enforce referential integrity: every foreign key references a real parent table/column, across schemas where required (e.g. `erp_docs.supplier_contracts.supplier_id → erp_core.suppliers.supplier_id`).
6. Be reproducible: re-running the migrations on a clean database produces the identical schema (idempotent DDL, deterministic ordering).
7. Be inspectable: `list_tables` reports every table under both schemas with the expected columns.

---

## Technical requirements

### Target database
- Single Supabase Postgres database in project `northwindai`.
- Two schemas only: `erp_core`, `erp_docs`. Do **not** use `public` for project tables (leave Supabase's managed objects in `public` untouched).
- The two-schema split is **logical, not physical** — it forces the future Query Router to reason about where data lives (`CLAUDE.md` invariant #1). Cross-schema foreign keys and joins are expected and allowed.

### Base Northwind source
- Source: <https://github.com/pthom/northwind_psql> (file `northwind.sql`).
- That script targets the `public` schema by default. It must be adapted to load into `erp_core` (see [Implementation guidance](#implementation-guidance)).
- Base tables to land in `erp_core` (names as in the source): `categories`, `customers`, `customer_demographics`, `customer_customer_demo`, `employees`, `employee_territories`, `order_details`, `orders`, `products`, `region`, `shippers`, `suppliers`, `territories`, `us_states`.

### Identifiers & conventions
- `snake_case` for all custom identifiers.
- The spec text mentions `leadTimeDays`; in Postgres use the column name **`lead_time_days`** (unquoted camelCase folds to lowercase and is error-prone). Document the mapping in the migration comment.
- Custom primary keys use `bigint generated always as identity` unless the row maps 1:1 to a base Northwind key.
- Use `numeric(12,2)` for money, `date` for calendar dates, `timestamptz` for event timestamps, `text` for free text, `jsonb` for flexible metadata.
- Add `created_at timestamptz not null default now()` to custom tables to support later temporal reasoning.

### Migration mechanism
- Each migration is a named migration applied via the Supabase MCP `apply_migration` tool (it records the migration in Supabase's migration history). Use `execute_sql` only for read-back verification, never for schema changes.
- Migrations are also committed to the repo under `db/migrations/` so the schema is reproducible and reviewable outside MCP.
- DDL must be idempotent where practical: `create schema if not exists`, `create table if not exists`. (The Northwind base-data load is **not** idempotent — guard it so it is applied exactly once on a clean DB; do not re-run it over existing data.)

---

## File structure

Create a `db/` tree (the agent applies these via MCP and commits them to the repo):

```text
test-project/
├─ db/
│  ├─ README.md                          # how migrations are applied + ordering
│  └─ migrations/
│     ├─ 0001_create_schemas.sql         # erp_core + erp_docs
│     ├─ 0002_northwind_base.sql         # adapted pthom northwind DDL (into erp_core)
│     ├─ 0003_northwind_seed.sql         # adapted pthom seed data (into erp_core)
│     ├─ 0004_erp_core_custom.sql        # warehouses, shipments, invoices,
│     │                                  #   inventory_movements, price_history
│     └─ 0005_erp_docs.sql               # documents, document_entities,
│                                        #   customer_communications,
│                                        #   supplier_contracts, product_specifications
```

> Splitting Northwind DDL (`0002`) from its seed (`0003`) keeps the structural migration replayable and lets Phase 03 truncate/extend data without touching structure.

---

## Implementation guidance

### Migration `0001` — schemas

```sql
create schema if not exists erp_core;
create schema if not exists erp_docs;
```

### Migrations `0002` / `0003` — base Northwind into `erp_core`

The pthom `northwind.sql` mixes DDL and `INSERT`/`COPY` data and assumes `public`. Adapt it:

1. Download `northwind.sql` from the reference repo.
2. Split it into structure (CREATE TABLE / constraints) and data (INSERT) — `0002` and `0003`.
3. Force the target schema by prefixing each file with:

   ```sql
   set search_path to erp_core;
   ```

   so unqualified `create table orders (...)` lands in `erp_core.orders`. Verify the source uses plain `INSERT` (not `COPY ... FROM stdin`, which MCP cannot stream); if it uses `COPY`, convert those blocks to multi-row `INSERT` statements first.
4. Keep the original intra-Northwind foreign keys (they will now resolve within `erp_core`).

> If the file is large, apply `0003` as the single seed migration but confirm it runs within MCP limits; otherwise chunk the seed into `0003a`, `0003b`, … in table-dependency order (categories/suppliers/customers/employees → products → orders → order_details).

### Migration `0004` — custom `erp_core` tables

```sql
set search_path to erp_core;

-- Warehouse master data
create table if not exists warehouses (
    warehouse_id   bigint generated always as identity primary key,
    code           text not null unique,
    name           text not null,
    location       text,
    warehouse_type text,                       -- e.g. 'central', 'regional'
    capacity_units integer,
    created_at      timestamptz not null default now()
);

-- Shipments connected to customer orders. Central source for ShipmentDelayEvent (Neo4j).
create table if not exists shipments (
    shipment_id            bigint generated always as identity primary key,
    order_id               smallint not null references orders(order_id),
    carrier                text,                -- maps loosely to shippers
    shipper_id             smallint references shippers(shipper_id),
    expected_delivery_date date,
    shipped_date           date,
    actual_delivery_date   date,
    -- positive => late. Generated so it can never disagree with the dates.
    delay_days integer generated always as (
        case
            when actual_delivery_date is not null and expected_delivery_date is not null
            then actual_delivery_date - expected_delivery_date
        end
    ) stored,
    status     text not null default 'pending', -- pending | in_transit | delivered | delayed | cancelled
    created_at timestamptz not null default now()
);

-- Invoices generated from orders
create table if not exists invoices (
    invoice_id     bigint generated always as identity primary key,
    invoice_number text not null unique,
    order_id       smallint not null references orders(order_id),
    invoice_date   date not null,
    due_date       date not null,
    payment_date   date,
    amount         numeric(12,2) not null,
    tax_amount     numeric(12,2) not null default 0,
    total_amount   numeric(12,2) not null,
    status         text not null default 'issued', -- issued | paid | overdue | cancelled
    payment_method text,
    created_at     timestamptz not null default now()
);

-- Inventory movements: inbound / outbound / return / adjustment
create table if not exists inventory_movements (
    movement_id   bigint generated always as identity primary key,
    product_id    smallint not null references products(product_id),
    warehouse_id  bigint not null references warehouses(warehouse_id),
    movement_type text not null,                -- inbound | outbound | return | adjustment
    quantity      integer not null,             -- signed: + inbound, - outbound
    movement_date timestamptz not null,
    reference     text,                          -- e.g. originating order / PO reference
    created_at    timestamptz not null default now()
);

-- Product price change history
create table if not exists price_history (
    price_history_id bigint generated always as identity primary key,
    product_id       smallint not null references products(product_id),
    old_price        numeric(12,2),
    new_price        numeric(12,2) not null,
    effective_date   date not null,
    created_at       timestamptz not null default now()
);
```

### Migration `0005` — `erp_docs` tables

```sql
set search_path to erp_docs, erp_core;

-- Registry of generated / processed documents
create table if not exists documents (
    document_id   bigint generated always as identity primary key,
    doc_type      text not null,               -- contract | invoice | communication | spec
    title         text,
    order_id      smallint references erp_core.orders(order_id),
    supplier_id   smallint references erp_core.suppliers(supplier_id),
    customer_id   bpchar(5) references erp_core.customers(customer_id),
    file_path     text,                         -- nullable in M1 (no PDFs yet)
    status        text not null default 'generated', -- generated | parsed | indexed
    metadata      jsonb not null default '{}'::jsonb,
    created_at    timestamptz not null default now()
);

-- Bridge between documents and the entities they mention/extract
create table if not exists document_entities (
    document_entity_id bigint generated always as identity primary key,
    document_id        bigint not null references documents(document_id),
    entity_type        text not null,           -- supplier | product | order | customer | term
    entity_ref         text not null,           -- the referenced key, as text
    mention            text,
    confidence         numeric(4,3),
    created_at         timestamptz not null default now()
);

-- Customer communications; complaints become CustomerComplaintEvent (Neo4j)
create table if not exists customer_communications (
    communication_id bigint generated always as identity primary key,
    customer_id      bpchar(5) not null references erp_core.customers(customer_id),
    order_id         smallint references erp_core.orders(order_id),
    product_id       smallint references erp_core.products(product_id),
    channel          text,                       -- email | phone | portal
    contact_reason   text,                       -- complaint | inquiry | return | feedback
    subject          text,
    body             text,
    sentiment        text,                       -- negative | neutral | positive
    occurred_at      timestamptz not null,
    created_at       timestamptz not null default now()
);

-- Structured supplier contracts; source of ContractTermEvent (structured-first, ADR 0010)
create table if not exists supplier_contracts (
    contract_id         bigint generated always as identity primary key,
    supplier_id         smallint not null references erp_core.suppliers(supplier_id),
    contract_number     text not null unique,
    lead_time_days      integer,                 -- spec: "leadTimeDays"
    start_date          date not null,
    end_date            date,
    minimum_order_value numeric(12,2),
    status              text not null default 'active', -- active | expired | terminated
    created_at          timestamptz not null default now()
);

-- Product technical sheets / descriptive content
create table if not exists product_specifications (
    spec_id    bigint generated always as identity primary key,
    product_id smallint not null references erp_core.products(product_id),
    title      text,
    spec_text  text,
    attributes jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);
```

> **Type-matching note:** Northwind keys are small ints / fixed-width text. In the pthom schema `customers.customer_id` is `bpchar(5)` and `orders.order_id` is `smallint`. The FK column types above mirror those — verify against the actual loaded base schema with `list_tables` and adjust if the source differs, otherwise FK creation will fail.

### Applying via MCP

For each file, call `apply_migration` with a descriptive name, e.g.:

```text
apply_migration(name="0001_create_schemas", query="<contents of 0001_create_schemas.sql>")
apply_migration(name="0002_northwind_base", query="<contents of 0002_northwind_base.sql>")
...
```

Then verify with `list_tables` (schemas `erp_core`, `erp_docs`) and read-back queries via `execute_sql`.

---

## Acceptance criteria

This phase is complete when **all** of the following hold:

- [ ] `list_tables` shows schemas `erp_core` and `erp_docs`.
- [ ] All base Northwind tables exist in `erp_core` and are populated, verifiable by row counts, e.g. `select count(*) from erp_core.customers;` (≈91) and `select count(*) from erp_core.orders;` (≈830 in the original seed).
- [ ] The five custom `erp_core` tables exist: `warehouses`, `shipments`, `invoices`, `inventory_movements`, `price_history` (created empty — `count(*) = 0`).
- [ ] The five `erp_docs` tables exist: `documents`, `document_entities`, `customer_communications`, `supplier_contracts`, `product_specifications` (created empty).
- [ ] Cross-schema foreign keys resolve — e.g. inserting a `supplier_contracts` row with a non-existent `supplier_id` is rejected (spot-check, then rollback / delete).
- [ ] `shipments.delay_days` is a stored generated column and computes correctly for a test row with known dates (then remove the test row).
- [ ] All migration files are present under `db/migrations/` in the documented order and are committed to git.
- [ ] `db/README.md` explains the migration order and how they are applied via Supabase MCP.
- [ ] Re-reading the schema (`list_tables`) matches the column definitions in this directive (allowing for the verified base-type adjustments).

A short verification query block to include in `db/README.md`:

```sql
-- schemas
select schema_name from information_schema.schemata
where schema_name in ('erp_core','erp_docs');

-- custom table inventory
select table_schema, table_name
from information_schema.tables
where table_schema in ('erp_core','erp_docs')
order by table_schema, table_name;
```

---

## Out of scope (do NOT do in this phase)

- **Generating extended/synthetic data or the Controlled Scenarios** (Tokyo Traders, Exotic Liquids, Pavlova, Grandma Kelly's) — that is **Phase 03**. Custom tables ship **empty**; the base Northwind seed is the only data loaded here.
- Any Neo4j work: schemas, projection, nodes, relationships, Event Nodes — **Phase 05+**.
- Any Qdrant collections, embeddings, or chunking — **Phase 07**.
- Query validators / guardrails, the SQL executor, text-to-SQL, `answer_trace` — **Phase 04+**.
- LangChain / LangGraph / LLM wiring — **Phase 04 / Phase 08**.
- A `purchase_orders` table and any PDF/delivery-note document flows — out of scope for Milestone 1 (`docs/PRD.md` "Out of Scope"). Do not add them.
- Row-Level Security, auth, roles, or deployment hardening — out of scope for Milestone 1.
- Indexes for performance tuning beyond primary/foreign keys and natural `unique` constraints — defer; add only if a later phase needs them.

---

## References

- `docs/ISSUES.md` → Issue 2 (SQL-only ladder step depends on this schema) and the data-layer portion of the roadmap.
- `Project_Idea.md` §3.1 (Northwind starting point), §3.2 (schema split `erp_core`/`erp_docs`), §3.3 (custom tables and their purpose), §13 Phase 1 (roadmap).
- `CLAUDE.md` → Architecture invariant #1 (three-layer storage, data born in PostgreSQL, the deliberate schema split).
- `docs/adr/0010-contract-term-events-from-structured-source-first.md` → why `supplier_contracts.lead_time_days` is structured-first.
- `docs/PRD.md` → implementation decisions on `erp_core`/`erp_docs` contents; Out of Scope list.
- Reference dataset: <https://github.com/pthom/northwind_psql>.
