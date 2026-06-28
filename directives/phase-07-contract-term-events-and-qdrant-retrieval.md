# Phase 07 - ContractTermEvents & Graph-to-Qdrant Contract Retrieval / Query Ladder Step 4

> This phase bundles Issue 8 (structured ContractTermEvents, Neo4j-only) and
> Issue 9 (graph-to-Qdrant contract retrieval, ladder Step 4). It must align with
> the actual Supabase dataset analyzed before writing this directive: there are
> exactly 4 rows in `erp_docs.supplier_contracts` (suppliers 1, 3, 4, 7) and the
> 4 matching `erp_docs.documents` rows of `doc_type = 'supplier_contract'` have
> `file_path = NULL` and **no contract text**. The contract document content does
> not exist yet and must be generated as a deterministic Controlled Scenario
> artifact (ADR 0011) before the Qdrant retrieval step can be built.

---

## Objective

Deliver the fourth query ladder step end to end and stand up the contract side of
the Knowledge Layer plus the Neo4j-to-Qdrant bridge:

- **Part A (Issue 8, structured):** derive `Contract` nodes and structured
  `ContractTermEvent` nodes from `erp_docs.supplier_contracts` fields
  (`lead_time_days`, `start_date`, `end_date`, `minimum_order_value`, `status`),
  with `Supplier -> Contract -> ContractTermEvent` traversal. No documents, no
  Qdrant (ADR 0010).
- **Part B (Issue 9, retrieval):** generate clean digital PDF contracts, chunk
  and embed their text into Qdrant, store **references only** in Neo4j
  (ADR 0006), and answer ladder Step 4:

  ```text
  What do Tokyo Traders contracts say about delivery lead times?
  ```

  via a `graph_plus_vector` route: Neo4j finds the supplier/contract/document
  context, Qdrant retrieves the relevant contract chunks.

This is the first phase that introduces the Vector Store and the document
pipeline. Implement it as two explicit checkpoints:

1. **Phase 07A - Structured Contract Knowledge.** Prove the structured
   `Supplier -> Contract -> ContractTermEvent` path with Neo4j-only tests.
2. **Phase 07B - Contract Document Retrieval.** Only after 07A passes, add
   deterministic contract PDFs, Qdrant indexing, `Document` references, and
   ladder Step 4.

Do not merge the two checkpoints into one debugging surface. Prove the
structured contract path before, and independently from, the document/vector
path, in keeping with the progressive query ladder (ADR 0008).

---

## Ground Truth From Supabase

`erp_docs.supplier_contracts` (4 rows, one per controlled-scenario supplier):

```text
contract_id  supplier_id  company_name              lead_time_days  min_order_value  status
1            1            Exotic Liquids            12              500.00           active
2            3            Grandma Kelly's Homestead 30              1200.00          active
3            4            Tokyo Traders             14              900.00           active
4            7            Pavlova, Ltd.             10              750.00           active
```

All contracts: `start_date = 2020-01-01`, `end_date = NULL` (open-ended).

`erp_docs.documents` of `doc_type = 'supplier_contract'` (4 rows, document_id
1-4) already exist, each with `supplier_id` and
`metadata = {lead_time_days, contract_number}`, but **`file_path = NULL` and no
body/content column**. The `documents` table is a registry/pointer only.

Implication: Part B must (1) generate the actual contract document text, (2)
persist the generated files in the repository, and (3) set
`documents.file_path` for the 4 contract documents as a one-time data-prep step.

---

## Contract Document Generation (Controlled Scenario artifact)

Generate 4 clean digital PDF contracts deterministically, consistent with the
structured fields above, with graduated retrieval difficulty so the vector
retrieval is actually exercised (not a keyword lookup):

