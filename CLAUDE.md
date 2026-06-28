# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

This repository contains a Python backend, database migrations, synthetic data
tooling, query ladder code, evaluation artifacts, and tests from the completed
early phases. The source of truth for what to build next is, in priority order:

Use `directives/` together with `docs/ISSUES.md`: directives capture the active
phase-level implementation decisions that refine the issue slices.

- [Project_Idea.md](Project_Idea.md) — full project specification (domain, architecture, stack, roadmap, milestones).
- [docs/PRD.md](docs/PRD.md) — problem statement, 48 user stories, implementation/testing decisions, out-of-scope list.
- [docs/ISSUES.md](docs/ISSUES.md) — the PRD broken into 13 dependency-ordered, independently-buildable slices. **Build in this order**; each issue lists `Blocked by`.
- [CONTEXT.md](CONTEXT.md) — domain glossary. Use these exact terms (and avoid the listed `_Avoid_` synonyms) in code, comments, and docs.
- [docs/adr/](docs/adr/) — ADRs 0001–0014 record the binding architectural decisions referenced below.

When implementing, work issue-by-issue from ISSUES.md. Issue 1 (dev stack health check) is the only one with no blockers. The overarching strategy is the **progressive query ladder** (Step 1 SQL-only → Step 5 Golden Query): prove one layer at a time before composing them. Do not attempt the Golden Query first.

## Project: NorthwindAI

