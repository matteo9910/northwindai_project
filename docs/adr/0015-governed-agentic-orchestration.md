# Governed agentic orchestration over the data sources

AI Agent Query is built as a governed agent that answers arbitrary **in-domain** questions (not only the Golden Query): given a natural-language question, a **Supervisor** plans an explicit set of per-store sub-tasks, dispatches each to a **Specialized Worker** (SQL, Cypher, or vector expert) grounded in a curated **Semantic Catalog**, runs a bounded **Sufficiency Check** that may trigger a targeted re-plan, and then synthesizes an evidence-first answer. The agent decides the route and generates the queries itself; the code — not the prompt — keeps it safe and traceable.

**Considered options**:
- *Router → fixed pipeline (single-shot)*: classify once and run a pre-wired pipeline. Rejected — cannot gather more when the first attempt is insufficient, and only ever serves pre-modelled questions.
- *ReAct (free reason–act loop)*: maximally flexible, but nested unbounded loops are hard to bound, govern, and trace; rejected as the control architecture.
- *Autonomous sub-agents per store*: each expert its own independent reasoning loop. Rejected — nested autonomy is a governance and tracing hazard. The experts are focused, non-autonomous workers; the Supervisor is the only decision-maker.
- *Raw live schema introspection / minimal static schema for grounding*: rejected as the primary grounding source — query generation (especially Cypher) needs descriptions, glossary, examples, and join paths, not bare column names. Live introspection is kept only as a later drift-check against the curated catalog.

**Consequences**: Every generated SQL/Cypher/vector request still passes its code-level validator before execution (ADR 0009), with a bounded generate→validate→repair loop per worker; nothing un-validated runs. The plan, the per-store queries, the retrieved evidence, the sufficiency decisions, and all validation results are recorded in `answer_trace` (ADR 0003), so the agent's autonomy stays inspectable. The deterministic ladder steps remain as evaluation baselines, and the Golden Query becomes a test of the generic agent rather than a hard-wired pipeline.