| Supplier | Lead time | Role | Retrieval difficulty | How the lead-time clause is written |
|---|---|---|---|---|
| Tokyo Traders (4) | 14 d | hero (Golden Query target) | medium | lead-time clause present but embedded in delivery-terms prose |
| Pavlova (7) | 10 d | fast contrast | easy | explicit, isolated "Delivery Lead Time" section |
| Grandma Kelly's (3) | 30 d | slow contrast | medium | term written in words ("within thirty business days") |
| Exotic Liquids (1) | 12 d | semantic trap | hard | no literal "lead time"; uses synonyms ("delivery window", "fulfilment period") with a seasonal exception |

Generation rules:

1. **Deterministic.** Fixed templates and fixed field values; regenerating
   produces byte-stable files (a content hash test should pass on re-run).
2. **Consistent with structured data.** Each PDF's stated lead time, minimum
   order value, validity and status must match its `supplier_contracts` row.
   Discrepancy detection between structured fields and text is **out of scope**
   for this milestone; keep them consistent.
3. **Clean digital PDFs only.** No scans, no OCR, no noise (ADR / spec: clean
   digital PDFs before OCR).
4. **Stored in a dedicated folder** committed to the repo:
   `data/contracts/CT-<supplier_id>-2020.pdf` (e.g., `CT-4-2020.pdf`).
5. **Realistic structure.** Sections such as Parties, Term & Validity, Delivery
   Lead Time, Minimum Order Value, Pricing, Termination — enough surrounding
   prose that chunking and semantic retrieval are meaningful.

After generation, set `erp_docs.documents.file_path` for document_id 1-4 to the
corresponding relative PDF path via a one-time data-prep migration (this is
seeding/data tooling, not application runtime; the app never mutates PostgreSQL).

---

## Design Decisions

1. **Two relationship families, again.** `Contract` and the
   `Supplier -> Contract` link are **explicit** (FK from
   `supplier_contracts.supplier_id`). `ContractTermEvent` nodes are **derived**
   knowledge (Neo4j-born, ADR 0004), one per structured term.

2. **ContractTermEvent granularity = one node per term type.** Derive these
   `term_type` values from the structured fields:
   - `lead_time` (carries `lead_time_days`)
   - `minimum_order_value` (carries `minimum_order_value`)
   - `contract_validity` (carries `start_date`, `end_date`, `status`)

   This yields 3 `ContractTermEvent` nodes per contract (12 total) and makes the
   lead-time question answerable by a single typed node. Business identity is
   `{contract_id, term_type}`; implementation identity should use a stable
   `term_key = "<contract_id>:<term_type>"` while preserving `contract_id` and
   `term_type` as explicit properties.

3. **Contract identity.** `Contract {contract_id}`, linked
   `(:Supplier)-[:HAS_CONTRACT]->(:Contract)` and
   `(:Contract)-[:HAS_TERM]->(:ContractTermEvent)`.

4. **Neo4j stores references, never embeddings or full text (ADR 0006).** Model
   a `Document` node:

   ```cypher
   (:Contract)-[:HAS_DOCUMENT]->(:Document {document_id, doc_type, file_path,
                                            vector_chunk_ids})
   ```

   `vector_chunk_ids` is the list of Qdrant point ids for that document's chunks.
   No chunk text, no embeddings on any Neo4j node.

5. **Qdrant is the only place with chunk text + embeddings (ADR 0006, 0007).**
   One collection (e.g., `contract_chunks`) with payload metadata:
   `supplier_id`, `contract_id`, `document_id`, `contract_number`, `chunk_index`,
   `source_path`, and the chunk `text`. Point ids are deterministic
   (e.g., `uuid5(document_id + ':' + chunk_index)`) so re-indexing is idempotent
   and Neo4j references stay stable.

6. **Local BGE embeddings for the PoC.** Use a local sentence-transformers BGE
   model, defaulting to `BAAI/bge-small-en-v1.5` (384 dims), not a paid API.
   Rationale: deterministic, local, no per-run API cost, and strong enough for
   clean supplier-contract retrieval. The model id is configurable; OpenRouter
   or another embedding provider can replace it later without changing the
   indexer/retriever contracts.

