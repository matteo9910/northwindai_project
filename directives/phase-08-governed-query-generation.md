# Phase 08 — Governed Query Generation (Semantic Catalog + Specialized Workers)

> Realizes part of Issue 10. Binds ADR 0009 (code guardrails), 0015 (agentic
> orchestration), 0016 (model strategy). Prerequisite: Phases 04–07 (ladder +
> validators + executors + `answer_trace`) are built and stay unchanged.

This is the phase where the **guardrails stop being dormant**: queries move from
hard-coded templates to **LLM-generated**, and the existing validators become the
gate. No Supervisor and no loop yet (Phase 09) — this phase delivers the
generation primitives the agent will orchestrate.

## Objective

For a single `(sub_question, target_store)` pair, produce a **validated, executed**
result plus a trace fragment, via a per-store **Specialized Worker** that grounds
generation in a curated **Semantic Catalog** and self-repairs within a bounded
number of attempts. Reuse the governed execution paths already built:

- SQL: the governed validate→execute path from the Top Customers step (Issue 2).
- Cypher: `validate_cypher` + `run_validated_cypher` (Steps 2–4).
- Vector retrieval already exists (`search_vector_chunks`) and needs **no
  generation** — it is wired in Phase 09, not here.

## Design decisions

1. **LLM client behind an abstraction (ADR 0016).** One module wraps the model
   calls; model is selected **per role** from config. Models reached via OpenRouter
   (`anthropic/claude-opus-4-8`, `anthropic/claude-sonnet-4-6`). `temperature`/
   `top_p`/`top_k` are **unavailable** on these models — do not send them; steer
   with the prompt and `effort`. Keep the abstraction thin enough to later point at
   the Anthropic API directly where prompt caching / `effort` matter.
2. **Semantic Catalog is curated, assembled from existing sources.** Per-store
   slices built from: the SQL schema (`erp_core`/`erp_docs` tables, columns, types),
   the Neo4j labels/relationships from `projection.py`, the `CONTEXT.md` glossary,
   the validator allowlists, and a few example values / join paths. Each worker gets
   **only its store's slice** (the SQL worker never sees graph labels, etc.).
3. **Model per worker (ADR 0016):** SQL worker → Sonnet 4.6; Cypher worker →
   Opus 4.8 (text-to-Cypher is the hardest task). Configurable.
4. **Generate → validate → repair, bounded (ADR 0009).** The worker generates a
   query, runs it through the store's validator, and on a validation failure **or**
   an execution error feeds the precise cause (the validator `violations` list, or
   the DB error) back to the model and regenerates, up to `max_repair_attempts`
   (config, default 2). On final failure it returns a **structured failure**, never
   an exception that aborts the caller.
5. **Structured output.** The worker returns a typed result carrying the generated
   query, the validation result, the rows/records, metrics, and the repair attempts
   — everything the Phase 09 trace will need. An empty result set is **not** a
   failure (that is a sufficiency concern for Phase 09).

## Functional requirements

1. `LLMClient` (or equivalent) with a `generate_structured(role, system, user, schema)`
   surface; role → model resolved from config; OpenRouter key from `config.py`.
2. `SemanticCatalog` exposing `slice_for("sql")` / `slice_for("cypher")` (and a
   stub `slice_for("vector")` describing the collection + filter contract).
3. `SqlWorker` and `CypherWorker` implementing generate→validate→repair→execute,
   each returning a `WorkerResult` (success|failure, query, validation, rows,
   metrics, attempts).
4. Config additions: per-role model ids, `max_repair_attempts`, OpenRouter base URL.
5. Reuse the existing validators/executors verbatim — do not fork them.

## File structure

- `backend/agent/__init__.py`
- `backend/agent/llm.py` — model-per-role client over OpenRouter.
- `backend/agent/catalog.py` — Semantic Catalog assembly + per-store slices.
- `backend/agent/workers/sql_worker.py`, `backend/agent/workers/cypher_worker.py`.
- `backend/agent/types.py` — `WorkerResult`, `ExecutionPlan` stub, shared models.
- `backend/config.py` — `planner_model`, `sql_worker_model`, `cypher_worker_model`,
  `synthesis_model`, `max_repair_attempts`, `openrouter_base_url`.
- `pyproject.toml` — add the OpenRouter/LLM client dependency if missing.

## Tests

- Catalog slices contain the right store's objects and exclude others; allowlists
  and glossary terms are present.
- Worker repair loop: a stubbed LLM that first returns an invalid query (e.g. a
  mutation, or a non-allowlisted label) then a valid one → worker validates,
  repairs once with the `violations` fed back, and succeeds within the cap.
- Worker final failure: stubbed LLM that never produces a valid query → structured
  failure after `max_repair_attempts`, no exception, attempts recorded.
- Generated read-only queries pass; generated mutations are rejected by the
  existing validators (proves the gate works on generated input).
- Live tests (real model) skip cleanly when `OPENROUTER_API_KEY` is unset.
- `pytest` and `ruff check .` pass.

## Out of scope

- The Supervisor, routing, the plan-execute loop, the Sufficiency Check
  (Phase 09).
- Evidence-first LLM synthesis and evaluation (Phase 10).
- The vector worker wiring (Phase 09) — only the catalog contract is stubbed here.
- Local LLM serving; prompt-cache tuning (note the seam, implement later).

## References

- CLAUDE.md invariants #5 (code guardrails), #6 (`answer_trace`), #13 (agentic).
- ADR 0009 (guardrails), 0015 (orchestration), 0016 (model strategy).
- CONTEXT.md: `Specialized Worker`, `Semantic Catalog`.
