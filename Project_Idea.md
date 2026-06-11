# NorthwindAI - ERP Intelligence Suite
## Project specification document

> **Purpose of this document**: describe the idea, domain, architecture, and roadmap for NorthwindAI. This document incorporates the decisions made during the brainstorming session and serves as the foundation for the next planning and implementation phases.

---

## 1. Vision and project goal

NorthwindAI is a personal portfolio side project that simulates a mini-ERP enriched with AI features inspired by the pillars developed by Formula AI Tech for enterprise management software.

The project is designed as intensive preparation for the AI/ML Engineer role at Formula SpA, starting in July 2026. The goal is not to build a generic AI demo, but to create a realistic technical environment for studying and implementing patterns that are relevant in enterprise work: GraphRAG over ERP data, document processing, agent orchestration, query governance, evaluation, and traceability.

The project has three AI pillars:

1. **AI Agent Query**: an agentic assistant orchestrated with LangGraph, able to query structured ERP data, the domain graph, and unstructured documents.
2. **AI Document Processing**: a pipeline that processes PDF documents, extracts relevant information, indexes it in a vector database, and connects it to the ERP domain.
3. **AI Predictive Engine**: forecasting and anomaly detection models over ERP data, to be developed after the first two features.

The initial priority is **AI Agent Query**, with a milestone centered on real, demonstrable GraphRAG. AI Document Processing will initially be introduced in a controlled way, mainly to support contracts and documents that are useful for GraphRAG. Predictive Engine remains a later phase.

---

## 2. Architectural principles

NorthwindAI explicitly separates three layers:

```text
PostgreSQL / Supabase = Operational Source of Truth
Neo4j = Knowledge Layer
Qdrant = Vector Store
```

**PostgreSQL / Supabase** stores the raw operational facts of the mini-ERP: orders, customers, products, suppliers, shipments, invoices, amounts, dates, statuses, and quantities. Data is born here.

**Neo4j** stores the ERP Domain Graph: instance-level business entities, business relationships, and derived knowledge. Event Nodes live only in Neo4j and are not materialized in PostgreSQL.

**Qdrant** stores text chunks, embeddings, metadata, and semantic similarity indexes. Neo4j may contain references to documents or chunks, but it must not become the embedding database.

**LangGraph** orchestrates the agent through an explicit Query Router, which decides whether a question requires SQL, Cypher, vector search, or a combination.

Every non-trivial answer must include a structured `answer_trace` with the selected route, generated SQL/Cypher queries, traversed graph paths, retrieved chunks, documents used, and relevant metrics.

---

## 3. Mini-ERP data structure

### 3.1 Starting point

The project starts from the complete PostgreSQL version of the Northwind database:

https://github.com/pthom/northwind_psql

Northwind provides the initial ERP skeleton: customers, orders, order details, products, suppliers, employees, shippers, categories, and territories.

The original data is too small and temporally limited for the goals of this project, so it will be extended with deterministic synthetic data and controlled scenarios.

### 3.2 Logical separation into PostgreSQL schemas

To simulate a multi-system reality without exploding the scope, the PostgreSQL database will be split into two logical schemas:

```text
erp_core
erp_docs
```

**erp_core** contains transactional and operational data:

- `customers`
- `orders`
- `order_details`
- `products`
- `suppliers`
- `employees`
- `shippers`
- `categories`
- `territories`
- `invoices`
- `shipments`
- `warehouses`
- `inventory_movements`
- `price_history`

**erp_docs** contains document data, communications, and semi-structured content:

- `documents`
- `document_entities`
- `customer_communications`
- `supplier_contracts`
- `product_specifications`

This separation forces the agent to reason about routing: some questions are SQL-only over `erp_core`, others require document content from `erp_docs`, and others require composition across PostgreSQL, Neo4j, and Qdrant.

### 3.3 Main custom tables

**invoices**: invoices generated from orders. Stores invoice number, dates, due date, payment date, amounts, taxes, status, and payment method.

**shipments**: shipments connected to orders. Stores expected dates, actual dates, delivery date, delay, carrier, and status. This table is central for generating `ShipmentDelayEvent` nodes in Neo4j.

**warehouses**: warehouse master data with capacity, location, and type.

**inventory_movements**: inbound, outbound, return, and adjustment movements. Used to model stock, replenishment, and `StockOutEvent`.