7. **Explicit route, asserted (no router yet).** Step 4 route is hard-set to
   `graph_plus_vector`. The LangGraph Query Router is Issue 10 / Phase 08.

8. **Code-level guardrails extend to the vector path (ADR 0009).** Cypher used
   for the graph half goes through `validate_cypher` as before. The Qdrant half is
   read-only by construction (search/scroll only, never upsert at query time) and
   must enforce: a collection allowlist, a `top_k` cap, and a required metadata
   filter so retrieval is always scoped. For Step 4, use the graph-resolved
   `supplier_id` and `document_id` filter. The retriever should keep the
   validation model general enough to support other metadata scopes later.
   Surface these as structured `VectorValidationResult` entries in the trace
   with `dialect = "vector"` alongside SQL/Cypher validation results.

9. **answer_trace carries the new evidence surfaces (ADR 0003).** Step 4 must
   populate `route`, `generated_cypher`, `graph_paths`, `retrieved_chunks`,
   `documents_used`, `metrics` (neo4j + qdrant), `validation_results`, and
   `provenance`.

10. **Step 4 is evidence-first and deterministic.** Do not introduce LLM
    synthesis in this phase. The answer should combine the structured
    `ContractTermEvent` lead-time value with retrieved Qdrant chunk evidence and
    keep the user-facing synthesis minimal and deterministic.

11. **No event tables in PostgreSQL.** `Contract`, `ContractTermEvent`, and
    `Document` graph elements are derived/projected into Neo4j only.

---

## Functional Requirements

### Part A - structured ContractTermEvents (Issue 8)

1. Project `Contract` nodes from `erp_docs.supplier_contracts`, with
   `(:Supplier)-[:HAS_CONTRACT]->(:Contract)` and Graph Provenance
   (`source_table = 'supplier_contracts'`, FK column `supplier_id`).

2. Derive `ContractTermEvent` nodes (one per `term_type` per contract) linked via
   `(:Contract)-[:HAS_TERM]->(:ContractTermEvent)`, each carrying its value,
   `derived_from = 'erp_docs.supplier_contracts'`, and provenance.

3. `Supplier -> Contract -> ContractTermEvent` traversal must return Tokyo
   Traders' lead-time term. Provide a governed graph-only read for this (a small
   step or test helper) using `validate_cypher` + `run_validated_cypher`.

4. `ContractTermEvent` nodes must not be materialized in PostgreSQL.

### Part B - Qdrant contract retrieval, ladder Step 4 (Issue 9)

5. Generate and commit the 4 clean PDF contracts in `data/contracts/` per the
   table above and set `documents.file_path` for the 4 contract documents.

6. Load each PDF locally with `langchain-opendataloader-pdf`, chunk the text,
   embed the chunks with the configured local BGE model, and upsert them into
   the Qdrant `contract_chunks` collection with the metadata payload from
   Design Decision 5.

7. Attach a `Document` node per contract in Neo4j with `vector_chunk_ids`
   referencing the Qdrant points (no text, no embeddings).

8. Implement ladder Step 4 (`graph_plus_vector`) answering "What do Tokyo Traders
   contracts say about delivery lead times?":
   - graph half: validated Cypher to find Tokyo Traders' contract + document
     context (`Supplier -> Contract -> Document`), returning provenance and the
     `supplier_id`/`document_id` scope;
   - vector half: scoped Qdrant semantic search for delivery-lead-time evidence
     over the graph-resolved `supplier_id` and `document_id`;
   - return a deterministic evidence-first answer containing the structured
     lead-time value and retrieved chunks, plus a full `answer_trace`.

9. Extend the Cypher validator allowlists with the new labels
   (`Contract`, `ContractTermEvent`, `Document`) and relationship types
   (`HAS_CONTRACT`, `HAS_TERM`, `HAS_DOCUMENT`).

