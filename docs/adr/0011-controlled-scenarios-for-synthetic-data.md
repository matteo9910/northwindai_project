# Generate controlled scenarios in synthetic data

Synthetic ERP data will include controlled business scenarios designed to make the GraphRAG query ladder and Golden Query testable. In addition to statistically realistic data, the generator will create deliberate patterns such as suppliers with delayed shipments to top customers, suppliers with delays to non-top customers, complaints unrelated to delays, and contrasting contract terms.

**Consequences**: The dataset can validate reasoning paths, false positives, and multi-hop behavior instead of relying on random generation to accidentally produce useful cases. This makes evaluation repeatable and keeps the demo grounded in explainable business situations.
