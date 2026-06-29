# NorthwindAI Milestone Runbook

This runbook drives the first PoC milestone from a terminal: services, data
prep, governed AI Agent Query, trace inspection, and evaluation.

## 1. Configure

Create `.env` from `.env.example` and set:

- Supabase/PostgreSQL connection values.
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`.
- `QDRANT_URL` and optional `QDRANT_API_KEY`.
- `OPENROUTER_API_KEY` for live agent planning, query generation, sufficiency,
  synthesis, and optional eval judge.

Java 11+ must be on `PATH` for OpenDataLoader PDF parsing.

## 2. Start Services

```powershell
docker compose up -d neo4j qdrant
```

Supabase/PostgreSQL is external and must already contain the seeded mini-ERP
data.

## 3. Prepare Knowledge Stores

```powershell
python -m data_generation.contracts
python -m data_generation.contract_documents
python -m backend.graph.projection --reset
python -m backend.vector.indexer
```

This produces deterministic contract PDFs, writes supplier-contract document
paths to PostgreSQL, projects the ERP Domain Graph into Neo4j, and indexes
contract chunks into Qdrant with local BGE embeddings.

## 4. Verify Ladder Baselines

```powershell
python -m backend.ladder.top_customers --emit-trace
python -m backend.ladder.supplier_products --emit-trace
python -m backend.ladder.shipment_delays --emit-trace
python -m backend.ladder.contract_lead_times --emit-trace
```

These commands prove the deterministic governed paths that the agent reuses.

## 5. Run The Agent From Terminal

The live agent runtime uses a LangGraph `StateGraph` Supervisor and LangChain
`ChatOpenRouter` structured calls. A single question may use planner, worker,
sufficiency, and synthesis model calls, so run live smoke tests deliberately when
OpenRouter credit is limited.

One-shot:

```powershell
python -m backend.agent.cli -q "Who are the top customers by net revenue?" --emit-trace --json
```

Interactive:

```powershell
python -m backend.agent.cli --emit-trace
```

Useful demo questions:

- `Who are the top customers by net revenue?`
- `Which products are supplied by Tokyo Traders?`
- `Which Tokyo Traders orders had delivery-delay complaints?`
- `What does the Tokyo Traders contract say about delivery lead time?`
- `Which suppliers caused delivery-delay complaints for top customers, and what contract lead-time evidence supports supplier follow-up?`
- `Show packaging quality complaints and do not classify them as delivery delay complaints.`
- `What is the best stock to buy tomorrow?`

The last question should be refused as out of domain.

## 6. Run The API

```powershell
uvicorn backend.main:app --reload
```

Then:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/agent/query `
  -ContentType "application/json" `
  -Body '{"question":"What does the Tokyo Traders contract say about delivery lead time?"}'
```

## 7. Inspect Trace

CLI traces default to:

```text
evaluation/answer_traces/agent_last_trace.json
```

Inspect:

- `execution_plan`
- `worker_results`
- `sufficiency_decisions`
- `generated_sql`
- `generated_cypher`
- `validation_results`
- `retrieved_chunks`
- `documents_used`
- `citations`
- `provenance`

## 8. Run Evaluation

```powershell
python -m evaluation.agent.runner
```

Outputs:

- `evaluation/agent/answer_traces/*.json`
- `evaluation/agent/results.json`

The deterministic assertions check route, outcome, trace fields, allowed
validations, and false-positive traps. LLM-as-judge prose grading is optional and
skip-safe when `OPENROUTER_API_KEY` is unset.

## 9. Test And Lint

```powershell
pytest
ruff check .
```
