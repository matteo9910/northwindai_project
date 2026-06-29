# NorthwindAI

NorthwindAI is a mini-ERP GraphRAG learning project. This repository now
contains the first PoC milestone: a governed AI Agent Query backend with a
progressive ladder, Neo4j event/contract projection, Qdrant contract retrieval,
and a LangGraph Supervisor that can generate governed SQL/Cypher, retrieve
contract chunks, synthesize evidence-first answers, and emit `answer_trace`.

## Prerequisites

- Python 3.11
- Docker Desktop with Docker Compose v2
- Git
- A Supabase project named `northwindai`
- Java 11+ on `PATH` for OpenDataLoader PDF parsing in Phase 07 contract
  indexing. On Windows, Temurin 21 JRE works; after installation, restart the
  shell or prepend its `bin` directory to `PATH`.
- `OPENROUTER_API_KEY` in `.env` for live AI Agent Query planning, query
  generation, sufficiency, synthesis, and optional eval judging.

## Supabase Setup

Create one Supabase project named `northwindai`. Use a single Supabase database;
later phases create the logical PostgreSQL schemas `erp_core` and `erp_docs`
inside that database.

From the Supabase dashboard, collect:

- database host, port, database name, user, and password
- project URL
- publishable/anon API key

Copy `.env.example` to `.env` if needed, then replace the placeholders in `.env`
with the real values. The `.env` file is ignored by Git and must not be
committed.

## Local Environment

Create and activate a virtual environment:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the project and development tools:

```powershell
pip install -e ".[dev]"
```

## Start Services

Start Neo4j and Qdrant:

```powershell
docker compose up -d
```

Neo4j browser is available at:

```text
http://localhost:7474
```

Qdrant REST API is available at:

```text
http://localhost:6333
```

Supabase/PostgreSQL is managed externally and is not started by Docker Compose.

## Run the API

Start the FastAPI backend:

```powershell
uvicorn backend.main:app --reload
```

Check service health:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

The endpoint returns `status: ok` only when PostgreSQL/Supabase, Neo4j, and
Qdrant are all reachable. If one service is unavailable, the response is
`status: degraded` and includes the failing service detail.

Ask the governed AI Agent Query endpoint:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/agent/query `
  -ContentType "application/json" `
  -Body '{"question":"Who are the top customers by net revenue?"}'
```

## Query Ladder

Run the SQL-only Top Customers ladder step:

```powershell
python -m backend.ladder.top_customers --emit-trace
```

Prepare the Neo4j graph projection before running the graph-only Supplier ->
Product, shipment-delay complaint, and contract ladder steps:

```powershell
docker compose up -d neo4j qdrant
python -m backend.graph.projection
python -m backend.ladder.supplier_products --emit-trace
python -m backend.ladder.shipment_delays --emit-trace
```

The projection command reads the current ladder scope from PostgreSQL and writes
`Supplier`, `Product`, `Customer`, `Order`, `Shipment`, `ShipmentDelayEvent`,
`CustomerComplaintEvent`, `Contract`, `ContractTermEvent`, and supplier-contract
`Document` reference graph elements into Neo4j with Graph Provenance.
Phase 06 also maps `erp_docs.customer_communications.subject` to normalized
complaint `issue_type` values and derives classified complaint issue Event Nodes:
`DeliveryDelayComplaintEvent`, `PackagingQualityComplaintEvent`, and
`ProductQualityComplaintEvent`. `DeliveryDelayComplaintEvent` is linked to
supporting `ShipmentDelayEvent` evidence when order/product context matches.
Phase 07 derives three `ContractTermEvent` nodes per supplier contract
(`lead_time`, `minimum_order_value`, `contract_validity`) and stores only
document references in Neo4j. Neo4j never stores full contract text or
embeddings.

Ladder Step 3 (`shipment_delays`) answers the narrowed question "Which Tokyo
Traders orders had shipment delays *with* a classified delivery-delay complaint?".
The traversal inner-joins the `DeliveryDelayComplaintEvent`, so it returns only
delayed orders that also carry a supported delivery-delay complaint, not every
delayed shipment.
Use `python -m backend.graph.projection --reset` only to clear the full
projected graph scope supported so far before re-projecting it.

Generate deterministic contract PDFs and prepare the document registry before
running the graph-plus-vector contract retrieval step:

```powershell
python -m data_generation.contracts
python -m data_generation.contract_documents
python -m backend.graph.projection
python -m backend.vector.indexer
python -m backend.ladder.contract_lead_times --emit-trace
```

`data_generation.contract_documents` is the only Phase 07 data-prep step that
updates PostgreSQL: it sets the four `erp_docs.documents.file_path` values for
supplier contracts. The runtime API does not mutate PostgreSQL. The vector
indexer loads the PDFs locally with OpenDataLoader, embeds chunks with the local
BGE default model `BAAI/bge-small-en-v1.5`, upserts them into Qdrant collection
`contract_chunks`, and updates Neo4j `Document.vector_chunk_ids`.

Ladder Step 4 (`contract_lead_times`) answers "What do Tokyo Traders contracts
say about delivery lead times?" through a `graph_plus_vector` route. Neo4j
resolves Tokyo Traders' contract, lead-time `ContractTermEvent`, and `Document`
scope; Qdrant retrieves the supporting contract chunks filtered by
`supplier_id` and `document_id`. The response is evidence-first and does not use
LLM synthesis.

## AI Agent Query

Run a one-shot question from the terminal:

```powershell
python -m backend.agent.cli -q "Who are the top customers by net revenue?" --emit-trace
```

Start interactive terminal mode:

```powershell
python -m backend.agent.cli --emit-trace
```

The agent uses a LangGraph `StateGraph` Supervisor plan-execute loop. LangChain
LCEL chains call OpenRouter through `ChatOpenRouter` with structured outputs.
The planner selects one of the route families (`sql_only`, `graph_only`,
`vector_only`, `graph_plus_sql`, `graph_plus_vector`,
`sql_plus_graph_plus_vector`), dispatches non-autonomous Specialized Workers,
runs a Sufficiency Check, and returns one of:
`answered`, `needs_clarification`, `abstained`, or `refused`.

Generated SQL and Cypher always pass the same validators used by the ladder
before execution. Vector retrieval is always scoped by graph-resolved metadata
filters. The trace includes the execution plan, worker results, sufficiency
decisions, generated queries, validations, retrieved chunks, documents, metrics,
citations, and provenance.

Run the agent evaluation suite:

```powershell
python -m evaluation.agent.runner
```

The suite persists traces under `evaluation/agent/answer_traces/` and writes a
summary to `evaluation/agent/results.json`. LLM-as-judge prose grading is
skip-safe when `OPENROUTER_API_KEY` is unset; deterministic trace assertions
remain available offline.

## Tests and Linting

Run smoke tests:

```powershell
pytest
```

Run linting:

```powershell
ruff check .
```

The health smoke tests monkeypatch the service checks, so they do not require
live Supabase, Neo4j, or Qdrant services.

## Milestone Runbook

For the end-to-end demo sequence, including data prep, graph projection, vector
indexing, terminal questions, trace inspection, and eval execution, use
[`docs/RUNBOOK.md`](docs/RUNBOOK.md).
