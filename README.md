# NorthwindAI

NorthwindAI is a mini-ERP GraphRAG learning project. This repository currently
implements the Phase 01 development baseline: local service infrastructure,
typed configuration, a FastAPI backend, and a `/health` endpoint for
PostgreSQL/Supabase, Neo4j, and Qdrant reachability.

## Prerequisites

- Python 3.11
- Docker Desktop with Docker Compose v2
- Git
- A Supabase project named `northwindai`

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

## Phase 01 Scope

This phase does not create `erp_core` or `erp_docs` schemas, import Northwind
data, build the ERP Domain Graph, create Qdrant collections, add LangGraph, or
implement AI Agent Query behavior. Those arrive in later issue slices.