**price_history**: product price change history.

**documents**: registry of processed or generated documents, with references to order, supplier, customer, file, status, and metadata.

**document_entities**: bridge table between documents and extracted or mentioned entities. Helps connect document content, Qdrant, and the graph.

**customer_communications**: customer communications. It must be optionally linkable to customer, order, product, and contact reason. Complaints generate `CustomerComplaintEvent` nodes.

**supplier_contracts**: structured supplier contract data, including `leadTimeDays`, dates, status, and minimum order value. In the first milestone, this table generates `ContractTermEvent` nodes from structured source data.

**product_specifications**: product technical sheets and descriptive content.

---

## 4. ERP Domain Graph

The graph is not an ERD and does not represent only tables. The graph is instance-level: each node represents a specific business entity or operational event.

Examples:

```text
Customer:ALFKI
Order:11077
Product:42
Supplier:7
Shipment:3001
Document:88
Contract:15
ShipmentDelayEvent:9001
CustomerComplaintEvent:923
```

Tables define node types; rows become concrete nodes.

Example relationships:

```text
Customer PLACED Order
Order CONTAINS Product
Product SUPPLIED_BY Supplier
Order HAS_SHIPMENT Shipment
Shipment HAS_EVENT ShipmentDelayEvent
CustomerComplaintEvent REFERS_TO Order
Supplier HAS_CONTRACT Contract
Contract HAS_TERM ContractTermEvent
Document MENTIONS Supplier
Document SUPPORTS ContractTermEvent
```

### 4.1 Explicit and derived relationships

The graph contains two families of relationships:

**Explicit relationships**: derived directly from foreign keys or reliable operational links in the database.

**Derived relationships**: produced by controlled pipelines, business rules, or document processing. They must not be raw LLM guesses.

Every node and relationship must include minimal provenance metadata:

```text
source_system
source_schema
source_table
source_pk
projection_version
rule_name
rule_version
confidence
derived_from
```

Not every field is mandatory for every node, but every graph element must be traceable.

### 4.2 Initial Event Nodes

Event Nodes represent operational occurrences or business facts in time. They live only in Neo4j and are generated by the Knowledge Layer from raw facts in PostgreSQL or from document evidence.

First-phase Event Nodes:

- `ShipmentDelayEvent`: a shipment delivered after the expected or required date.
- `CustomerComplaintEvent`: a customer complaint captured from structured communications or document processing.
- `StockOutEvent`: a product or warehouse reaching zero stock or a critical shortage threshold.
- `InvoiceOverdueEvent`: an unpaid invoice past its due date.
- `ContractTermEvent`: a relevant contract term, initially derived from `supplier_contracts`.

In the first phase, we use explicit Event Nodes and avoid shortcuts. We avoid synthetic edges such as:

```text
Supplier LINKED_TO_DELAY_COMPLAINT Customer
```

We prefer readable, traceable paths:

```text
Supplier -> Product -> Order -> Shipment -> ShipmentDelayEvent -> CustomerComplaintEvent
```

### 4.3 Plausible relationships, not strong causality

Relationships between events, such as a shipment delay and a complaint, must not claim causality unless the evidence supports it.

Preferred relationship:

```text
ShipmentDelayEvent POSSIBLY_RELATED_TO CustomerComplaintEvent
```

with properties:

```text
matching_reason
time_window_days
confidence
evidence
```

This lets the agent explain correlations without overstating certainty.

---

## 5. AI Agent Query

### 5.1 Goal

AI Agent Query is the main feature of the first phase. The goal is to build an agentic assistant that answers business questions about the mini-ERP using SQL, Neo4j, and Qdrant in a governed and traceable way.

The system must not use GraphRAG for everything. Point and aggregate questions remain SQL-first. GraphRAG is valuable when a question requires multi-hop traversal, temporal relationships, events, documents, and derived knowledge.

SQL-only example:

```text
How many orders did we receive in Q3 2024?
```

GraphRAG example:

```text
Which suppliers had shipment delays that seem related to complaints from top customers in the last quarter, and how do their contract terms compare?
```

### 5.2 LangGraph Query Router

The first important node in the agent is a LangGraph `Query Router`. The router classifies the question and produces an explicit plan.

Expected routes:

- `sql_only`
- `graph_only`
- `vector_only`
- `graph_plus_sql`
- `graph_plus_vector`
- `sql_plus_graph_plus_vector`

The router output must be included in the `answer_trace`.

### 5.3 SQL and Cypher guardrails

The agent may generate SQL and Cypher, but execution must always pass through a code-level validation layer, such as `query_validator.py`.

Prompts can guide the model, but they are not an enforcement mechanism.

SQL guardrails:

- only `SELECT`
- allowlist for `erp_core` and `erp_docs`
- allowlist for queryable tables
- block `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`
- row limits when appropriate
- optional dry-run or explain before execution

Cypher guardrails:

- read-only queries only
- block `CREATE`, `MERGE`, `DELETE`, `SET`, `REMOVE`
- allowlist for labels and relationships
- limits on path length and traversal depth
- timeout for potentially large traversals

### 5.4 Answer trace

Every non-trivial answer must include a structured `answer_trace`.

Example contents:

```text
route
generated_sql
generated_cypher
graph_paths
retrieved_chunks
documents_used
metrics
validation_results
provenance
```

The trace is essential for debugging, evaluation, governance, and enterprise explainability.

---

## 6. Query ladder and Golden Query

The Golden Query must not be the first test. The project should reach it through a progressive query ladder where each step validates one layer.

### Step 1 - SQL only

```text
Who are the top 10 customers by revenue in the last year?
```

Goal: validate text-to-SQL, PostgreSQL connectivity, revenue calculation, and SQL guardrails.

### Step 2 - Graph only, simple traversal

```text
Which products does Tokyo Traders supply?
```

Goal: validate PostgreSQL -> Neo4j sync and a simple Cypher query.

### Step 3 - Graph with Event Nodes

```text
Which Tokyo Traders orders had delays?
```

Goal: validate `ShipmentDelayEvent` and the Supplier -> Product -> Order -> Shipment -> Event traversal.

### Step 4 - Graph + Vector

```text
What do Tokyo Traders contracts say about delivery lead times?
```

Goal: Neo4j identifies the supplier/contract/document; Qdrant retrieves relevant chunks.

### Step 5 - Full Golden Query

```text
Which suppliers had shipment delays that seem related to complaints from top customers in the last quarter, and how do their contract terms compare?
```

Goal: combine SQL for top customers, Neo4j for multi-hop traversal, Qdrant for contracts and documents, the LangGraph router, and the `answer_trace`.

For every step, store:

- expected answer spec
- expected route
- actual route
- generated SQL/Cypher
- traversed graph path
- retrieved chunks
- final answer
- divergences and diagnosis

---

## 7. Synthetic data generation

Data generation must have two components:

1. **Statistical realism**: plausible distributions, trends, seasonality, noise, and coherent volumes.
2. **Controlled Scenario**: intentional patterns for testing reasoning, false positives, and the Golden Query.

### 7.1 Statistical realism

The original Northwind data will be expanded over the January 2020 - December 2025 horizon.

Indicative targets:

- 2,500-3,000 orders/year
- 15,000-18,000 total orders
- seasonality by product category
- Pareto-like customer distribution
- product popularity derived from the original data
- price and demand trends

Expected libraries:

- Faker
- numpy
- scipy
- pandas

Generation must be deterministic through a fixed seed.

### 7.2 Controlled Scenario

Controlled scenarios make the Golden Query testable.

Examples:

**Scenario A**: Tokyo Traders supplies products ordered by top customers. In the last three months, several orders are delayed. Some complaints mention delays or missed deliveries. The contract defines a 14-day lead time, but the actual average performance is 22 days.

**Scenario B**: Exotic Liquids has similar delays, but toward non-top customers. This tests the top customer filter.

**Scenario C**: Pavlova Ltd has top customers and complaints, but the complaints are not related to delays. This tests false positives.

**Scenario D**: Grandma Kelly's Homestead has worse contract terms but fewer complaints. This supports qualitative comparison.

---

## 8. AI Document Processing

### 8.1 Goal

AI Document Processing must process unstructured documents, extract relevant content, index it in Qdrant, and connect it to the ERP domain through PostgreSQL and Neo4j.

In the first milestone, document processing remains intentionally controlled. The priority is to support GraphRAG, not to solve OCR and noisy documents immediately.

### 8.2 First phase: supplier contracts