A mini-ERP GraphRAG intelligence suite built on an extended [Northwind](https://github.com/pthom/northwind_psql) dataset. The first milestone delivers **AI Agent Query**: an agentic assistant that routes business questions across PostgreSQL, Neo4j, and Qdrant and returns governed, traceable answers.

## Architecture invariants (do not violate)

These are decisions captured in ADRs and the PRD. They are the "why" that is not obvious from any single file:

1. **Three-layer storage with a strict data/knowledge boundary.** Data is *born* in PostgreSQL; derived knowledge is *born* in Neo4j.
   - **PostgreSQL/Supabase = Operational Source of Truth** — raw ERP facts (dates, amounts, statuses, quantities). Split into two logical schemas: `erp_core` (transactional: customers, orders, order_details, products, suppliers, shipments, invoices, warehouses, inventory_movements, price_history, …) and `erp_docs` (documents, document_entities, customer_communications, supplier_contracts, product_specifications). The schema split is deliberate — it forces the router to reason about where data lives.
   - **Neo4j = Knowledge Layer** — the ERP Domain Graph, instance-level (rows become concrete nodes like `Customer:ALFKI`, `Order:11077`; tables define node *types*). Event Nodes (`ShipmentDelayEvent`, `CustomerComplaintEvent`, `DeliveryDelayComplaintEvent`, `PackagingQualityComplaintEvent`, `ProductQualityComplaintEvent`, `StockOutEvent`, `InvoiceOverdueEvent`, `ContractTermEvent`) live **only in Neo4j** and must never be materialized in PostgreSQL (ADR 0004).
   - **Qdrant = Vector Store** — chunk text, embeddings, metadata, semantic retrieval. Neo4j stores *references* to documents/chunks (e.g. `vector_chunk_ids`) but **never embeddings or full chunk text** (ADR 0006).

2. **Graph provenance is mandatory** (ADR 0005). Every node and relationship must carry traceable provenance metadata: `source_system`, `source_schema`, `source_table`, `source_pk`, `projection_version`, `rule_name`, `rule_version`, `confidence`, `derived_from` (not every field on every node, but every element must be traceable to its source/rule).

3. **Two relationship families.** *Explicit* relationships come directly from trusted ERP links (foreign keys). *Derived* relationships come from controlled pipelines/business rules — **never raw LLM guesses**. Prefer readable multi-hop paths (`Supplier → Product → Order → Shipment → ShipmentDelayEvent`) over shortcut edges.

4. **Classified and supported relationships, not raw causality claims** (ADR 0012). Links between events must come from explicit evidence or controlled rules, never raw LLM guesses. In Phase 06, complaint issue nodes are linked with `CLASSIFIED_AS` from `erp_docs.customer_communications.subject`; delivery-delay complaint nodes use `SUPPORTED_BY_DELAY` only when a matching `ShipmentDelayEvent` exists for the same order/product.

5. **Guardrails are enforced in code, not prompts** (ADR 0009). Generated SQL and Cypher must pass a code-level validator (e.g. `query_validator.py`) before execution:
   - SQL: `SELECT`-only; schema allowlist (`erp_core`, `erp_docs`); table allowlist; block `INSERT/UPDATE/DELETE/DROP/ALTER`; row limits.
   - Cypher: read-only; block `CREATE/MERGE/DELETE/SET/REMOVE`; label/relationship allowlist; path-depth limits; timeouts.
   - Validation results must be returnable in `answer_trace`.

6. **Every non-trivial answer returns a structured `answer_trace`** (ADR 0003): `route`, `generated_sql`, `generated_cypher`, `graph_paths`, `retrieved_chunks`, `documents_used`, `metrics`, `validation_results`, `provenance`. This is the primary debugging/governance/evaluation surface.

7. **Routing is explicit.** A LangGraph Query Router classifies each question into one of: `sql_only`, `graph_only`, `vector_only`, `graph_plus_sql`, `graph_plus_vector`, `sql_plus_graph_plus_vector` (ADR 0002). GraphRAG is **not** used for everything — point/aggregate questions stay SQL-first; GraphRAG is for multi-hop traversal, events, temporal relationships, and documents.

8. **ContractTermEvents come from structured fields first** (ADR 0010). Derive them from `supplier_contracts` columns (e.g. `leadTimeDays`) before introducing PDF parsing.

9. **Top Customers = ranked by net revenue** over the analysis period (ADR 0013), computed at query time — never stored manually. First ladder step: top 10 by revenue over the last 12 months.

10. **Synthetic data is deterministic** (fixed seed) and must include **Controlled Scenarios** (ADR 0011): intentional positive cases, negative cases, and false-positive traps (e.g. delays toward non-top customers, complaints unrelated to delays) so the Golden Query and evaluation are meaningful — not random data hoping for interesting patterns.

11. **Complaint issue classification uses structured source data in this PoC.** For Phase 06, `erp_docs.customer_communications.subject` is the simulated upstream classifier output and must be mapped to a normalized `issue_type` (`delivery_delay`, `packaging_quality`, `product_quality`). Preserve `body` as evidence text, but do not use body keyword matching as the primary classifier. `DeliveryDelayComplaintEvent` requires both a delivery-delay issue classification and matching `ShipmentDelayEvent` support for the same order/product; packaging and product-quality complaint Event Nodes are derived directly from their classified issue type.

12. **Phase 07 contract retrieval is checkpointed and evidence-first.** Implement Phase 07 as two verified checkpoints: 07A proves structured `Supplier -> Contract -> ContractTermEvent` traversal before 07B adds PDFs, Qdrant, and Step 4 retrieval. `Contract` is a business entity node; `ContractTermEvent` is one atomic term node per term type with `term_key = "<contract_id>:<term_type>"`; `Document` is a reference node only and must not store full text or embeddings. Use local BGE embeddings by default (`BAAI/bge-small-en-v1.5`) and local OpenDataLoader PDF parsing for the live indexing path. Step 4 is evidence-first and deterministic: combine structured lead-time data with retrieved contract chunks; do not introduce LLM synthesis in this phase.

## Intended stack (per spec, not yet scaffolded)

- **Backend/AI:** Python 3.11+, FastAPI, LangChain, LangGraph. LLMs via OpenRouter (cloud) and Hugging Face/Ollama (local).
- **Storage:** Supabase PostgreSQL; Neo4j Community (Docker); Qdrant (Docker). Expect Docker Compose for Neo4j + Qdrant.
- **Documents:** OpenDataLoader PDF (`langchain-opendataloader-pdf`). First document type is the supplier contract; clean digital PDFs before OCR/noisy docs.
- **Synthetic data libs:** Faker, numpy, scipy, pandas.
- **Frontend (later):** React/Next.js with Database Explorer, AI Agent Chat (must render an inspectable `answer_trace`), and Document Processing pages.

## Testing approach (per PRD)

There is no test suite yet. When tests are introduced, the highest-value seam is the **query ladder** (test external behavior/contracts, not implementation details). Each ladder step gets an *expected answer spec* (behavioral, not a fixed string) plus a persisted *actual answer_trace*, so failures can be localized to routing vs. query generation vs. traversal vs. retrieval vs. synthesis. Validator tests must prove mutation SQL/Cypher is rejected and read-only is accepted.

## Out of scope for the first milestone

OCR/noisy documents, structured-vs-PDF discrepancy detection, complex invoice/delivery-note processing, the Predictive Engine, production auth/deployment hardening, and a polished frontend. Do not pull these forward.
