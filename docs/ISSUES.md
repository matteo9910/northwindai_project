# NorthwindAI Implementation Issues

These issues break the PRD into independently grabbable tracer-bullet slices. They are written in dependency order and are ready to publish to an issue tracker once one is configured.

## Proposed Breakdown

1. **Title**: Bootstrap the NorthwindAI dev stack health check
   **Type**: AFK
   **Blocked by**: None
   **User stories covered**: 1, 3, 4, 5, 48

2. **Title**: Deliver the SQL-only Top Customers ladder step
   **Type**: AFK
   **Blocked by**: Issue 1
   **User stories covered**: 2, 3, 6, 7, 20, 26, 31, 35, 40

3. **Title**: Generate Controlled Scenarios for the Golden Query
   **Type**: AFK
   **Blocked by**: Issue 2
   **User stories covered**: 21, 22, 23, 24, 40, 41

4. **Title**: Deliver the Neo4j supplier-to-product traversal ladder step
   **Type**: AFK
   **Blocked by**: Issue 2
   **User stories covered**: 4, 12, 13, 14, 18, 27, 36

5. **Title**: Enforce read-only SQL and Cypher execution guardrails
   **Type**: AFK
   **Blocked by**: Issues 2, 4
   **User stories covered**: 30, 31, 32

6. **Title**: Deliver the shipment delay Event Node ladder step
   **Type**: AFK
   **Blocked by**: Issues 3, 4, 5
   **User stories covered**: 9, 12, 13, 14, 15, 16, 17, 18, 37

7. **Title**: Add CustomerComplaintEvent and plausible delay-to-complaint links
   **Type**: AFK
   **Blocked by**: Issue 6
   **User stories covered**: 10, 15, 16, 17, 18, 19, 24

8. **Title**: Deliver structured ContractTermEvents from supplier contracts
   **Type**: AFK
   **Blocked by**: Issues 3, 4, 5
   **User stories covered**: 8, 11, 16, 17, 18, 42, 43

9. **Title**: Deliver the graph-to-Qdrant contract retrieval ladder step
   **Type**: AFK
   **Blocked by**: Issue 8
   **User stories covered**: 5, 28, 38, 42, 44

10. **Title**: Implement the LangGraph Query Router across ladder routes
    **Type**: AFK
    **Blocked by**: Issues 2, 4, 6, 9
    **User stories covered**: 25, 26, 27, 28, 29

11. **Title**: Persist answer traces and evaluate ladder steps against specs
    **Type**: AFK
    **Blocked by**: Issue 10
    **User stories covered**: 33, 34, 40, 41

12. **Title**: Deliver the full Golden Query orchestration
    **Type**: AFK
    **Blocked by**: Issues 7, 9, 10, 11
    **User stories covered**: 20, 21, 22, 23, 24, 29, 33, 34, 39, 40, 41

13. **Title**: Prepare the first milestone demo runbook
    **Type**: AFK
    **Blocked by**: Issue 12
    **User stories covered**: 1, 39, 41, 46, 48

---

## Revised roadmap — governed agentic milestone (supersedes issues 10–13)

Issues 1–9 are **built and remain valid** — they are the data layers, the
projection, the Qdrant bridge, the code-level guardrails, the `answer_trace`, the
Controlled Scenarios, and the four deterministic ladder steps. After delivering
the ladder, the project scope was sharpened (ADR 0015–0018): the milestone target
is a **governed agentic assistant** that answers arbitrary *in-domain* questions,
not a hard-wired Golden Query pipeline. The ladder steps and the Golden Query are
repurposed as **execution primitives the agent reuses** and as **evaluation
baselines**.

Issues 10–13 are therefore realized by three phase directives (build in order):