10. Expose `GET /ladder/contract-lead-times` returning `{answer, answer_trace}`,
    and a CLI `--emit-trace` mirroring the other ladder steps.

11. Store the expected answer spec
    (`evaluation/ladder/step04_contract_lead_times.spec.json`) and persist the
    actual trace.

---

## Expected Graph Shape

Structured contract path (Part A):

```text
Supplier -HAS_CONTRACT-> Contract -HAS_TERM-> ContractTermEvent {term_type:'lead_time'}
                                  -HAS_TERM-> ContractTermEvent {term_type:'minimum_order_value'}
                                  -HAS_TERM-> ContractTermEvent {term_type:'contract_validity'}
```

Document reference path (Part B):

```text
Contract -HAS_DOCUMENT-> Document {document_id, file_path, vector_chunk_ids:[...]}
```

Qdrant (separate store, not in the graph):

```text
collection contract_chunks: {id, vector, payload:{supplier_id, contract_id,
  document_id, contract_number, chunk_index, source_path, text}}
```

Step 4 retrieval flow:

```text
graph: (Supplier {company_name:'Tokyo Traders'})-[:HAS_CONTRACT]->(Contract)-[:HAS_DOCUMENT]->(Document)
vector: qdrant.search("delivery lead times", filter={supplier_id:4, document_id:3}, top_k=k)
```

---

## File Structure

- `data/contracts/CT-1-2020.pdf` … `CT-7-2020.pdf` - generated clean PDFs.
- `data_generation/contracts.py` - deterministic PDF generator (templates +
  fixed values + difficulty tiers); a `__main__` to (re)generate all 4.
- migration/data-prep to set `documents.file_path` for document_id 1-4.
- Keep this data-prep separate from Qdrant indexing: PDF generation writes
  files, the data-prep step updates PostgreSQL document pointers, and the
  vector indexer reads those pointers instead of mutating PostgreSQL.
- `backend/vector/__init__.py`
- `backend/vector/connection.py` - Qdrant client from settings.
- `backend/vector/embeddings.py` - local BGE embedding model wrapper.
- `backend/vector/indexer.py` - load PDF, chunk, embed, upsert; idempotent.
- `backend/vector/retriever.py` - scoped, read-only, validated search.
- `backend/graph/projection.py` - add Contract / ContractTermEvent / Document
  projectors and derivers, wired into `project_all` and `reset_projection` in
  dependency order (Supplier exists -> Contract -> ContractTermEvent / Document).
- `backend/graph/cypher_validator.py` - allowlist additions.
- `backend/ladder/contract_lead_times.py` - Step 4 module.
- `backend/ladder/router.py` - `GET /ladder/contract-lead-times`.
- `backend/ladder/constants.py` - `CONTRACT_LEAD_TIMES_COMPANY = "Tokyo Traders"`.
- `backend/config.py` - add `qdrant_collection`, `embedding_model` (defaults).
- `evaluation/ladder/step04_contract_lead_times.spec.json` and the persisted
  `evaluation/answer_traces/step04_contract_lead_times.json`.
- `pyproject.toml` - add `sentence-transformers`,
  `langchain-opendataloader-pdf`, and `reportlab` if missing. `qdrant-client`
  already exists for health checks.

---

## Implementation Notes

- Reuse the projection patterns from Phase 05/06: `_fetch_rows`, batched
  `UNWIND ... MERGE`, `_run_batches`, uniqueness constraints, scoped reset.
- Add uniqueness constraints: `Contract.contract_id`, `Document.document_id`,
  and `ContractTermEvent.term_key`.
- Keep Qdrant indexing idempotent: deterministic point ids; upsert (not blind
  insert); the indexer must be safe to re-run.
- `project_contract_documents` may create `Document` nodes with
  `vector_chunk_ids = []`; after Qdrant upsert, the vector indexer is
  responsible for updating the Neo4j `Document.vector_chunk_ids` references.
