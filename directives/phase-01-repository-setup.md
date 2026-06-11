# Phase 01 — Repository & Environment Setup

> Macro phase 1 of the NorthwindAI build. Establishes the project skeleton, the
> Python/AI dependency stack, local Dockerized infrastructure (Neo4j + Qdrant),
> the Supabase connection, and an end-to-end health check that proves every
> service is reachable. No business logic yet.

---

## Objective

Stand up a runnable NorthwindAI development baseline so that:

- the repository structure, dependency stack, and tooling are in place,
- Neo4j and Qdrant run locally via Docker Compose,
- the Supabase PostgreSQL project is reachable from configuration (no hardcoded secrets),
- a FastAPI `/health` endpoint reports the availability of **PostgreSQL/Supabase, Neo4j, and Qdrant**,
- a smoke test verifies that health behavior.

This is the thin end-to-end slice that every later phase builds on. It corresponds to **Issue 1** in `docs/ISSUES.md` (user stories 1, 3, 4, 5, 48).

**Query ladder:** no ladder step is delivered in this phase. Ladder Step 1 (SQL-only Top Customers) begins in Phase 04.

---

## Prerequisites

- **None** — this is the first phase and can start immediately (Issue 1 is `Blocked by: None`).
- A Supabase account exists. The project itself is created by hand in this phase (see [Manual setup steps](#manual-setup-steps-done-by-hand)).
- Local tooling expected on the machine: Python 3.11+, Docker Desktop (with Compose v2), Git, and the GitHub CLI or an SSH/HTTPS remote.

---

## Manual setup steps (done by hand)

These steps are performed by the project owner in the Supabase dashboard **before** the coding agent runs any database work. The agent does **not** create the project.

1. **Create one Supabase project** named:

   ```text
   northwindai
   ```

   - Region: choose the one closest to you (record it; it affects latency only).
   - Set and securely store the database password.
   - This single project hosts **both** logical schemas — `erp_core` and `erp_docs` — as PostgreSQL **schemas inside the same database** (per `Project_Idea.md` §3.2, `CLAUDE.md` invariant #1). Do **not** create a second project; the two-schema split is logical, not physical, so the SQL executor and the Golden Query can run cross-schema joins on a single connection.

2. **Collect the project connection details** from *Project Settings → Database* and *Project Settings → API*:
   - Connection string / host, port (`5432` direct or `6543` pooled), database name (`postgres`), user, password.
   - Project URL and the publishable/anon API key (kept for later phases; not required by the health check itself).

3. **Confirm the Supabase MCP server targets this project.** The MCP server is already configured in this environment. Once `northwindai` exists, the coding agent operates on it directly via MCP tools (`list_tables`, `apply_migration`, `execute_sql`) — this is how schema creation runs in Phase 02. No manual SQL is required in Phase 01; the agent only needs to *connect* and *read* for the health check.

> The schemas `erp_core` and `erp_docs` are created in **Phase 02**, not here. Phase 01 stops at "Supabase is reachable from config."

---

## Functional requirements

After this phase the system MUST:

1. Start Neo4j and Qdrant locally with a single `docker compose up -d`.
2. Load configuration (Supabase, Neo4j, Qdrant, LLM providers) from environment variables / `.env`, never from hardcoded literals.
3. Expose a FastAPI backend with a `GET /health` endpoint that returns the reachability status of each of the three data services independently.
4. Report a degraded-but-honest result: if one service is down, `/health` reports that service as `unavailable` and the others as `available` (it must not crash or hide failures).
5. Pass an automated smoke test that exercises `/health`.
6. Be startable by a new contributor following `README.md` alone.

---

## Technical requirements

### Language & runtime
- **Python 3.11+** (target 3.11; do not require 3.12-only features).
- Dependency management via `pyproject.toml` (preferred) **or** `requirements.txt`. Pick one and be consistent.

### Python dependencies (pin minor versions)

| Package | Version (indicative) | Purpose |
|---|---|---|
| `fastapi` | `>=0.111,<1.0` | Backend API + `/health` |
| `uvicorn[standard]` | `>=0.30` | ASGI server |
| `pydantic` | `>=2.7` | Config + response models |
| `pydantic-settings` | `>=2.3` | `.env` loading into a typed `Settings` object |
| `psycopg[binary]` | `>=3.1` | PostgreSQL/Supabase connectivity check |
| `neo4j` | `>=5.20` | Official Neo4j Python driver |
| `qdrant-client` | `>=1.9` | Qdrant connectivity check |
| `httpx` | `>=0.27` | Test client / outbound checks |
| `python-dotenv` | `>=1.0` | (optional) local `.env` convenience |
| `pytest` | `>=8.2` | Smoke test |
| `pytest-asyncio` | `>=0.23` | Async test support |
| `ruff` | `>=0.5` | Lint/format |

> LangChain / LangGraph / OpenRouter / Hugging Face / Ollama clients are **not** installed in this phase. They arrive in Phase 04+ (SQL executor) and Phase 08 (agent). Keep Phase 01 dependencies minimal so the baseline stays fast to install.

### Infrastructure (Docker Compose)
- **Neo4j Community** image: `neo4j:5-community`.
  - Ports: `7474` (HTTP browser), `7687` (Bolt).
  - Auth via `NEO4J_AUTH=neo4j/<password-from-env>`.
  - Named volumes for `data` and `logs`.
- **Qdrant** image: `qdrant/qdrant:latest` (pin a concrete tag in practice, e.g. `qdrant/qdrant:v1.9.2`).
  - Ports: `6333` (REST), `6334` (gRPC).
  - Named volume for `/qdrant/storage`.
- Supabase/PostgreSQL is **not** containerized — it is the managed `northwindai` project. Compose covers only Neo4j and Qdrant.

### Configuration contract (`.env`)
`.env` is git-ignored; `.env.example` is committed with placeholder values:

```dotenv
# --- Supabase / PostgreSQL (project: northwindai) ---
SUPABASE_DB_HOST=db.<project-ref>.supabase.co
SUPABASE_DB_PORT=5432
SUPABASE_DB_NAME=postgres
SUPABASE_DB_USER=postgres
SUPABASE_DB_PASSWORD=__set_me__
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_ANON_KEY=__set_me__

# --- Neo4j (local Docker) ---
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=__set_me__

# --- Qdrant (local Docker) ---
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

# --- LLM providers (placeholders; consumed in later phases) ---
OPENROUTER_API_KEY=
HUGGINGFACE_API_TOKEN=
OLLAMA_BASE_URL=http://localhost:11434
```

A typed `Settings` (pydantic-settings) class loads these. Missing required values fail fast with a clear error.

---

## File structure

Create the following (folders for later phases are scaffolded as empty packages with a short `__init__.py` or `.gitkeep` so the layout is visible from day one):

```text
test-project/
├─ .env.example                # committed, placeholders only
├─ .env                        # git-ignored, real values (NOT committed)
├─ .gitignore                  # ignores .env, __pycache__, .venv, etc.
├─ docker-compose.yml          # Neo4j + Qdrant
├─ pyproject.toml              # deps + ruff/pytest config (or requirements.txt)
├─ README.md                   # setup + run instructions (see acceptance)
├─ backend/
│  ├─ __init__.py
│  ├─ main.py                  # FastAPI app, mounts /health
│  ├─ config.py                # pydantic-settings Settings
│  └─ health/
│     ├─ __init__.py
│     ├─ router.py             # GET /health
│     └─ checks.py             # check_postgres(), check_neo4j(), check_qdrant()
├─ data_generation/            # Phase 03 (scaffold only)
│  └─ .gitkeep
├─ graph/                      # Phase 05/06 (scaffold only)
│  └─ .gitkeep
├─ agent/                      # Phase 04/08 (scaffold only)
│  └─ .gitkeep
├─ eval/                       # Phase 09 (scaffold only)
│  └─ .gitkeep
└─ tests/
   ├─ __init__.py
   └─ test_health.py           # smoke test for /health
```

> `docs/`, `CLAUDE.md`, `CONTEXT.md`, `Project_Idea.md`, and `directives/` already exist — do not recreate or overwrite them.

---

## Implementation guidance

### `docker-compose.yml` (shape)

```yaml
services:
  neo4j:
    image: neo4j:5-community
    container_name: northwindai-neo4j
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      - NEO4J_AUTH=neo4j/${NEO4J_PASSWORD}
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs

  qdrant:
    image: qdrant/qdrant:v1.9.2
    container_name: northwindai-qdrant
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_storage:/qdrant/storage

volumes:
  neo4j_data:
  neo4j_logs:
  qdrant_storage:
```

### `/health` response contract

```json
{
  "status": "ok",
  "services": {
    "postgres": { "available": true,  "detail": "northwindai reachable" },
    "neo4j":    { "available": true,  "detail": "bolt ok" },
    "qdrant":   { "available": true,  "detail": "6333 ok" }
  }
}
```

- Top-level `status` is `"ok"` only when all three are `available`; otherwise `"degraded"`.
- Each check has a short timeout (e.g. 2–3s) and catches its own exceptions so one failure never masks the others.
- The Postgres check is a lightweight `SELECT 1` over the Supabase connection (it does **not** assume any schema/table exists yet).
- The Neo4j check runs `RETURN 1` over Bolt; the Qdrant check calls the client's healthz/collections endpoint.

### Smoke test (`tests/test_health.py`)
- Use FastAPI `TestClient`/`httpx` against the app.
- Assert `/health` returns HTTP 200 and a body containing all three service keys.
- The check functions must be structured so they can be **monkeypatched/stubbed**, so the smoke test passes deterministically in CI without live Neo4j/Qdrant/Supabase. (A separate, optionally-skipped integration test may hit the real services when `docker compose up` is running.)

---

## Acceptance criteria

This phase is complete when **all** of the following are verifiable:

- [ ] `git init` done, GitHub remote linked, and an initial commit exists. `.gitignore` excludes `.env`, `.venv/`, `__pycache__/`.
- [ ] The Supabase project **`northwindai`** exists (created by hand) and its connection details are present in `.env` (and `.env.example` carries placeholders only).
- [ ] `docker compose up -d` starts `northwindai-neo4j` and `northwindai-qdrant`; both report healthy/running. Neo4j browser is reachable at `http://localhost:7474`, Qdrant at `http://localhost:6333`.
- [ ] Dependencies install cleanly from a fresh virtualenv via the documented command (e.g. `pip install -e .` or `pip install -r requirements.txt`).
- [ ] `uvicorn backend.main:app --reload` starts the API with no errors.
- [ ] `GET /health` returns the three-service contract above. With all services up, `status == "ok"`; with one stopped, that service shows `available: false` and `status == "degraded"` (verify by stopping one container).
- [ ] `pytest` passes, including `tests/test_health.py`.
- [ ] `ruff check .` passes (or documented lint command).
- [ ] No secret values are committed; only `.env.example` placeholders.
- [ ] `README.md` documents, end to end: prerequisites, creating the `northwindai` Supabase project, filling `.env`, `docker compose up -d`, installing deps, running the API, and running tests — sufficient for a new agent to reproduce the stack.

---

## Out of scope (do NOT do in this phase)

- Creating the `erp_core` / `erp_docs` schemas or any tables — that is **Phase 02** (via Supabase MCP `apply_migration`).
- Importing Northwind data or generating synthetic data — **Phase 02 / Phase 03**.
- Any Neo4j graph projection, node/relationship creation, or Cypher — **Phase 05+**.
- Any Qdrant collection creation, embeddings, or chunking — **Phase 07**.
- Installing or wiring LangChain, LangGraph, OpenRouter, Hugging Face, or Ollama clients — **Phase 04 / Phase 08**.
- Query validators / guardrails (`query_validator.py`) — **Phase 04 (SQL)** and **Phase 05 (Cypher)**.
- `answer_trace`, the Query Router, or any ladder query logic — **Phase 04+**.
- Frontend (Database Explorer, Agent Chat, Document Processing pages) — **Phase 11**.
- Authentication, authorization, deployment hardening — out of scope for Milestone 1 entirely.

---

## References

- `docs/ISSUES.md` → Issue 1 (acceptance criteria mirrored above).
- `Project_Idea.md` §2 (architecture), §3.2 (schema split), §11 (stack), §13 Phase 1 (roadmap).
- `CLAUDE.md` → Architecture invariant #1 (three-layer storage, schema split).
- `docs/PRD.md` → user stories 1, 3, 4, 5, 6, 48.
