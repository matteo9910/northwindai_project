from __future__ import annotations

from backend.graph.cypher_validator import CypherPolicy, validate_cypher


def test_cypher_validator_accepts_read_only_traversal_and_injects_limit():
    result = validate_cypher(
        """
        MATCH (s:Supplier {company_name: $company_name})-[r:SUPPLIES]->(p:Product)
        RETURN p.product_id AS product_id, p.product_name AS product_name
        ORDER BY p.product_name
        """
    )

    assert result.allowed is True
    assert result.statement_type == "READ"
    assert result.referenced_labels == ["Product", "Supplier"]
    assert result.referenced_relationship_types == ["SUPPLIES"]
    assert result.effective_cypher is not None
    assert "LIMIT 1000" in result.effective_cypher


def test_cypher_validator_caps_existing_limit():
    result = validate_cypher(
        "MATCH (:Supplier)-[:SUPPLIES]->(p:Product) RETURN p LIMIT 5000"
    )

    assert result.allowed is True
    assert result.effective_cypher is not None
    assert "LIMIT 1000" in result.effective_cypher


def test_cypher_validator_rejects_mutations_and_call():
    blocked = [
        "CREATE (:Supplier {supplier_id: 1})",
        "MERGE (:Supplier {supplier_id: 1})",
        "MATCH (s:Supplier) DELETE s",
        "MATCH (s:Supplier) DETACH DELETE s",
        "MATCH (s:Supplier) SET s.company_name = 'X'",
        "MATCH (s:Supplier) REMOVE s.company_name",
        "LOAD CSV FROM 'file:///x.csv' AS row RETURN row",
        "CREATE INDEX supplier_id FOR (s:Supplier) ON (s.supplier_id)",
        "CALL db.labels()",
    ]

    for cypher in blocked:
        result = validate_cypher(cypher)
        assert result.allowed is False
        assert result.violations


def test_cypher_validator_rejects_bad_label_and_relationship():
    result = validate_cypher(
        "MATCH (:UnknownCustomer)-[:BOUGHT]->(p:Product) RETURN p"
    )

    assert result.allowed is False
    assert "label_not_allowed:UnknownCustomer" in result.violations
    assert "relationship_not_allowed:BOUGHT" in result.violations


def test_cypher_validator_rejects_paths_deeper_than_policy():
    result = validate_cypher(
        "MATCH (:Supplier)-[:SUPPLIES*1..5]->(:Product) RETURN 1",
        policy=CypherPolicy(max_depth=4),
    )

    assert result.allowed is False
    assert "path_depth_exceeded:5>4" in result.violations


def test_cypher_validator_rejects_unbounded_variable_path():
    result = validate_cypher(
        "MATCH (:Supplier)-[:SUPPLIES*]->(:Product) RETURN 1"
    )

    assert result.allowed is False
    assert "variable_path_unbounded" in result.violations


def test_cypher_validator_allows_star_in_projection():
    # A literal `*` in RETURN must not be mistaken for an unbounded path.
    result = validate_cypher(
        "MATCH (:Supplier)-[:SUPPLIES]->(p:Product) RETURN count(*) AS total"
    )

    assert result.allowed is True
    assert "variable_path_unbounded" not in result.violations


def test_cypher_validator_rejects_uppercase_label_outside_allowlist():
    # An all-uppercase label must still be enforced against the allowlist.
    result = validate_cypher(
        "MATCH (:CUSTOMER)-[:SUPPLIES]->(p:Product) RETURN p"
    )

    assert result.allowed is False
    assert "label_not_allowed:CUSTOMER" in result.violations


def test_cypher_validator_accepts_shipment_delay_traversal():
    result = validate_cypher(
        """
        MATCH (:Supplier)-[:SUPPLIES]->(:Product)<-[:CONTAINS]-(:Order)
              -[:FULFILLED_BY]->(:Shipment)-[:HAS_DELAY_EVENT]
              ->(:ShipmentDelayEvent)
        RETURN count(*) AS total
        """
    )

    assert result.allowed is True
    assert result.referenced_labels == [
        "Order",
        "Product",
        "Shipment",
        "ShipmentDelayEvent",
        "Supplier",
    ]
    assert result.referenced_relationship_types == [
        "CONTAINS",
        "FULFILLED_BY",
        "HAS_DELAY_EVENT",
        "SUPPLIES",
    ]


def test_cypher_validator_accepts_delivery_delay_complaint_traversal():
    result = validate_cypher(
        """
        MATCH (:Supplier)-[:SUPPLIES]->(:Product)<-[:CONTAINS]-(:Order)
              -[:FULFILLED_BY]->(:Shipment)-[:HAS_DELAY_EVENT]
              ->(:ShipmentDelayEvent)<-[:SUPPORTED_BY_DELAY]
              -(:DeliveryDelayComplaintEvent)<-[:CLASSIFIED_AS]
              -(:CustomerComplaintEvent)
        RETURN count(*) AS total
        """
    )

    assert result.allowed is True
    assert "DeliveryDelayComplaintEvent" in result.referenced_labels
    assert "CustomerComplaintEvent" in result.referenced_labels
    assert "CLASSIFIED_AS" in result.referenced_relationship_types
    assert "SUPPORTED_BY_DELAY" in result.referenced_relationship_types


def test_cypher_validator_rejects_legacy_possibly_related_relationship():
    result = validate_cypher(
        """
        MATCH (:ShipmentDelayEvent)-[:POSSIBLY_RELATED_TO]
              ->(:CustomerComplaintEvent)
        RETURN count(*) AS total
        """
    )

    assert result.allowed is False
    assert "relationship_not_allowed:POSSIBLY_RELATED_TO" in result.violations

