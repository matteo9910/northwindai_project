# Use an explicit Query Router for agent planning

AI Agent Query will start with a LangGraph Query Router node that classifies each user question and produces an explicit execution plan. The router decides whether the answer should use SQL, Neo4j graph traversal, vector search, or a combination, so tool selection is a visible part of the agent workflow rather than hidden inside a single prompt.

**Considered Options**: Routing every question through the graph would make the GraphRAG path simpler but would weaken direct analytical questions that are better served by SQL; relying on a single prompt to choose tools would be faster to prototype but harder to inspect, test, and improve.
