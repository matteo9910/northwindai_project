# Derive ContractTermEvents from structured contract data first

ContractTermEvents will initially be derived from structured `supplier_contracts` fields such as lead time, start date, end date, minimum order value, and status. PDF contract parsing and comparison will be added later as an enrichment layer, after structured ContractTermEvents and graph traversal are working.

**Consequences**: The first implementation can validate the Neo4j contract path without depending on document parsing quality. Later, contract PDFs can provide textual evidence, clause extraction, and discrepancy detection between structured contract data and document content.
