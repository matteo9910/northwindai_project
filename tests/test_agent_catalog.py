from backend.agent.catalog import SemanticCatalog


def test_catalog_slices_are_store_specific():
    catalog = SemanticCatalog()

    sql_slice = catalog.slice_for("sql")
    cypher_slice = catalog.slice_for("cypher")
    vector_slice = catalog.slice_for("vector")

    assert "erp_core.orders" in sql_slice["allowed_tables"]
    assert "Supplier" not in sql_slice
    assert "Supplier" in cypher_slice["allowed_labels"]
    assert "erp_core.orders" not in cypher_slice
    assert vector_slice["collection"] == "contract_chunks"
    assert vector_slice["mandatory_filters"] == ["supplier_id", "document_id"]


def test_planner_catalog_describes_route_families():
    text = SemanticCatalog().planner_text()

    assert "sql_plus_graph_plus_vector" in text
    assert "requires_filters_from_graph" in text

