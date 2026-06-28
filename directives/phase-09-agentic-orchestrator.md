# Phase 09 — Agentic Orchestrator (Supervisor plan-execute loop)

> Realizes Issues 10 and the orchestration half of 12. Binds ADR 0002 (routing),
> 0015 (orchestration), 0017 (answer contract). Prerequisite: Phase 08 (workers +
> catalog + LLM client).

This phase delivers the **agentic core**: a Supervisor that turns an arbitrary
in-domain question into a governed, traceable answer by planning, dispatching to
the Phase 08 workers, judging sufficiency, and iterating under a hard cap.

## Objective

Implement the **Supervisor** as a LangGraph plan-execute loop (ADR 0015):

```
question → plan (route + per-store sub-tasks) → dispatch to workers →
gather evidence → Sufficiency Check → (re-plan, bounded) → assemble answer + trace
```

with three terminal outcomes: **answered**, **needs_clarification**, **abstained**.
Synthesis *prose* is Phase 10 — this phase assembles a deterministic answer from
the gathered evidence so the loop and trace are testable end to end.

## Design decisions

1. **Plan-execute + bounded reflection (ADR 0015).** The planner (Opus 4.8)
   produces an explicit `ExecutionPlan`: a route family (`sql_only`, `graph_only`,
   `vector_only`, `graph_plus_sql`, `graph_plus_vector`,
   `sql_plus_graph_plus_vector` — ADR 0002) plus the per-store sub-tasks. The
   Supervisor dispatches each sub-task to its Phase 08 worker.
2. **Supervisor is the only brain.** Workers are non-autonomous; the Supervisor
   owns routing, sufficiency, and iteration. No nested agent loops.
3. **Vector worker plugs in here.** It performs **no generation** — it embeds the
   user question locally and searches Qdrant scoped by filters **resolved from the
   graph step** (e.g. `supplier_id`, `document_id`), via the existing
   `search_vector_chunks` + `validate_vector_search`. The mandatory metadata filter
   (ADR 0009) is non-negotiable; values come from prior structured results, never
   from raw user/LLM text.
4. **Hybrid Sufficiency Check under a hard cap (ADR 0015).** Deterministic guards
   first (all planned sub-tasks executed? any hard worker failure? iteration cap
   reached?), then an LLM judgment (Opus 4.8) on semantic completeness. A hard cap
   (config, default 2 re-plans) bounds the loop regardless of the LLM. A re-plan is
   **targeted** (add/replace specific sub-tasks), not a full restart.
5. **Terminal outcomes (ADR 0017).** Genuinely ambiguous question → one targeted
   **clarification** question (`needs_clarification`); minor under-specification →
   proceed with a stated assumption; out-of-domain → refuse; evidence still
   insufficient at the cap → **abstain** (state what could not be determined). The
   abstention/clarification *decision* lives here; the *prose* is Phase 10.
6. **One `answer_trace`, same shape (ADR 0003).** Populate `route`,
   `generated_sql`, `generated_cypher`, `graph_paths`, `retrieved_chunks`,
   `documents_used`, `metrics`, `validation_results` (SQL/Cypher/vector union), and
   `provenance` from the gathered evidence — plus the plan and the sufficiency
   decisions so the autonomy is inspectable.

## Functional requirements

1. `ExecutionPlan` / agent state model (question, plan, gathered evidence per
   store, iteration count, trace fragments, outcome).
2. Planner node: question + catalog → `ExecutionPlan` (structured output, Opus 4.8).
3. Dispatch node: run the planned sub-tasks through the Phase 08 SQL/Cypher
   workers and the new vector worker; collect `WorkerResult`s.
4. `VectorWorker`: filters resolved from graph evidence; wraps the existing scoped,
   validated Qdrant search.
5. Sufficiency node: deterministic guards + LLM judgment; emits continue / re-plan
   (bounded) / answer / clarify / abstain.
6. Assembly node: build the answer object and the full `answer_trace`. Deterministic
   evidence assembly for now (Phase 10 swaps in evidence-first synthesis).
7. `POST /agent/query` → `{ outcome, answer | clarification | abstention,
   answer_trace }`; CLI `--emit-trace` mirroring the ladder steps.

## File structure

- `backend/agent/graph.py` — the LangGraph Supervisor (nodes + edges + cap guard).
- `backend/agent/planner.py`, `backend/agent/sufficiency.py`.
- `backend/agent/workers/vector_worker.py`.
- `backend/agent/assemble.py` — answer + `answer_trace` assembly.
- `backend/agent/router.py` — `POST /agent/query`; wire into `backend/main.py`.
- extend `backend/agent/types.py` from Phase 08.

## Tests

- Routing: representative questions map to the expected route family (a simple
  point/aggregate question → `sql_only`; a contract-lead-time question →
  `graph_plus_vector`; a Golden-Query-shaped question → the tri-store route).
- Loop terminates: the hard cap is enforced even when the LLM keeps asking for
  more (stub the sufficiency LLM to always say "need more" → loop stops at the cap
  and abstains).
- Vector worker is always scoped: a search without graph-resolved filters is
  refused by `validate_vector_search`.
- Terminal outcomes: ambiguous question → `needs_clarification`; out-of-domain →
  refusal; insufficient evidence at cap → `abstained`.
- `answer_trace` fully populated incl. plan + sufficiency decisions; validators
  present for every executed query.
- A previously deterministic ladder question, asked through the agent, returns an
  answer consistent with the ladder baseline (the agent generalizes the ladder).
- Live tests skip cleanly when models/services are unconfigured.
- `pytest` and `ruff check .` pass.

## Out of scope

- Evidence-first LLM synthesis prose and the evaluation suite (Phase 10).
- Multi-turn conversation memory (each request independent; clarification reply is
  a new request).
- Autonomous sub-agents; parallel speculative execution beyond the planned set.

## References

- CLAUDE.md invariants #5, #6, #7, #13.
- ADR 0002 (routing), 0003 (`answer_trace`), 0009 (guardrails), 0015
  (orchestration), 0017 (answer contract).
- CONTEXT.md: `Supervisor`, `Specialized Worker`, `Execution Plan`,
  `Sufficiency Check`, `Clarification`, `Abstention`, `In-domain Question`.
