# Use LangChain and LangGraph for the agent runtime

AI Agent Query will use LangGraph `StateGraph` for the Supervisor's bounded
plan-execute-reflect loop and LangChain LCEL chains for all LLM-backed
structured calls. OpenRouter access uses the official `langchain-openrouter`
`ChatOpenRouter` integration, not a hand-written HTTP client and not
`ChatOpenAI` pointed at an OpenAI-compatible endpoint.

**Considered options**:
- *Hand-written loop plus raw OpenRouter HTTP*: worked for the PoC, but hid the
  intended framework learning goal and duplicated orchestration/transport code
  that LangGraph and LangChain already provide.
- *LangChain `create_agent` / ReAct loop*: rejected for the current milestone
  because AI Agent Query needs explicit, inspectable routing and bounded control
  flow. The Supervisor remains the only autonomous component and workers remain
  non-autonomous.
- *`ChatOpenAI` against OpenRouter*: rejected after checking the official
  integration docs. `ChatOpenRouter` exposes OpenRouter-specific features such
  as reasoning, provider routing, and structured output support more directly.

**Consequences**: The framework owns transport and control flow, but governance
does not move. Generated SQL and Cypher still pass code-level validators before
execution, vector retrieval remains graph-scoped, and every response still emits
the same `answer_trace` contract. The old `OpenRouterLLMClient` and bespoke JSON
parsing are removed. Offline tests use LangChain fake/stub models; live tests
remain cost-aware because each agent run may trigger multiple OpenRouter calls.
