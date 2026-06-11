# NorthwindAI PRD - GraphRAG ERP Intelligence Suite

## Problem Statement

The user is preparing to join Formula SpA as an AI/ML Engineer and needs a realistic side project that builds practical confidence with the patterns likely to appear in enterprise AI work: GraphRAG over ERP data, document-aware retrieval, agent orchestration, query governance, answer traceability, and evaluation.

Generic RAG demos are not enough for this goal. The project needs to simulate a business domain where structured ERP data, derived business knowledge, and document evidence interact. It also needs to make the value of GraphRAG visible: simple analytical questions should use SQL, while investigative multi-hop questions should use the ERP Domain Graph and document retrieval.

The first milestone must therefore deliver a demonstrable AI Agent Query workflow over a mini-ERP, with a progressive query ladder that proves each layer independently before composing them into the Golden Query.

## Solution

Build NorthwindAI, a mini-ERP intelligence suite based on an extended Northwind database. The first product milestone focuses on AI Agent Query: an agentic assistant that routes user questions across PostgreSQL, Neo4j, and Qdrant, returning governed answers with structured traces.

The system will use PostgreSQL/Supabase as the Operational Source of Truth for raw ERP facts, Neo4j as the Knowledge Layer for the ERP Domain Graph, and Qdrant as the Vector Store for document chunks and semantic retrieval. LangGraph will orchestrate the agent through an explicit Query Router that chooses SQL, graph traversal, vector search, or a combination.

The first milestone proves the architecture through a progressive query ladder:

1. SQL-only customer revenue ranking.
2. Simple Neo4j supplier-to-product traversal.
3. Neo4j traversal with Event Nodes for supplier-related shipment delays.
4. Neo4j-to-Qdrant retrieval for supplier contract terms.
5. The Golden Query combining SQL, Neo4j, Qdrant, routing, and answer tracing.

The Golden Query is:

```text
Which suppliers had shipment delays that seem related to complaints from top customers in the last quarter, and how do their contract terms compare?
```

## User Stories

