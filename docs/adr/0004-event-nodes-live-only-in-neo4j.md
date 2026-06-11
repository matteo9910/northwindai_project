# Store Event Nodes only in Neo4j

Event Nodes will live only in Neo4j and will not be materialized back into PostgreSQL. PostgreSQL remains the operational source of truth for raw ERP facts such as dates, amounts, statuses, and quantities, while Neo4j acts as the knowledge layer where derived events, semantic relationships, and graph traversal patterns are created.

**Considered Options**: Materializing events in PostgreSQL would make them easier to query with SQL, but it would blur the boundary between raw operational facts and derived knowledge, and it would introduce synchronization risk between PostgreSQL event tables and Neo4j event nodes.
