# NorthwindAI

NorthwindAI is a mini-ERP learning project built to study AI features that operate on enterprise business data. It models a realistic ERP domain so AI services can reason over business entities, documents, and their relationships.

## Language

**AI Agent Query**:
The conversational AI feature that answers questions about ERP data by reasoning over the business domain and its supporting data sources.
_Avoid_: Chatbot, assistant only, SQL bot

**ERP Domain Graph**:
An explicit graph of business entities and business relationships in the mini-ERP, such as customers, orders, invoices, suppliers, and documents.
_Avoid_: Metadata graph, chunk graph

**Operational Source of Truth**:
The PostgreSQL data layer that stores raw ERP facts such as dates, amounts, statuses, quantities, and transactional records.
_Avoid_: Knowledge layer, derived event store

**Knowledge Layer**:
The Neo4j graph layer that stores derived knowledge such as business events, semantic relationships, and traversal-ready domain patterns.
_Avoid_: Operational database, raw ERP source

**Graph Provenance**:
The metadata attached to graph nodes and relationships that records where they came from, how they were created, and which projection or extraction rule produced them.
_Avoid_: Debug metadata, optional trace fields

**Golden Query**:
The end-to-end business question used to prove that SQL, graph traversal, vector retrieval, routing, and answer tracing work together.
_Avoid_: First test query, simple demo prompt

**Controlled Scenario**:
A deliberately generated business pattern in the synthetic ERP data used to test specific reasoning paths, edge cases, and false positives.
_Avoid_: Random sample data, demo fixture only

**Plausible Relationship**:
A derived graph relationship that links two events or entities based on temporal, semantic, or business evidence without claiming definitive causality.
_Avoid_: Causal relationship, proven cause

**Top Customer**:
A customer ranked among the highest customers by net revenue over the selected analysis period.
_Avoid_: Strategic customer, frequent customer, large account

**GraphRAG**:
A retrieval and reasoning approach that uses the ERP Domain Graph as a first-class structure for traversing business relationships, grounding answers, and connecting structured and unstructured data.
_Avoid_: Plain RAG, vector search only, SQL plus embeddings

**Explicit Graph Relationship**:
A graph relationship copied directly from a trusted ERP source relationship, such as a foreign key or an operational business link.
_Avoid_: Inferred relationship, semantic guess

**Derived Graph Relationship**:
A graph relationship produced by a controlled pipeline from operational data, document evidence, or business rules.
_Avoid_: Raw LLM guess, untracked inference

**Event Node**:
A graph node that represents a meaningful business event or operational occurrence, such as a shipment delay, customer complaint, stock-out, return, or contract breach.
_Avoid_: Shortcut edge, hidden inference

**Contract**:
A business entity node that represents a supplier contract as an agreement record in the Knowledge Layer.
_Avoid_: Contract document chunk, ContractTermEvent, PDF only

**Document Reference**:
A graph node that represents a pointer from the Knowledge Layer to a document artifact and its vector chunk identifiers, without storing full text or embeddings.
_Avoid_: Document text node, embedding node, chunk store

**ShipmentDelayEvent**:
An event that represents a shipment delivered later than the expected or required delivery date.
_Avoid_: Late order, delay flag

**CustomerComplaintEvent**:
An event that represents a customer complaint captured from structured communications or document processing.
_Avoid_: Negative sentiment only, generic feedback

**Complaint Issue Type**:
A normalized classification of a customer complaint, derived in this PoC from `erp_docs.customer_communications.subject`, such as `delivery_delay`, `packaging_quality`, or `product_quality`.
_Avoid_: Regex match, sentiment category, free-form subject only

**DeliveryDelayComplaintEvent**:
An Event Node that represents a customer complaint classified as a delivery-delay issue and supported by a matching `ShipmentDelayEvent` for the same order and product.
_Avoid_: Possible delay complaint, keyword delay match

**PackagingQualityComplaintEvent**:
An Event Node that represents a customer complaint classified as a packaging-quality issue.
_Avoid_: Damaged shipment event, generic quality complaint

**ProductQualityComplaintEvent**:
An Event Node that represents a customer complaint classified as a product-quality issue.
_Avoid_: Packaging complaint, supplier delay complaint

**StockOutEvent**:
An event that represents a product or warehouse inventory level reaching zero or a critical shortage threshold.
_Avoid_: Low stock flag

**InvoiceOverdueEvent**:
An event that represents an unpaid invoice whose due date has passed.
_Avoid_: Pending invoice, unpaid invoice

**ContractTermEvent**:
An event-like graph node that represents one specific contractual term type for a contract, such as lead time, minimum order value, or contract validity.
_Avoid_: Full contract text, document chunk, whole contract node

**In-domain Question**:
A user question whose answer is contained in the project's data sources; questions outside this scope are refused or sent back for clarification rather than answered.
_Avoid_: Any question, open chat, general knowledge query

**Supervisor**:
The single component responsible for planning and controlling how a question is answered: it forms the Execution Plan, dispatches work, runs the Sufficiency Check, and decides whether to gather more or answer.
_Avoid_: Master agent, controller, router only

**Specialized Worker**:
A focused, non-autonomous component that generates and repairs a query for exactly one data source (the SQL, Cypher, or Vector expert), grounded in that source's slice of the Semantic Catalog.
_Avoid_: Sub-agent, autonomous agent, tool only

**Semantic Catalog**:
The curated, per-source description of both structure and meaning — schema, glossary terms, example values, join paths, and allowlists — that grounds query generation.
_Avoid_: Schema dump, raw introspection, prompt boilerplate

**Execution Plan**:
The explicit, inspectable set of per-source sub-tasks the Supervisor produces before any query runs.
_Avoid_: Chain, prompt, hidden reasoning

**Sufficiency Check**:
The step where the Supervisor judges whether the evidence gathered so far answers the question or whether one more targeted step is needed, within a bounded number of iterations.
_Avoid_: Self-critique only, blind retry, confidence score

**Abstention**:
An answer in which the agent explicitly states what it could not determine because the evidence was insufficient, instead of filling the gap with model knowledge.
_Avoid_: Guess, fallback answer, best-effort completion

**Clarification**:
A response in which the agent returns a single targeted question for a genuinely ambiguous request instead of answering it.
_Avoid_: Follow-up chat, confirmation prompt, re-ask

**Evidence-First Synthesis**:
The final answer-writing step where the agent uses only gathered SQL rows, graph
paths, and retrieved chunks, citing trace elements and abstaining when evidence
is insufficient.
_Avoid_: Free-form model answer, outside knowledge, unsupported summary

**Citation**:
A reference from a final answer claim to a specific SQL row, graph path, or
vector chunk present in `answer_trace`.
_Avoid_: Footnote without source, model confidence, generic reference
