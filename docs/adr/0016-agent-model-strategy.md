# Model strategy for the agent roles

The agent uses Claude models via OpenRouter, picked per role: **Opus 4.8**
(`anthropic/claude-opus-4-8`) for the Supervisor (planning + sufficiency
reasoning) and for the Cypher worker (text-to-Cypher is the hardest,
most error-prone generation, so it gets the strongest model from the start);
**Sonnet 4.6** (`anthropic/claude-sonnet-4-6`) for the SQL worker and for
evidence-first synthesis. The vector worker needs no generation model: the
retrieval query is the user's question embedded locally, with filters supplied
by the graph step. Local LLMs are out of scope for now. The model per role is
configuration, not hard-coded.

**Considered options / notes**:
- *Sonnet everywhere for execution*: rejected for Cypher because putting the
  weakest model on the hardest generation maximizes failures. Sonnet is kept
  for SQL (well-represented, easier) and synthesis (writing from evidence, not
  hard reasoning).
- *All local (Ollama/HF)*: deferred because quality on text-to-Cypher and
  planning is the dominant success factor for a generic agent.
- *Determinism*: Opus 4.8 / Sonnet 4.6 reject `temperature`/`top_p`/`top_k`
  through the current OpenRouter path. Stability is controlled via prompting
  and `effort`, and evaluation stays behavioral, never fixed-string.

**Consequences**: LLM calls go through LangChain's official `ChatOpenRouter`
integration (ADR 0019), so role-specific model choice, reasoning effort,
provider routing, and structured outputs stay in one transport layer. Cost and
latency are tuned per role via model choice + `effort` + catalog discipline, not
by lowering correctness.
