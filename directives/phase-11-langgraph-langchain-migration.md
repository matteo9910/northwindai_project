# Phase 11 — Migrate the agentic layer to LangChain + LangGraph

> Re-aligns the implementation with its own Phase 09 directive and the intended stack.
> Refactor of Phases 08–10 (`backend/agent/`): no behavior change to governance or the
> answer contract — only the LLM transport and the orchestration control-flow change.

## Context

The governed agentic assistant (Phases 08–10) lives in `backend/agent/` and works
(live-verified). But it was **hand-rolled**: the Supervisor loop is a plain `for` loop
in `backend/agent/graph.py`, and every LLM call goes through a custom
`OpenRouterLLMClient` (raw `httpx` + regex JSON parsing) in `backend/agent/llm.py`.

This contradicts the **stated stack and the Phase 09 directive itself**, which says
*"Implement the Supervisor as a LangGraph plan-execute loop"*
(`directives/phase-09-agentic-orchestrator.md:13`) and lists `graph.py` as
*"the LangGraph Supervisor"*. CLAUDE.md's intended stack also names a "LangGraph Query
Router".

**Goal:** re-implement the orchestration and all LLM interactions with **LangGraph**
(StateGraph for the plan-execute-reflect loop) and **LangChain** (`ChatOpenRouter`
from the official OpenRouter integration, `ChatPromptTemplate`,
`.with_structured_output`), idiomatically, replacing the hand-rolled code outright.
Motivation: framework skill-building + production-grade orchestration. Confirmed
decisions: **full idiomatic depth** and **clean replacement** (no legacy/flagged
fallback).

### Non-negotiable invariant: governance is preserved exactly

The LLM now *drives* routing/generation through a framework, but the **rails do not
move** (CLAUDE.md invariants 5–7, 13). These stay as the authority, unchanged:

- `backend/query/validator.py` (`validate_sql`) and `backend/graph/cypher_validator.py`
  (`validate_cypher`) — code-level guardrails, **not prompts**.
- `backend/query/executor.py` (`run_validated_sql`) and
  `backend/graph/cypher_executor.py` (`run_validated_cypher`) — execution.
- `backend/vector/retriever.py` (`validate_vector_search`, `search_vector_chunks`) —
  mandatory metadata filter scoping.
- `backend/agent/catalog.py` (`SemanticCatalog`) — grounding context.
- `backend/query/trace.py` (`AnswerTrace`) — the answer contract.
- The Pydantic contract types in `backend/agent/types.py` (`ExecutionPlan`,
  `ExecutionTask`, `WorkerResult`, `SufficiencyDecision`, `EvidenceBundle`, `Citation`,
  `AgentQueryRequest/Response`) — kept; they become the `.with_structured_output`
  schemas and the LangGraph state payloads.

LangChain/LangGraph replace **transport + control flow only**. The generate → validate
→ repair → execute discipline and the trace shape are untouched in behavior.

## Dependencies (add to `pyproject.toml`)

```
langgraph>=0.2,<1.0
langchain-core>=1.0,<2.0
langchain-openrouter>=0.0.2,<1.0
```

(`langchain` meta-package not required; we use `langchain-core` +
`langchain-openrouter`.) No checkpointer / `langgraph-checkpoint` — multi-turn memory
stays out of scope per the directives (each request independent). Then
`pip install -e .` into `.venv`.

## Architecture

### 1. LLM transport — `backend/agent/llm.py` (rewrite)

Replace `OpenRouterLLMClient` (httpx) with a small factory over LangChain's
official OpenRouter integration:

```python
def build_chat_model(role: AgentRole, settings: Settings) -> BaseChatModel:
    return ChatOpenRouter(
        model=_model_for(role, settings),          # opus/sonnet per role (keep mapping)
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key,
        max_tokens=settings.openrouter_max_tokens,
        app_url="https://localhost/northwindai",
        app_title="NorthwindAI",
        reasoning={"effort": settings.openrouter_reasoning_effort},
        openrouter_provider={"require_parameters": True},
    )
```

- **Temperature gotcha (must verify, see Risks):** these Anthropic models reject
  `temperature`/`top_p` (ADR 0016). Do not pass temperature/top_p/top_k from our
  factory; verify the wire payload during live smoke.
