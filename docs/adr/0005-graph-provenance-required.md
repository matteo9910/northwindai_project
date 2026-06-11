# Require provenance on graph nodes and relationships

Every Neo4j node and relationship will carry minimal provenance metadata describing its source, projection version, and derivation path. Direct PostgreSQL projections record their source schema, table, and primary key, while derived nodes and relationships record the rule, extraction method, confidence when relevant, and source records or documents used to create them.

**Considered Options**: Adding provenance only to derived Event Nodes would reduce graph verbosity, but it would make mixed paths harder to audit and weaken answer traces when a response combines raw ERP entities, document-derived entities, and inferred business events.