| Phase | Directive | Realizes / supersedes | Theme |
|---|---|---|---|
| **08** | `directives/phase-08-governed-query-generation.md` | parts of 10 | Semantic Catalog + LLM client (OpenRouter, behind an abstraction) + text-to-SQL/Cypher **Specialized Workers** behind the existing validators, with bounded self-repair. The guardrails stop being dormant. |
| **09** | `directives/phase-09-agentic-orchestrator.md` | 10, 12 | **Supervisor** plan-execute loop: routing, dispatch to workers, hybrid **Sufficiency Check** under a hard cap, **clarification**/**abstention**. The vector worker (no generation model) plugs in here. |
| **10** | `directives/phase-10-synthesis-and-evaluation.md` | 11, 12, 13 | **Evidence-first synthesis** + the heterogeneous **evaluation suite** (behavioral specs + `answer_trace` assertions + LLM-as-judge on the prose). The Golden Query becomes one case in the suite; demo runbook. |

What does **not** change: every generated SQL/Cypher/vector request still passes
`validate_sql` / `validate_cypher` / `validate_vector_search` before execution, and
every answer still emits the same `answer_trace` shape. Routes and queries move
from hard-coded to LLM-generated; the governed execution path is reused verbatim.

The original issue bodies below are retained for traceability of the user-story
coverage; where they describe a fixed pipeline, the phase directives above are the
binding implementation guidance.

---

## Issue 1: Bootstrap the NorthwindAI dev stack health check

## What to build

Build the smallest runnable NorthwindAI development slice that proves the local project can start the core services and report their health. The slice should verify that the application can see PostgreSQL/Supabase configuration, Neo4j, and Qdrant, even if the business data model is not fully implemented yet.

This should create a thin end-to-end baseline for future issues: environment configuration, service startup, a simple backend health surface, and automated smoke checks.

## Acceptance criteria

- [ ] The local development stack can start the backend-facing services needed for the first milestone.
- [ ] Neo4j and Qdrant are available as development services.
- [ ] PostgreSQL/Supabase connection settings are represented in configuration without hardcoding secrets.
- [ ] A health check reports the availability of PostgreSQL/Supabase configuration, Neo4j, and Qdrant.
- [ ] A smoke test verifies the health check behavior.
- [ ] Setup instructions are documented well enough for a new agent to start the stack.

## Blocked by

None - can start immediately.

---

## Issue 2: Deliver the SQL-only Top Customers ladder step

## What to build

Deliver the first query ladder step end to end: answer "Who are the top 10 customers by revenue in the last year?" using PostgreSQL/Supabase as the Operational Source of Truth.

This slice should create the initial `erp_core` shape needed for customer, order, and order detail revenue calculation, then expose a governed SQL-only execution path that returns the top customers and records the expected answer spec for the ladder step.

## Acceptance criteria

- [ ] The database contains enough `erp_core` customer, order, and order detail data to calculate net revenue.
- [ ] Top Customers are calculated by net revenue over the selected analysis period.
- [ ] The SQL-only ladder question returns the top 10 customers with revenue values.
- [ ] The SQL used for the answer is read-only.
- [ ] The expected answer spec for this ladder step is stored.
- [ ] Tests verify revenue calculation and SQL-only behavior.

## Blocked by

- Issue 1

---

## Issue 3: Generate Controlled Scenarios for the Golden Query

## What to build

Generate deterministic Controlled Scenarios that make the Golden Query testable. The dataset should include positive cases, negative cases, and false-positive traps around suppliers, shipment delays, top customers, complaints, and contract terms.

This slice should make the dataset intentionally useful for GraphRAG evaluation rather than relying on random generation to accidentally produce interesting patterns.

## Acceptance criteria

- [ ] Synthetic data generation is deterministic from a fixed seed.
- [ ] The dataset includes a supplier delay scenario involving top customers.
- [ ] The dataset includes a supplier delay scenario involving non-top customers.
- [ ] The dataset includes complaints that are not related to shipment delays.
- [ ] The dataset includes contrasting supplier contract terms.
- [ ] A verification report or test proves the controlled scenarios exist.

## Blocked by

- Issue 2

---

## Issue 4: Deliver the Neo4j supplier-to-product traversal ladder step

## What to build

Deliver the second query ladder step end to end: answer "Which products does Tokyo Traders supply?" using Neo4j graph traversal.

This slice should project the required supplier and product instances from PostgreSQL into the ERP Domain Graph, create explicit relationships, attach Graph Provenance, and validate the supplier-to-product traversal.

## Acceptance criteria

- [ ] Supplier and product rows are projected into Neo4j as instance-level nodes.
- [ ] Supplier-to-product relationships are created from trusted ERP source relationships.
- [ ] Projected nodes and relationships include Graph Provenance.
- [ ] The graph-only ladder question returns the products supplied by Tokyo Traders.
- [ ] The expected answer spec for this ladder step is stored.
- [ ] Tests verify the projection and graph traversal.

## Blocked by

- Issue 2

---

## Issue 5: Enforce read-only SQL and Cypher execution guardrails

## What to build

Build the code-level query validation layer that sits between AI Agent Query and database execution. The validator must enforce read-only SQL and Cypher behavior independently from prompt instructions.

This slice should make both accepted and rejected query behavior observable through tests and through the execution path used by ladder steps.

## Acceptance criteria

- [ ] SQL validation allows read-only queries against allowed schemas and tables.
- [ ] SQL validation rejects mutation or schema-changing statements.
- [ ] Cypher validation allows read-only traversal queries against allowed labels and relationships.
- [ ] Cypher validation rejects graph mutation statements.
- [ ] Validation failures are returned in a structured way that can appear in `answer_trace`.
- [ ] Tests cover accepted and rejected SQL and Cypher examples.

## Blocked by

- Issue 2
- Issue 4

---

## Issue 6: Deliver the shipment delay Event Node ladder step

## What to build

Deliver the third query ladder step end to end: answer "Which Tokyo Traders orders had delays?" using Neo4j traversal through `ShipmentDelayEvent` nodes.

This slice should project the needed order and shipment data, derive `ShipmentDelayEvent` nodes in Neo4j only, attach Graph Provenance, and support the Supplier -> Product -> Order -> Shipment -> Event traversal.

## Acceptance criteria

- [ ] Order and shipment instances needed for the scenario are represented in Neo4j.
- [ ] `ShipmentDelayEvent` nodes are created in Neo4j from shipment facts.
- [ ] `ShipmentDelayEvent` nodes are not materialized in PostgreSQL.
- [ ] Event Nodes include provenance describing the rule and source facts used.
- [ ] The ladder question returns delayed Tokyo Traders orders with delay details.
- [ ] The expected answer spec for this ladder step is stored.
- [ ] Tests verify event creation and traversal.

## Blocked by

- Issue 3
- Issue 4
- Issue 5

---

## Issue 7: Add CustomerComplaintEvent and plausible delay-to-complaint links

## What to build

Extend the Knowledge Layer with `CustomerComplaintEvent` nodes and plausible relationships between shipment delays and complaints. The system should avoid claiming causality unless explicit evidence supports it.

This slice should make complaint evidence usable in later Golden Query orchestration while preserving the domain distinction between plausible relationship and proven cause.

## Acceptance criteria

- [ ] Customer complaint communications are represented as `CustomerComplaintEvent` nodes in Neo4j.
- [ ] Complaint events are linked to relevant customer, order, or product context when available.
- [ ] Shipment delay events can be linked to complaint events with plausible relationship semantics.
- [ ] Plausible relationship links include confidence, matching reason, time window, and evidence references.
- [ ] Tests cover both related and unrelated complaint scenarios.
- [ ] The graph does not use definitive causal relationship names for these links.

## Blocked by

- Issue 6

---

## Issue 8: Deliver structured ContractTermEvents from supplier contracts

## What to build

Create `ContractTermEvent` nodes from structured supplier contract data before introducing PDF contract parsing. This should allow the graph to answer contract-term questions using reliable structured fields such as lead time, start date, end date, minimum order value, and status.

This slice validates the contract side of the ERP Domain Graph independently from Qdrant.

## Acceptance criteria

- [ ] Supplier contract records exist for the controlled scenario suppliers.
- [ ] Structured contract fields are projected or derived into `ContractTermEvent` nodes in Neo4j.
- [ ] ContractTermEvents include provenance and source contract references.
- [ ] Supplier -> Contract -> ContractTermEvent traversal works for Tokyo Traders.
- [ ] Tests verify structured ContractTermEvent creation and traversal.

## Blocked by

- Issue 3
- Issue 4
- Issue 5

---

## Issue 9: Deliver the graph-to-Qdrant contract retrieval ladder step

## What to build

Deliver the fourth query ladder step end to end: answer "What do Tokyo Traders contracts say about delivery lead times?" by using Neo4j to find the relevant supplier/contract/document context and Qdrant to retrieve contract chunks.

This slice should use clean contract document content and prove the Neo4j-to-Qdrant bridge before introducing noisy documents or OCR.

## Acceptance criteria

- [ ] Clean supplier contract content exists for Tokyo Traders.
- [ ] Contract content is chunked and indexed in Qdrant with useful metadata.
- [ ] Neo4j stores references to relevant documents or chunk identifiers without storing embeddings.
- [ ] The graph-plus-vector ladder question retrieves contract lead-time evidence.
- [ ] Retrieved chunks are included in the response evidence.
- [ ] The expected answer spec for this ladder step is stored.
- [ ] Tests verify document retrieval by supplier/contract context.

## Blocked by

- Issue 8

---

## Issue 10: Implement the LangGraph Query Router across ladder routes

## What to build

Implement the LangGraph Query Router that classifies user questions and produces explicit execution plans. The router should choose SQL, graph traversal, vector search, or a hybrid plan based on the query ladder questions.

This slice makes tool selection inspectable before the full Golden Query is composed.

## Acceptance criteria

- [ ] The router supports `sql_only`, `graph_only`, `vector_only`, `graph_plus_sql`, `graph_plus_vector`, and `sql_plus_graph_plus_vector` route types.
- [ ] The router produces an explicit execution plan for each query ladder question.
- [ ] SQL-only ladder questions route to SQL execution.
- [ ] Simple graph ladder questions route to Neo4j execution.
- [ ] Contract retrieval questions route to graph-plus-vector execution.
- [ ] Router output can be included in `answer_trace`.
- [ ] Tests verify route selection for representative ladder questions.

## Blocked by

- Issue 2
- Issue 4
- Issue 6
- Issue 9

---

## Issue 11: Persist answer traces and evaluate ladder steps against specs

## What to build

Build the evaluation and traceability slice for the query ladder. Each ladder step should have an expected answer spec, produce an actual `answer_trace`, and support comparison between expected and actual behavior.

This slice makes debugging structured: failures should identify whether routing, query generation, graph traversal, retrieval, or synthesis diverged.

## Acceptance criteria

- [ ] Each implemented ladder step has an expected answer spec.
- [ ] Each non-trivial answer returns a structured `answer_trace`.
- [ ] Traces include route, generated SQL/Cypher, graph paths, retrieved chunks, documents used, metrics, validation results, and provenance when applicable.
- [ ] Evaluation compares expected route against actual route.
- [ ] Evaluation compares expected evidence usage against actual evidence usage.
- [ ] Evaluation output helps diagnose where a failed answer diverged.
- [ ] Tests cover trace shape and evaluation behavior.

## Blocked by

- Issue 10

---

## Issue 12: Deliver the full Golden Query orchestration

## What to build

Deliver the full Golden Query end to end:

```text
Which suppliers had shipment delays that seem related to complaints from top customers in the last quarter, and how do their contract terms compare?
```

The implementation should combine SQL for Top Customers, Neo4j for supplier-delay-complaint traversal, Qdrant for contract evidence, the LangGraph Query Router for planning, code-level guardrails for execution, and `answer_trace` for governance.

## Acceptance criteria

- [ ] SQL identifies Top Customers by net revenue for the selected analysis period.
- [ ] Neo4j identifies suppliers connected to shipment delays and plausibly related customer complaints.
- [ ] Qdrant retrieves contract evidence for the relevant suppliers.
- [ ] The answer compares supplier contract terms against operational delay patterns.
- [ ] The answer distinguishes certain facts from plausible relationships.
- [ ] The full response includes a structured `answer_trace`.
- [ ] The Golden Query is evaluated against its expected answer spec.
- [ ] Tests or evaluation fixtures prove the positive and false-positive scenarios.

## Blocked by

- Issue 7
- Issue 9
- Issue 10
- Issue 11

---

## Issue 13: Prepare the first milestone demo runbook

## What to build

Prepare the first milestone demo runbook that explains how to start the system, seed the data, run the query ladder, inspect answer traces, and demonstrate the Golden Query.

This slice should make the milestone reproducible for the project owner and for future agents.

## Acceptance criteria

- [ ] The runbook explains how to start required services.
- [ ] The runbook explains how to seed or verify the dataset.
- [ ] The runbook lists each query ladder question in order.
- [ ] The runbook explains what a successful answer and trace should show for each ladder step.
- [ ] The runbook explains how to run the Golden Query demo.
- [ ] The runbook links back to the PRD, glossary, and relevant ADRs.

## Blocked by

- Issue 12