- Keep the three exception types (`LLMConfigurationError`, `LLMProviderError`,
  `LLMResponseError`) — the FastAPI router and tests depend on them. Add a thin
  translation: missing key → `LLMConfigurationError`; `openai.APIError`/HTTP →
  `LLMProviderError`; structured-output parse failure → `LLMResponseError`. Keeps the
  503 mapping in `router.py` and `test_agent_supervisor.py` green.
- Drop the bespoke `parse_json_object` — `.with_structured_output(Model)` replaces it.

### 2. Components become LCEL chains (full idiomatic)

Each LLM-using component keeps its **class, constructor injection, and public method
signature** (so the Supervisor wiring and component contracts stay stable), but its
internals become a `ChatPromptTemplate | chat_model.with_structured_output(Model)`
chain instead of a `generate_structured` dict call.

- `planner.py` — `Planner.plan()` returns an `ExecutionPlan` via
  `.with_structured_output(ExecutionPlan)`. **Keep** the route coercion in `_parse_plan`
  (terminal `refuse`/`clarify` echoed into `route` → normalize to `sql_only`
  placeholder) as a post-validator.
- `workers/sql_worker.py`, `workers/cypher_worker.py` — `_generate_query` becomes an
  LCEL chain returning a small `GeneratedQuery` Pydantic model (`query`, `rationale`).
  The **repair loop stays** (generate → validate → repair → execute), driven by the
  existing validators.
- `sufficiency.py` — deterministic guards first, then the LLM judgment via
  `.with_structured_output(SufficiencyDecision)`.
- `synthesis.py` — `.with_structured_output` over a `SynthesisOutput` model (answer +
  citations). Keep the deterministic fallback when no model is injected.
- `workers/vector_worker.py` — **unchanged** (no LLM; already a clean wrapper over the
  validated Qdrant search). Confirms the invariant: vector worker has no generation model.

Injection seam shift: components currently take an `LLMClient`. They will instead take a
LangChain `BaseChatModel` (or default to `build_chat_model(role, settings)`). This is
the one interface change that ripples into tests (see Test strategy).

### 3. Orchestration — `backend/agent/graph.py` (rewrite as LangGraph StateGraph)

Replace the `for iteration in range(...)` loop with a compiled `StateGraph`.

- **State** (`AgentState`, a `TypedDict` or Pydantic): `question`, `plan`,
  `worker_results`, `sufficiency_decisions`, `iteration`, `feedback`, `response`.
