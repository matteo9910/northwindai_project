# Phase 10 — Evidence-First Synthesis & Agent Evaluation

> Realizes Issues 11, 12, 13. Binds ADR 0012 (plausible vs certain), 0017 (answer
> contract), 0018 (evaluation). Prerequisite: Phase 09 (Supervisor loop + trace).

The final phase makes the agent's answers **trustworthy** and **proven**: it
replaces Phase 09's deterministic assembler with governed evidence-first synthesis,
and stands up the evaluation that demonstrates the agent is generic — not tuned to
one query.

## Objective

1. Replace the assembly node with an **evidence-first synthesis** node that writes
   the user-facing answer strictly from the gathered evidence, with citations into
   the `answer_trace`, abstaining when evidence is insufficient.
2. Deliver the **evaluation suite**: a heterogeneous set of in-domain questions
   with behavioral specs, deterministic `answer_trace` assertions, and an
   LLM-as-judge for the prose. The Golden Query is **one case** in this suite.
3. Write the **milestone demo runbook**.

## Design decisions

1. **Evidence-first, strict (ADR 0017).** The synthesis model (Sonnet 4.6) receives
   only the question and the gathered evidence (graph rows, SQL rows, retrieved
   chunks) — no outside knowledge. Every claim must be attributable to a specific
   evidence element present in `answer_trace`. The hard reasoning already happened
   in Phase 09; synthesis writes faithfully.
2. **Certain vs plausible (ADR 0012).** The answer explicitly distinguishes facts
   (from SQL / explicit graph) from plausible relationships (derived links). Never
   present a plausible link as a proven cause.
3. **Abstention is an outcome, not a failure (ADR 0017).** When Phase 09 reaches
   the cap with insufficient evidence, synthesis produces an abstention answer that
   states what could not be determined. Same for the `needs_clarification` outcome
   (render the targeted question).
4. **Behavioral evaluation, never fixed-string (ADR 0018).** Specs assert
   *behavior*: expected route family, expected sources/tables used, facts that must
   appear (checked against a PostgreSQL/Neo4j read-back), required-abstention cases,
   and false-positive traps drawn from the Controlled Scenarios (ADR 0011).
5. **Deterministic where possible, LLM-judge only for prose.** Structural checks
   (route, valid generated queries, provenance present, evidence cited, abstention
   when required) run deterministically against the persisted trace. An
   LLM-as-judge grades the free-text synthesis against a rubric (grounded? abstains
   correctly? distinguishes plausible from certain?).

## Functional requirements

1. `backend/agent/synthesis.py` — evidence-first synthesis (Sonnet 4.6) wired in as
   the Supervisor's answer node, replacing the Phase 09 deterministic assembler;
   handles the answered / abstained / clarification cases.
2. `evaluation/agent/suite/*.spec.json` — a heterogeneous question set spanning the
   route families: at least one each of `sql_only`, `graph_only`, `vector_only`,
   `graph_plus_vector`, and the full `sql_plus_graph_plus_vector` **Golden Query**;
   plus an abstention case and a false-positive trap (Scenario B/C).
3. `evaluation/agent/runner.py` — runs each question through `POST /agent/query` (or
   the in-process Supervisor), persists the actual `answer_trace`, applies the
   deterministic assertions, and invokes the LLM-judge on the prose.
4. The Golden Query case proves the positive scenario (Tokyo Traders delay ↔ top
   customers ↔ contract terms) **and** the false-positive traps do not trigger.
5. `docs/RUNBOOK.md` — start services, seed/verify data, run the agent, inspect a
   trace, run the eval suite, demo the Golden Query; links to PRD/glossary/ADRs.

## Tests

- Synthesis is grounded: with fixed evidence, every claim maps to a trace element;
  an injected unsupported fact is not emitted (or triggers abstention).
- Abstention: a question with no supporting evidence yields an abstention answer,
  not a fabricated one.
- Certain-vs-plausible: an answer involving a derived link labels it as plausible,
  not causal.
- Eval runner: deterministic assertions pass for each spec; the LLM-judge returns a
  structured verdict; a deliberately broken trace fixture fails the right assertion
  (diagnoses routing vs generation vs traversal vs retrieval vs synthesis).
- Golden Query case: positive scenario answered with tri-store evidence; traps
  absent.
- LLM-dependent tests (synthesis, judge) skip cleanly when models are unconfigured;
  deterministic assertions run offline against persisted traces.
- `pytest` and `ruff check .` pass.

## Out of scope

- Multi-turn memory, local LLM serving (CLAUDE.md out-of-scope).
- Re-ranking / hybrid search / query expansion.
- A polished frontend (the runbook drives the CLI/API; the `answer_trace` is the
  inspection surface).
- Production auth/RLS hardening (Supabase RLS-disabled advisory tracked separately).

## References

- CLAUDE.md invariants #4 (plausible not causal), #6 (`answer_trace`),
  #10 (Controlled Scenarios), #13 (agentic).
- ADR 0003 (`answer_trace`), 0011 (controlled scenarios), 0012 (plausible vs
  certain), 0017 (answer contract), 0018 (evaluation).
- CONTEXT.md: `Abstention`, `Clarification`, `Plausible Relationship`,
  `Golden Query`, `Controlled Scenario`.
- ISSUES.md Issues 11, 12, 13.
