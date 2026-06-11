# Use Neo4j for the ERP Domain Graph

We will store the ERP Domain Graph in Neo4j Community, populated by controlled pipelines from Supabase PostgreSQL. Supabase remains the operational source of truth, while Neo4j provides an explicit graph database for instance-level business entities, explicit relationships, and derived relationships used by GraphRAG.

**Considered Options**: NetworkX was simpler but less representative of an enterprise graph architecture; PostgreSQL recursive queries kept the stack smaller but would not provide a first-class graph model; vector database metadata alone was useful for retrieval but too weak for domain graph traversal.