1. As an AI Engineer, I want a realistic ERP learning project, so that I can practice enterprise AI patterns before joining Formula SpA.
2. As an AI Engineer, I want the project to use an extended Northwind domain, so that I can work with familiar but realistic ERP entities.
3. As an AI Engineer, I want PostgreSQL to remain the Operational Source of Truth, so that raw business facts stay separate from derived knowledge.
4. As an AI Engineer, I want Neo4j to store the ERP Domain Graph, so that I can practice first-class graph modeling and traversal.
5. As an AI Engineer, I want Qdrant to store embeddings and document chunks, so that semantic retrieval is handled by a dedicated vector database.
6. As an AI Engineer, I want the database split into `erp_core` and `erp_docs`, so that the project simulates a multi-system ERP environment without excessive infrastructure complexity.
7. As an AI Engineer, I want `erp_core` to contain transactional ERP data, so that operational facts are modeled cleanly.
8. As an AI Engineer, I want `erp_docs` to contain documents, communications, contracts, and specifications, so that document-related data has a clear boundary.
9. As an AI Engineer, I want shipments modeled explicitly, so that shipment delays can be derived as business events.
10. As an AI Engineer, I want customer communications linkable to customers, orders, products, and reasons, so that complaints can be connected to operational events.
11. As an AI Engineer, I want supplier contracts to include structured lead-time data, so that contract terms can be represented before PDF parsing is mature.
12. As an AI Engineer, I want the ERP Domain Graph to be instance-level, so that actual business entities and records become traversable nodes.
13. As an AI Engineer, I want graph nodes for customers, orders, products, suppliers, shipments, contracts, documents, and events, so that the agent can navigate the real business domain.
14. As an AI Engineer, I want explicit graph relationships derived from trusted ERP links, so that the graph preserves reliable business structure.
15. As an AI Engineer, I want derived graph relationships produced only by controlled pipelines, so that the graph does not rely on untracked LLM guesses.
16. As an AI Engineer, I want Event Nodes for shipment delays, customer complaints, stock-outs, overdue invoices, and contract terms, so that operational occurrences are modeled as first-class knowledge.
17. As an AI Engineer, I want Event Nodes to live only in Neo4j, so that derived knowledge does not pollute the Operational Source of Truth.
18. As an AI Engineer, I want graph provenance on every node and relationship, so that every answer can be audited back to its source or rule.
19. As an AI Engineer, I want shipment delays and complaints linked through plausible relationships, so that the system does not overstate causality.
20. As an AI Engineer, I want Top Customers defined by net revenue, so that the Golden Query uses a stable business definition.
21. As an AI Engineer, I want synthetic data to include controlled scenarios, so that the Golden Query and false positives are testable.
22. As an AI Engineer, I want controlled scenarios for delayed suppliers serving top customers, so that GraphRAG has meaningful cases to reason over.
23. As an AI Engineer, I want controlled scenarios where delays affect non-top customers, so that the system can prove the top customer filter works.
24. As an AI Engineer, I want controlled scenarios where complaints are unrelated to delays, so that plausible relationship logic can avoid false positives.
25. As an AI Engineer, I want an explicit LangGraph Query Router, so that tool selection is inspectable and testable.
26. As an AI Engineer, I want the router to support SQL-only questions, so that simple analytical questions use the best tool.
27. As an AI Engineer, I want the router to support graph-only questions, so that multi-hop business traversal can use Neo4j.
28. As an AI Engineer, I want the router to support vector-only questions, so that pure document questions can use semantic retrieval.
29. As an AI Engineer, I want the router to support hybrid SQL, graph, and vector plans, so that complex investigative questions can combine evidence sources.
30. As an AI Engineer, I want generated SQL and Cypher validated in code, so that prompt instructions are not the only safety mechanism.
31. As an AI Engineer, I want SQL execution limited to read-only allowed schemas and tables, so that the agent cannot mutate operational data.
32. As an AI Engineer, I want Cypher execution limited to read-only traversals, so that the agent cannot mutate the Knowledge Layer.
33. As an AI Engineer, I want every non-trivial answer to return an `answer_trace`, so that I can inspect how the agent reached the answer.
34. As an AI Engineer, I want the `answer_trace` to include generated SQL, Cypher, graph paths, retrieved chunks, documents, and metrics, so that debugging is structured.
35. As an AI Engineer, I want the first query ladder step to validate SQL-only revenue ranking, so that PostgreSQL access and text-to-SQL are proven first.
36. As an AI Engineer, I want the second query ladder step to validate a simple Neo4j traversal, so that graph projection and Cypher work independently.
37. As an AI Engineer, I want the third query ladder step to validate Event Node traversal, so that derived business events are proven before document retrieval.
38. As an AI Engineer, I want the fourth query ladder step to validate Neo4j-to-Qdrant retrieval, so that contract evidence can be found through graph context.
39. As an AI Engineer, I want the fifth query ladder step to run the full Golden Query, so that the final demo proves the complete GraphRAG architecture.
40. As an AI Engineer, I want expected answer specs for each ladder step, so that evaluation checks behavior rather than surface wording only.
41. As an AI Engineer, I want actual answer traces stored for each ladder step, so that failed answers can be diagnosed by comparing expected and actual reasoning paths.
42. As an AI Engineer, I want supplier contracts to be the first document type, so that document retrieval supports the Golden Query directly.
43. As an AI Engineer, I want ContractTermEvents derived from structured contract fields first, so that graph traversal works before PDF parsing complexity is added.
44. As an AI Engineer, I want clean contract PDFs added after structured contract traversal works, so that Qdrant retrieval can be validated incrementally.
45. As an AI Engineer, I want OCR and noisy documents postponed, so that the first milestone focuses on GraphRAG rather than document parsing robustness.
46. As an AI Engineer, I want a future frontend to expose the answer and trace, so that the system can be demonstrated as an inspectable enterprise-style assistant.
47. As an AI Engineer, I want the Predictive Engine postponed, so that forecasting does not dilute the first GraphRAG milestone.
48. As an AI Engineer, I want the project decisions captured in documentation, so that future implementation work stays aligned with the agreed architecture.

## Implementation Decisions

