# Use Qdrant for vector storage

The project will use Qdrant as the vector database for document chunks, embeddings, metadata filtering, and semantic retrieval. Qdrant fits the enterprise-oriented learning goals better than a lightweight local-only store because it runs cleanly in Docker, supports strong metadata filtering, and integrates well with LangChain.

**Considered Options**: Chroma would be faster to prototype locally, but Qdrant better matches the project goal of practicing a realistic GraphRAG architecture with a dedicated vector database service.
