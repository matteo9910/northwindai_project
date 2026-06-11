# Return structured answer traces

AI Agent Query will return a structured answer trace for every non-trivial response. The trace records the SQL queries, graph paths, vector search results, documents, chunks, and metrics used to produce the answer, supporting debugging, evaluation, traceability, and governance.

**Considered Options**: Plain natural-language answers would be faster to build but would hide the reasoning path; ad hoc debug logs would help developers but would not provide a stable artifact for frontend inspection, evaluation, or enterprise-style auditability.
