# Repository Guidelines

## Project Structure & Module Organization

This repository contains the NorthwindAI specification plus a runnable Python backend, database migrations, synthetic data tooling, Neo4j projection code, vector indexing code, query ladder code, evaluation artifacts, and tests. Treat directives, ADRs, and glossary terms as the source of truth for current implementation work.

- `Project_Idea.md`: concept, architecture, roadmap, and stack.
- `CONTEXT.md`: domain glossary; use these terms in code, docs, tests, and comments.
- `docs/PRD.md`: requirements, user stories, and implementation/testing decisions.
- `docs/ISSUES.md`: dependency-ordered implementation slices. Start with Issue 1 and respect `Blocked by`.
- `docs/adr/`: binding architectural decisions for storage, graph, routing, provenance, and query validation.
- `CLAUDE.md`: agent-facing context and implementation invariants.

## Build, Test, and Development Commands

Use Python 3.11+. Common commands:

- `python -m venv .venv`: create a local Python environment.
- `pip install -e ".[dev]"`: install runtime and dev dependencies.
- `docker compose up -d neo4j qdrant`: start graph and vector services.
- `uvicorn backend.main:app --reload`: run the FastAPI backend.
- `python -m backend.graph.projection`: project PostgreSQL data into Neo4j.
- `python -m data_generation.contracts`: generate deterministic supplier contract PDFs.
- `python -m data_generation.contract_documents`: set supplier contract `documents.file_path` values in PostgreSQL as a data-prep step.
- `python -m backend.vector.indexer`: index supplier contract chunks into Qdrant and update Neo4j `Document.vector_chunk_ids`.
- `pytest`: run automated tests.
- `ruff check .`: run linting.

Phase 07 live PDF indexing requires Java 11+ on `PATH` for OpenDataLoader.

## Coding Style & Naming Conventions

Prefer domain terms from `CONTEXT.md`, including `AI Agent Query`, `ERP Domain Graph`, `Operational Source of Truth`, `Knowledge Layer`, `Graph Provenance`, `Controlled Scenario`, and `Golden Query`. Avoid rejected synonyms.

Use Python `snake_case` for modules, functions, and variables. Use `PascalCase` for classes and graph labels such as `ShipmentDelayEvent`, `CustomerComplaintEvent`, `DeliveryDelayComplaintEvent`, `PackagingQualityComplaintEvent`, `ProductQualityComplaintEvent`, `Contract`, `ContractTermEvent`, and `Document`. Keep SQL schemas explicit: `erp_core` for operational facts and `erp_docs` for documents and communications.

For Phase 06 complaint issue modeling, treat `erp_docs.customer_communications.subject` as the structured source classification and map it to normalized `issue_type` values. Preserve `body` as evidence text, but do not use body keyword matching as the primary classifier.

For Phase 07 contract retrieval, implement and reason in two checkpoints: structured `Supplier -> Contract -> ContractTermEvent` first, then PDF/Qdrant retrieval. `Document` nodes are references only: no full text or embeddings in Neo4j. Step 4 is evidence-first and deterministic, with no LLM synthesis.

## Testing Guidelines

Tests should validate observable behavior and contracts, not implementation details. Prioritize the progressive query ladder:

1. SQL-only Top Customers.
2. Neo4j supplier-to-product traversal.
3. Event Node traversal with classified complaint issue events.
4. Graph-to-Qdrant contract retrieval.
5. Golden Query orchestration.

Validator tests must reject mutation SQL/Cypher and accept allowed read-only queries. Persist expected answer specs and actual `answer_trace` outputs for ladder evaluations.

## Commit & Pull Request Guidelines

This directory is not currently a Git repository, so no history conventions can be inferred. Once Git is initialized, use concise imperative subjects such as `Add query validator smoke tests`.

Pull requests should include the issue slice, behavior summary, test evidence, and any ADR or glossary impact. Link screenshots only when frontend or visual trace rendering exists.

## Agent-Specific Instructions

Build issue-by-issue from `docs/ISSUES.md`, refined by the active phase directive in `directives/`. Preserve the PostgreSQL/Neo4j/Qdrant boundary, require Graph Provenance, enforce query guardrails in code, and do not attempt the Golden Query before earlier ladder steps pass.
