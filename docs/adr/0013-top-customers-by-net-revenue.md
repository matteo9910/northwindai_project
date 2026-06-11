# Define Top Customers by net revenue

Top Customers will be identified by net revenue over the selected analysis period, starting with the top 10 customers by revenue in the last 12 months. The metric is computed from PostgreSQL order data rather than stored manually, allowing AI Agent Query to use SQL for ranking customers before combining those customer IDs with graph traversal.

**Consequences**: The term "Top Customer" has a stable business meaning in the project, reducing ambiguity in routing, evaluation, controlled scenarios, and the Golden Query.