- The indexer and PDF generator are build/data tooling (run via CLI), not part
  of the request path - mirror `python -m backend.graph.projection`.
- Unit tests should stub the embedding provider. Live indexing tests may use
  the configured local BGE model and should skip cleanly when the model,
  Qdrant, or contract PDFs are unavailable.
- Step 4 assembles the trace from two metric sources; key metrics as
  `{"neo4j": ..., "qdrant": ...}`.
- Preserve Graph Provenance on every new node/relationship; use descriptive
  `rule_name`s: `contract_projection`, `supplier_has_contract_projection`,
  `contract_lead_time_term`, `contract_minimum_order_value_term`,
  `contract_validity_term`, `contract_document_reference`.

---

## Tests

- ContractTermEvent derivation: 12 typed term events for the 4 contracts; Tokyo
  Traders' `lead_time` term has value 14; not materialized in PostgreSQL.
- `Supplier -> Contract -> ContractTermEvent` traversal returns Tokyo's
  lead-time term; provenance present; idempotent on re-projection.
- PDF generation is deterministic (stable content hash) and consistent with the
  structured `supplier_contracts` values.
- Qdrant indexing: 4 documents chunked and upserted; point ids deterministic;
  Neo4j `Document.vector_chunk_ids` match the indexed point ids; no chunk text or
  embeddings stored on any Neo4j node.
- Retrieval correctness: a delivery-lead-time query scoped to Tokyo Traders
  returns the lead-time chunk; the hard case (Exotic Liquids, synonyms only) is
  retrievable semantically without the literal phrase "lead time".
- Vector guardrails: collection allowlist enforced, `top_k` capped, required
  metadata filter enforced; Step 4 specifically filters by `supplier_id` and
  `document_id`; results returnable in `answer_trace.validation_results` through
  a typed `VectorValidationResult`.
- Step 4 `answer_trace`: route `graph_plus_vector`; `generated_cypher`,
  `graph_paths`, `retrieved_chunks`, `documents_used`, `metrics` (neo4j+qdrant),
  `validation_results`, `provenance` all populated.
- Step 4 answer is evidence-first and deterministic: no LLM synthesis; includes
  Tokyo Traders' structured lead-time term and the retrieved contract chunk
  evidence.
- Live tests skip cleanly when Supabase/Neo4j/Qdrant are unconfigured, mirroring
  Phase 05/06.
- `pytest` and `ruff check .` pass.

---

## Out of Scope

- OCR and noisy/scanned documents (clean digital PDFs only).
- Structured-vs-document discrepancy detection (keep them consistent here).
- Embedding `product_specifications` or `customer_communications` documents
  (contracts only this phase).
- LangGraph route classification (Issue 10 / Phase 08) - route is asserted.
- The full Golden Query orchestration (Issue 12).
- Re-ranking, hybrid BM25+vector search, multi-vector, or query expansion.
- Production auth/RLS hardening (note: Supabase reports RLS disabled on
  `erp_docs.*`; tracked separately, not addressed here).

---

## References

- CLAUDE.md invariants #1 (data/knowledge boundary), #2 (provenance), #3
  (explicit vs derived), #5 (code guardrails), #6 (answer_trace), #7 (routing;
  `graph_plus_vector`).
- ADR 0005 (provenance), 0006 (separate graph/vector storage), 0007 (Qdrant),
  0008 (progressive ladder), 0009 (code guardrails), 0010 (ContractTermEvents
  from structured source first), 0011 (controlled, deterministic synthetic data).
- CONTEXT.md: `ContractTermEvent`, `Knowledge Layer`, `Graph Provenance`,
  `GraphRAG`, `Explicit Graph Relationship`, `Derived Graph Relationship`.
- ISSUES.md Issues 8 and 9. PRD user stories 5, 8, 11, 16, 17, 18, 28, 38, 42,
  43, 44. Project_Idea.md ladder Step 4.
