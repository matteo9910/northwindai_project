# Separate graph and vector storage

Neo4j will store business entities, relationships, Event Nodes, and references to relevant documents or chunks, while the vector database will store chunk text, embeddings, metadata, and semantic similarity indexes. PostgreSQL remains responsible for raw operational facts, so each persistence layer has a distinct role in the GraphRAG architecture.

**Considered Options**: Storing full extracted text and chunks directly in Neo4j would simplify the first prototype, but it would blur graph traversal with semantic retrieval and make it harder to evaluate the value added by the vector database.
