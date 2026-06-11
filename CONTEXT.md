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

**ShipmentDelayEvent**:
An event that represents a shipment delivered later than the expected or required delivery date.
_Avoid_: Late order, delay flag

**CustomerComplaintEvent**:
An event that represents a customer complaint captured from structured communications or document processing.
_Avoid_: Negative sentiment only, generic feedback

**StockOutEvent**:
An event that represents a product or warehouse inventory level reaching zero or a critical shortage threshold.
_Avoid_: Low stock flag

**InvoiceOverdueEvent**:
An event that represents an unpaid invoice whose due date has passed.
_Avoid_: Pending invoice, unpaid invoice

**ContractTermEvent**:
An event-like graph node that represents a relevant contractual term extracted from structured contract data or contract documents.
_Avoid_: Full contract text, document chunk