The first end-to-end document type will be the supplier contract, not the invoice.

Reason: contracts directly support the query ladder and the Golden Query, especially for questions about lead time and delivery terms.

Initial phase:

```text
supplier_contracts structured fields
-> ContractTermEvent in Neo4j
-> working traversal
```

Next phase:

```text
clean contract PDF
-> parsing
-> chunks in Qdrant
-> evidence connected to ContractTermEvent
```

Advanced phase:

```text
structured vs PDF comparison
-> consistency / discrepancy / confidence
```

### 8.3 Progressive document difficulty

Version 1:

- clean digital PDFs
- selectable text
- stable layout
- contracts consistent with `supplier_contracts`

Version 2:

- different templates
- borderless tables
- variable terminology
- longer contracts

Version 3:

- simulated scans
- OCR
- noise
- watermarks
- intentional discrepancies

### 8.4 Document stack

Expected parser:

- OpenDataLoader PDF
- LangChain integration through `langchain-opendataloader-pdf`

Expected output:

- structured Markdown
- JSON with blocks, tables, metadata, and bounding boxes when available
- text chunks indexed in Qdrant
- chunk references connected through Neo4j

---

## 9. Vector store with Qdrant

Qdrant is the official vector database for the project.

Responsibilities:

- chunk text
- embeddings
- metadata filtering
- semantic retrieval
- document/chunk lookup

Neo4j does not store embeddings and does not store full chunks. It stores references to documents or chunks when they are useful for navigation and traceability.

Example:

```text
Supplier -> Contract -> ContractTermEvent -> Document
Document / ContractTermEvent -> vector_chunk_ids
Qdrant -> chunk text + embedding + metadata
```

---

## 10. Evaluation

Evaluation does not compare only the final answer. Every query in the ladder must have an `expected answer spec`.

Example for Step 3:

```text
Query:
Which Tokyo Traders orders had delays?

Expected answer spec:
- identifies Tokyo Traders as a Supplier
- traverses Supplier -> Product -> Order -> ShipmentDelayEvent
- returns order_id, delay_days, expected_date, delivered_date
- includes at least one graph_path in the answer_trace
- does not use vector search
```

For the Golden Query:

```text
- uses SQL to calculate top customers
- uses Neo4j to find related delays and complaints
- uses Qdrant to retrieve contract terms
- cites documents/chunks used
- distinguishes certain facts from plausible relationships
- includes complete answer_trace
```

This enables structured debugging: if an answer is wrong, we can understand whether the problem is routing, query generation, graph traversal, retrieval, or synthesis.

---

## 11. Technology stack

### 11.1 Database and storage

- Supabase PostgreSQL for `erp_core` and `erp_docs`
- Neo4j Community in Docker for the ERP Domain Graph
- Qdrant in Docker for vector storage

### 11.2 Backend and AI

- Python 3.11+
- FastAPI
- LangChain
- LangGraph
- OpenRouter for cost-effective cloud LLMs
- Hugging Face / Ollama for local LLMs
- OpenDataLoader PDF for document processing
- scikit-learn / statsforecast / Prophet for the future Predictive Engine

### 11.3 Frontend

React or Next.js frontend with a desktop-oriented interface.

Expected pages:

- Database Explorer
- AI Agent Chat
- Document Processing

The chat UI must show not only the answer, but also an inspectable `answer_trace` view.

### 11.4 Mapping with the Formula stack

| Formula requirement | Technology in this project |
|---|---|
| Python | Python 3.11+ |
| LangChain | LangChain + LangGraph |
| RAG / GraphRAG | Neo4j + Qdrant + LangGraph |
| Vector database | Qdrant |
| REST API | FastAPI |
| Open-source LLMs | Hugging Face / Ollama |
| Document processing | OpenDataLoader PDF |
| Docker | Docker Compose |
| LLM system evaluation | Query ladder + expected answer spec + answer_trace |
| Governance | query validator + graph provenance + traceability |

---

## 12. First milestone

The first implementation milestone reaches the complete query ladder and the Golden Query.

Included:

- Supabase/PostgreSQL with `erp_core` and `erp_docs`
- extended Northwind schema
- `shipments` table
- `customer_communications` linkable to orders/products
- `supplier_contracts` with `leadTimeDays`
- synthetic data and controlled scenarios
- Neo4j in Docker
- instance-level projection from PostgreSQL to Neo4j
- initial Event Nodes
- provenance on nodes and relationships
- Qdrant in Docker
- LangGraph Query Router
- SQL executor with guardrails
- Cypher executor with guardrails
- structured `answer_trace`
- query ladder from Step 1 to Step 5
- evaluation with expected answer spec

Out of scope for the first milestone:

- OCR and noisy documents
- structured vs PDF comparison
- complex invoice processing
- delivery notes and purchase order document flows
- Predictive Engine
- complete and polished frontend

---

## 13. Roadmap

### Phase 1 - Data and infrastructure setup

- initialize repository
- define Docker Compose for Neo4j and Qdrant
- configure Supabase
- import Northwind
- create `erp_core` and `erp_docs` schemas
- create custom tables
- generate synthetic data and controlled scenarios

### Phase 2 - Graph projection

- define PostgreSQL -> Neo4j mapping
- create instance-level nodes
- create explicit relationships
- create Event Nodes
- add provenance
- validate basic Cypher traversals

### Phase 3 - Agent Query ladder

- implement LangGraph Query Router
- implement SQL executor
- implement Cypher executor
- implement query validator
- implement answer_trace
- validate Step 1, Step 2, and Step 3

### Phase 4 - Qdrant and contract document layer

- generate clean contracts
- index chunks in Qdrant
- connect Document/Chunk references to Neo4j
- validate Step 4

### Phase 5 - Golden Query

- combine SQL, Neo4j, and Qdrant
- store effective trace
- compare against expected answer spec
- prepare demo and technical retrospective

### Phase 6 - Advanced Document Processing

- PDF parsing with OpenDataLoader
- invoices and delivery notes
- OCR and noisy documents
- structured vs PDF comparison
- extraction confidence and discrepancy detection

### Phase 7 - Predictive Engine

- demand forecasting
- anomaly detection
- stock-out prediction
- dedicated FastAPI APIs

---

## Appendix A - References

| Resource | URL |
|---|---|
| Northwind PostgreSQL | https://github.com/pthom/northwind_psql |
| OpenDataLoader PDF | https://github.com/opendataloader-project/opendataloader-pdf |
| LangChain OpenDataLoader integration | https://github.com/opendataloader-project/langchain-opendataloader-pdf |
| Supabase | https://supabase.com |
| Neo4j | https://neo4j.com |
| Qdrant | https://qdrant.tech |
| FastAPI | https://fastapi.tiangolo.com |
| LangChain | https://python.langchain.com/docs |
| LangGraph | https://langchain-ai.github.io/langgraph |
| OpenRouter | https://openrouter.ai |
| Hugging Face | https://huggingface.co |
| Docker | https://docs.docker.com |

## Appendix B - Related ADRs

The main architectural decisions are documented in `docs/adr/`:

- `0001-neo4j-for-erp-domain-graph.md`
- `0002-query-router-for-agent-planning.md`
- `0003-structured-answer-trace.md`
- `0004-event-nodes-live-only-in-neo4j.md`
- `0005-graph-provenance-required.md`
- `0006-separate-graph-and-vector-storage.md`
- `0007-qdrant-for-vector-storage.md`
- `0008-progressive-query-ladder.md`
- `0009-code-level-query-guardrails.md`
- `0010-contract-term-events-from-structured-source-first.md`
- `0011-controlled-scenarios-for-synthetic-data.md`
- `0012-use-plausible-relationships-for-event-links.md`
- `0013-top-customers-by-net-revenue.md`
- `0014-first-milestone-scope.md`

## Appendix C - Formula job description

Role: AI Engineer - R&D GenAI, Formula SpA (Impresoft Group).

Relevant activities: design and develop end-to-end RAG architectures over structured and unstructured data; build data ingestion, preprocessing, chunking, embedding, indexing, retrieval, ranking, generation, and post-processing pipelines; experiment with retrieval strategies; use open-source LLMs; evaluate GenAI systems; develop backend AI services exposed through APIs that can integrate into application software.

Requirements mapped in this project: Python, LangChain, GenAI, open-source LLMs, RAG, vector search, REST APIs, non-relational databases, vector databases, Hugging Face, FastAPI, Docker, LLM evaluation, enterprise security and governance.