- **Nodes** (thin wrappers around the existing component objects — components hold the
  logic, LangGraph only wires them):
  - `plan_node` → `Planner.plan(question, feedback)`
  - `dispatch_node` → runs planned sub-tasks through the SQL/Cypher/vector workers in
    `depends_on` order; **keep `_augment_sub_question`** (inlines upstream rows into
    dependent SQL/Cypher sub-questions — bug-fix #2, must survive the rewrite).
  - `sufficiency_node` → `SufficiencyChecker.check(bundle, iteration, max_replans)`
  - `synthesize_node` → `EvidenceFirstSynthesizer.synthesize(bundle, decision)`
  - `assemble_node` → `build_answer_trace(bundle)` + `AgentQueryResponse`
- **Edges / control flow:**
  - `START → plan`
  - conditional after `plan`: terminal (`refuse`/`clarify`) → `synthesize`; else →
    `dispatch`
  - `dispatch → sufficiency`
  - conditional after `sufficiency`: `replan` **and** under cap → back to `plan` (set
    `feedback`, increment `iteration`); else → `synthesize`
  - `synthesize → assemble → END`
  - Hard cap enforced in state (mirrors `max_supervisor_replans`); also set the graph's
    `recursion_limit` as a backstop. Deliberately **not** using `create_react_agent` —
    we want explicit, governed control flow, not an autonomous ReAct loop (invariant 13:
    non-autonomous workers, Supervisor is the only brain).
- `AgentSupervisor` stays as the **façade**: `__init__` still accepts injected `planner`,
  `sql_worker`, `cypher_worker`, `vector_worker`, `sufficiency`, `synthesizer` (so
  `test_agent_supervisor.py` keeps working), builds the components, compiles the
  StateGraph once, and `run(question)` calls `graph.invoke(...)` and returns the
  `AgentQueryResponse`. Terminal/abstain/clarify/refuse map to the same `AgentOutcome`s
  as today.

### 4. Unchanged

`router.py`, `cli.py`, `main.py`, `assemble.py`, `catalog.py`, `types.py` (additive only:
small `GeneratedQuery`/`SynthesisOutput` helper models), and all foundation modules.
`router.py`/`cli.py` already depend only on `AgentSupervisor.run` and the exception types
— both preserved.

## Test strategy

Behavioral contracts stay; only the LLM-injection mechanics change.

- **`tests/test_agent_workers.py`** — replace the custom `FakeLLM` (which implements
  `generate_structured`) with LangChain fakes
  (`langchain_core.language_models.fake_chat_models`: `GenericFakeChatModel` /
  `FakeListChatModel`) returning the queued structured payloads, OR inject a stub chain
  via the worker constructor. Assertions on repair behavior (mutation rejected then
  repaired, failure at cap, violations surfaced) are unchanged. Vector-worker tests
  unchanged.
- **`tests/test_agent_supervisor.py`** — `FakePlanner`/`FakeSqlWorker` injection into
  `AgentSupervisor` must still work (façade preserved). The sufficiency-cap test and the
  three endpoint tests (200 / 503 config / 503 provider) stay; verify the LangGraph loop
  still abstains at the cap and the exception translation still yields 503.
- **`tests/test_agent_catalog.py`, `tests/test_agent_eval_runner.py`** — expected
  unaffected; run to confirm.
- All agent tests must run **offline** (no network): fakes/stubs only, no real
  `ChatOpenRouter` calls. Conservative live verification afterwards (1–2 OpenRouter
  calls) per the cost-conscious constraint.

## Out of scope

LangGraph checkpointer / multi-turn memory; parallel speculative execution beyond the
planned set; `create_react_agent`/autonomous sub-agents; any change to validators,
executors, catalog content, trace schema, or the foundation ladder/vector code; the
evaluation spec semantics.

## Risks / gotchas (verify during implementation)

1. **`temperature` on Anthropic-via-OpenRouter** — the single biggest integration risk.
   Verify the actual request body (capture once) and suppress temperature/top_p before
   relying on it.
2. **`.with_structured_output` transport** — over OpenRouter+Anthropic it may use tool/
   function-calling or json mode; confirm it returns valid `ExecutionPlan`/
   `SufficiencyDecision` instances. Keep defensive validation (route coercion) regardless.
3. **Error translation** — map `openai`/`langchain` exceptions back to
   `LLMProviderError`/`LLMConfigurationError` so the 503 contract and tests hold.
4. **Reasoning effort** — pass `reasoning.effort` via `model_kwargs`/`extra_body`;
   verify OpenRouter forwards it for these models.
5. **Bug-fixes must survive** — keep route coercion (planner) and `_augment_sub_question`
   (dependent-task evidence passing) in the rewrite.

## Verification

1. `./.venv/Scripts/python.exe -m ruff check .` clean.
2. `./.venv/Scripts/python.exe -m pytest tests/test_agent_*.py` — all offline agent tests
   green (workers repair/cap, supervisor dispatch + cap + 503 endpoints, catalog, eval
   runner).
3. Static: `grep` confirms no remaining `httpx` use in `backend/agent/` and that
   `langgraph`/`langchain_openrouter` are imported in `graph.py`/`llm.py`.
4. Conservative live smoke (cost-aware, 1–2 calls): one isolated SQL worker question and
   one full `AgentSupervisor.run` via the CLI (`--emit-trace`), confirming the emitted
   `answer_trace` has the same shape/fields as before (route, generated_sql/cypher,
   worker_results, sufficiency_decisions, validation_results, provenance) and a known
   ladder-style question returns a consistent answer.
5. Re-run the broader `pytest` + `ruff` once more before declaring done.

## References

- `directives/phase-08-governed-query-generation.md`,
  `directives/phase-09-agentic-orchestrator.md`,
  `directives/phase-10-synthesis-and-evaluation.md`.
- CLAUDE.md invariants #5, #6, #7, #13; intended stack (LangGraph/LangChain).
- ADR 0002 (routing), 0003 (`answer_trace`), 0009 (guardrails), 0015 (orchestration),
  0016 (model params: no temperature), 0017 (answer contract), 0018 (behavioral eval).
