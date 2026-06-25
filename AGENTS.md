# Repository Guidelines

## Project Structure & Module Organization

This repository contains the NorthwindAI specification plus a runnable Python backend, database migrations, synthetic data tooling, Neo4j projection code, query ladder code, evaluation artifacts, and tests. Treat directives, ADRs, and glossary terms as the source of truth for current implementation work.

- `Project_Idea.md`: concept, architecture, roadmap, and stack.
- `CONTEXT.md`: domain glossary; use these terms in code, docs, tests, and comments.
- `docs/PRD.md`: requirements, user stories, and implementation/testing decisions.
- `docs/ISSUES.md`: dependency-ordered implementation slices. Start with Issue 1 and respect `Blocked by`.
- `docs/adr/`: binding architectural decisions for storage, graph, routing, provenance, and query validation.
- `CLAUDE.md`: agent-facing context and implementation invariants.

## Build, Test, and Development Commands

There is no build system or test suite yet. When Issue 1 lands, add concrete commands here. The intended stack is Python 3.11+, FastAPI, LangGraph, PostgreSQL/Supabase, Neo4j, and Qdrant.

Expected future commands should cover:

- `python -m venv .venv`: create a local Python environment.
- `docker compose up neo4j qdrant`: start graph and vector services.
- `uvicorn app.main:app --reload`: run the future FastAPI backend.
- `pytest`: run automated tests.

Document what each command starts, tests, or validates.

## Coding Style & Naming Conventions

Prefer domain terms from `CONTEXT.md`, including `AI Agent Query`, `ERP Domain Graph`, `Operational Source of Truth`, `Knowledge Layer`, `Graph Provenance`, `Controlled Scenario`, and `Golden Query`. Avoid rejected synonyms.

Use Python `snake_case` for modules, functions, and variables. Use `PascalCase` for classes and graph Event Node labels such as `ShipmentDelayEvent`, `CustomerComplaintEvent`, `DeliveryDelayComplaintEvent`, `PackagingQualityComplaintEvent`, and `ProductQualityComplaintEvent`. Keep SQL schemas explicit: `erp_core` for operational facts and `erp_docs` for documents and communications.

For Phase 06 complaint issue modeling, treat `erp_docs.customer_communications.subject` as the structured source classification and map it to normalized `issue_type` values. Preserve `body` as evidence text, but do not use body keyword matching as the primary classifier.

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