- The first milestone focuses on AI Agent Query and the full GraphRAG query ladder.
- PostgreSQL/Supabase is the Operational Source of Truth for raw ERP facts.
- PostgreSQL will be logically split into `erp_core` and `erp_docs`.
- `erp_core` contains transactional and operational data such as customers, orders, products, suppliers, shipments, invoices, warehouses, inventory movements, and price history.
- `erp_docs` contains documents, extracted document entities, customer communications, supplier contracts, and product specifications.
- The Northwind database is the starting schema and will be extended with custom ERP tables.
- Synthetic data generation must expand the original Northwind data over a January 2020 to December 2025 horizon.
- Synthetic data generation must include both statistical realism and Controlled Scenarios.
- Controlled Scenarios must deliberately create supplier delay, top customer, complaint, contract-term, and false-positive cases.
- Top Customers are defined by net revenue over the selected analysis period, starting with the top 10 customers by revenue in the last 12 months.
- Neo4j Community is the graph database for the ERP Domain Graph.
- The ERP Domain Graph is instance-level: rows become concrete business nodes, while tables define node types.
- Event Nodes live only in Neo4j and are not stored in PostgreSQL.
- Initial Event Nodes are `ShipmentDelayEvent`, `CustomerComplaintEvent`, `StockOutEvent`, `InvoiceOverdueEvent`, and `ContractTermEvent`.
- `ContractTermEvent` is initially derived from structured supplier contract fields before PDF enrichment is introduced.
- Derived event links use plausible relationship semantics rather than definitive causality unless explicit evidence supports causation.
- Every graph node and relationship must include minimal Graph Provenance metadata.
- Qdrant is the vector database for document chunks, embeddings, metadata filtering, and semantic retrieval.
- Neo4j stores references to documents or chunks but not full embeddings or full chunk text.
- LangGraph orchestrates AI Agent Query.
- AI Agent Query starts with an explicit Query Router node.
- The Query Router produces an execution plan with routes such as `sql_only`, `graph_only`, `vector_only`, `graph_plus_sql`, `graph_plus_vector`, and `sql_plus_graph_plus_vector`.
- SQL and Cypher generated by the agent must pass through a code-level query validation layer before execution.
- SQL guardrails must enforce read-only access, allowed schemas, allowed tables, blocked mutation keywords, and row limits when appropriate.
- Cypher guardrails must enforce read-only traversal, allowed labels and relationships, blocked mutation keywords, traversal depth limits, and timeouts.
- Every non-trivial answer must include a structured `answer_trace`.
- `answer_trace` includes route, generated SQL, generated Cypher, graph paths, retrieved chunks, documents used, metrics, validation results, and provenance.
- The query ladder is the first implementation target and proceeds from SQL-only to the full Golden Query.
- Supplier contracts are the first document type for end-to-end document retrieval.
- Clean digital contract documents are introduced before noisy PDFs, OCR, or discrepancy detection.
- The first milestone excludes complex invoice processing, delivery note processing, noisy document parsing, the Predictive Engine, and a polished frontend.

## Testing Decisions

- Tests should validate external behavior and observable system contracts, not implementation details.
- The highest-value testing seam is the query ladder, because it exercises the user-facing behavior at progressively broader integration points.
- Each ladder step must have an expected answer spec rather than a fixed expected string.
- Each ladder step must persist the actual answer trace so that evaluation can compare expected route, actual route, generated SQL/Cypher, traversed graph paths, retrieved chunks, final answer, and diagnosis.
- The SQL-only ladder step validates text-to-SQL, PostgreSQL connectivity, net revenue calculation, and SQL guardrails.
- The graph-only ladder step validates PostgreSQL-to-Neo4j projection and simple Cypher traversal.
- The graph-with-events ladder step validates Event Node creation and traversal through supplier, product, order, shipment, and delay paths.
- The graph-plus-vector ladder step validates graph-driven document discovery and Qdrant retrieval.
- The Golden Query validates SQL, Neo4j, Qdrant, routing, answer synthesis, answer trace, and plausible relationship handling together.
- Query validator tests must prove that mutation SQL and Cypher are rejected.
- Query validator tests must prove that read-only allowed SQL and Cypher are accepted.
- Graph projection tests must prove that explicit relationships are created from trusted ERP links.
- Event Node tests must prove that derived events are created only in Neo4j from the expected operational facts.
- Graph Provenance tests must prove that nodes and relationships are traceable to source records, projection versions, rules, or extraction methods.
- Controlled Scenario tests must prove that the dataset contains the positive and negative cases required by the Golden Query.
- Top Customer tests must prove that the ranking is computed from net revenue rather than stored manually.
- Qdrant retrieval tests must prove that contract chunks can be filtered or retrieved by supplier/document context.
- Answer trace tests must prove that traces include enough evidence for debugging and governance.
- There is no prior automated test suite in the repo yet; the first implementation should introduce tests around the query ladder, query validation, graph projection, and controlled scenario generation.

## Out of Scope

- Full frontend implementation and visual polish.
- OCR and noisy document parsing.
- Structured-vs-PDF contract discrepancy detection.
- Complex invoice document processing.
- Delivery note and purchase order document processing.
- Predictive Engine forecasting and anomaly detection.
- Production authentication, authorization, tenant isolation, and deployment hardening.
- Real customer ERP integrations.
- Human feedback workflows for correcting agent answers.
- Training or fine-tuning open-source LLMs.
- Replacing SQL with GraphRAG for simple aggregate questions.

## Further Notes

The project intentionally preserves a clean boundary between data and knowledge: data is born in PostgreSQL, while derived knowledge is born in Neo4j. This is a central architectural principle and should guide future implementation decisions.

The first milestone should not attempt the Golden Query immediately. The progressive query ladder is the main product and engineering strategy: each step proves one layer before the full GraphRAG workflow is composed.

The PRD is based on the current repository documentation: the domain glossary, the project specification, and ADRs 0001 through 0014. The issue tracker publication step from the `to-prd` skill was not performed because no project issue tracker configuration or triage label vocabulary is present in this repository.
