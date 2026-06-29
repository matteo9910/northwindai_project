from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Literal

from backend.graph.cypher_validator import (
    ALLOWED_LABELS,
    ALLOWED_RELATIONSHIP_TYPES,
)
from backend.query.validator import ALLOWED_TABLES

CatalogStore = Literal["sql", "cypher", "vector"]


class SemanticCatalog:
    """Curated grounding context for governed generation.

    The catalog intentionally carries business meaning and safe join/traversal
    hints, not only raw schema names. Workers receive only their own store slice.
    """

    def __init__(self) -> None:
        self._slices = {
            "sql": _sql_slice(),
            "cypher": _cypher_slice(),
            "vector": _vector_slice(),
        }

    def slice_for(self, store: CatalogStore) -> dict[str, Any]:
        return deepcopy(self._slices[store])

    def text_for(self, store: CatalogStore) -> str:
        return json.dumps(self.slice_for(store), indent=2, sort_keys=True)

    def planner_text(self) -> str:
        return json.dumps(
            {
                "route_families": [
                    "sql_only",
                    "graph_only",
                    "vector_only",
                    "graph_plus_sql",
                    "graph_plus_vector",
                    "sql_plus_graph_plus_vector",
                ],
                "stores": {
                    "sql": {
                        "best_for": [
                            "aggregates over operational facts",
                            "top customers by net revenue",
                            "direct reads from erp_core/erp_docs tables",
                        ],
                    },
                    "cypher": {
                        "best_for": [
                            "supplier-product-order-shipment traversals",
                            "event node analysis",
                            "contract/document metadata traversal",
                        ],
                    },
                    "vector": {
                        "best_for": [
                            "contract PDF clause retrieval after graph scope",
                        ],
                        "requires_filters_from_graph": ["supplier_id", "document_id"],
                    },
                },
                "business_terms": _business_terms(),
            },
            indent=2,
            sort_keys=True,
        )


def _business_terms() -> dict[str, str]:
    return {
        "Operational Source of Truth": "PostgreSQL ERP data in erp_core/erp_docs.",
        "ERP Domain Graph": "Neo4j projection with events and provenance.",
        "Graph Provenance": (
            "source_system/schema/table/pk/rule properties on graph elements."
        ),
        "ShipmentDelayEvent": (
            "Neo4j event derived from shipments where delay_days > 0."
        ),
        "CustomerComplaintEvent": (
            "Neo4j event derived from customer_communications complaints."
        ),
        "CLASSIFIED_AS": (
            "Relationship from generic complaint event to issue-specific event."
        ),
        "DeliveryDelayComplaintEvent": (
            "Complaint classified by subject as delivery_delay."
        ),
        "Plausible Relationship": "Supported business link, not proof of causality.",
    }


def _sql_slice() -> dict[str, Any]:
    return {
        "store": "postgresql",
        "schemas": ["erp_core", "erp_docs"],
        "allowed_tables": sorted(ALLOWED_TABLES),
        "tables": {
            "erp_core.orders": {
                "columns": ["order_id", "customer_id", "employee_id", "order_date"],
                "meaning": "customer orders; join order_details by order_id.",
            },
            "erp_core.order_details": {
                "columns": [
                    "order_id",
                    "product_id",
                    "unit_price",
                    "quantity",
                    "discount",
                ],
                "meaning": (
                    "line-level revenue facts; net revenue = unit_price * "
                    "quantity * (1 - discount)."
                ),
            },
            "erp_core.customers": {
                "columns": ["customer_id", "company_name"],
                "meaning": "customer master data.",
            },
            "erp_core.products": {
                "columns": ["product_id", "product_name", "supplier_id"],
                "meaning": "product master data; supplier_id links to suppliers.",
            },
            "erp_core.suppliers": {
                "columns": ["supplier_id", "company_name"],
                "meaning": "supplier master data.",
            },
            "erp_core.shipments": {
                "columns": [
                    "shipment_id",
                    "order_id",
                    "expected_delivery_date",
                    "actual_delivery_date",
                    "delay_days",
                    "status",
                ],
                "meaning": "shipment facts; delay_days > 0 indicates a late shipment.",
            },
            "erp_docs.customer_communications": {
                "columns": [
                    "communication_id",
                    "customer_id",
                    "order_id",
                    "product_id",
                    "contact_reason",
                    "subject",
                    "body",
                    "sentiment",
                    "occurred_at",
                ],
                "meaning": (
                    "customer communications; subject is the structured issue "
                    "classification."
                ),
            },
            "erp_docs.supplier_contracts": {
                "columns": [
                    "contract_id",
                    "supplier_id",
                    "contract_number",
                    "lead_time_days",
                    "minimum_order_value",
                    "start_date",
                    "end_date",
                    "status",
                ],
                "meaning": "structured supplier contract facts.",
            },
            "erp_docs.documents": {
                "columns": [
                    "document_id",
                    "doc_type",
                    "title",
                    "supplier_id",
                    "file_path",
                    "status",
                    "metadata",
                ],
                "meaning": (
                    "document references; full text and embeddings live outside "
                    "PostgreSQL/Neo4j."
                ),
            },
        },
        "join_paths": [
            "orders.order_id -> order_details.order_id",
            "order_details.product_id -> products.product_id",
            "products.supplier_id -> suppliers.supplier_id",
            "orders.order_id -> shipments.order_id",
            "customer_communications.order_id -> orders.order_id",
            "customer_communications.product_id -> products.product_id",
            "supplier_contracts.supplier_id -> suppliers.supplier_id",
            "documents.supplier_id -> suppliers.supplier_id",
        ],
        "guardrails": [
            "Generate one read-only SELECT only.",
            "Use fully-qualified schema.table names.",
            "No semicolon.",
            "Never mutate data.",
        ],
        "examples": [
            {
                "question": "Top customers by net revenue",
                "shape": (
                    "SELECT customer_id, SUM(unit_price * quantity * "
                    "(1 - discount)) ... GROUP BY customer_id ORDER BY "
                    "net_revenue DESC"
                ),
            }
        ],
        "business_terms": _business_terms(),
    }


def _cypher_slice() -> dict[str, Any]:
    return {
        "store": "neo4j",
        "allowed_labels": sorted(ALLOWED_LABELS),
        "allowed_relationship_types": sorted(ALLOWED_RELATIONSHIP_TYPES),
        "node_meanings": {
            "Supplier": (
                "supplier master node from erp_core.suppliers. Properties: "
                "supplier_id, company_name. Supplier name lookup MUST use "
                "company_name, never name or supplier_name."
            ),
            "Product": "product master node supplied by Supplier",
            "Customer": "customer master node",
            "Order": "order node placed by Customer and containing Products",
            "Shipment": "shipment node fulfilling an Order",
            "ShipmentDelayEvent": "event node attached to delayed Shipment",
            "CustomerComplaintEvent": (
                "generic complaint event from customer_communications"
            ),
            "DeliveryDelayComplaintEvent": (
                "subject-classified delivery delay issue event"
            ),
            "PackagingQualityComplaintEvent": (
                "subject-classified packaging issue event"
            ),
            "ProductQualityComplaintEvent": (
                "subject-classified product quality issue event"
            ),
            "Contract": "structured supplier contract node",
            "ContractTermEvent": "contract term event such as lead_time",
            "Document": "document reference node; no full text or embeddings",
        },
        "node_properties": {
            "Supplier": ["supplier_id", "company_name"],
            "Product": ["product_id", "product_name", "supplier_id"],
            "Customer": ["customer_id", "company_name"],
            "Order": ["order_id", "customer_id", "order_date"],
            "Shipment": [
                "shipment_id",
                "order_id",
                "delay_days",
                "expected_delivery_date",
                "actual_delivery_date",
                "status",
            ],
            "ShipmentDelayEvent": [
                "shipment_id",
                "delay_days",
                "expected_delivery_date",
                "actual_delivery_date",
            ],
            "CustomerComplaintEvent": [
                "communication_id",
                "customer_id",
                "order_id",
                "product_id",
                "issue_type",
                "subject",
                "sentiment",
                "occurred_at",
            ],
            "DeliveryDelayComplaintEvent": [
                "communication_id",
                "customer_id",
                "order_id",
                "product_id",
                "issue_type",
            ],
            "Contract": [
                "contract_id",
                "contract_number",
                "supplier_id",
                "status",
                "start_date",
            ],
            "ContractTermEvent": [
                "term_key",
                "term_type",
                "contract_id",
                "lead_time_days",
                "minimum_order_value",
            ],
            "Document": [
                "document_id",
                "supplier_id",
                "contract_number",
                "file_path",
                "doc_type",
            ],
        },
        "property_notes": {
            "ContractTermEvent": (
                "One node per term type. Filter by term_type "
                "('lead_time', 'minimum_order_value', 'contract_validity') and "
                "return the matching scalar value (lead_time_days for lead_time, "
                "minimum_order_value for minimum_order_value)."
            ),
            "Customer": "Customer.customer_id is the 5-letter code (e.g. 'ALFKI').",
        },
        "traversal_paths": [
            "(s:Supplier)-[:SUPPLIES]->(p:Product)",
            "(c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)",
            "(o:Order)-[:FULFILLED_BY]->(sh:Shipment)-[:HAS_DELAY_EVENT]->(e:ShipmentDelayEvent)",
            "(cc:CustomerComplaintEvent)-[:CLASSIFIED_AS]->(dc:DeliveryDelayComplaintEvent)-[:SUPPORTED_BY_DELAY]->(e:ShipmentDelayEvent)",
            "(dc:DeliveryDelayComplaintEvent)-[:ABOUT_ORDER]->(o:Order)",
            "(dc:DeliveryDelayComplaintEvent)-[:ABOUT_PRODUCT]->(p:Product)",
            "(s:Supplier)-[:HAS_CONTRACT]->(c:Contract)-[:HAS_TERM]->(t:ContractTermEvent)",
            "(c:Contract)-[:HAS_DOCUMENT]->(d:Document)",
        ],
        "guardrails": [
            "Generate one read-only MATCH/RETURN query.",
            "No semicolon.",
            "Use only allowed labels and relationship types.",
            "Use only documented node properties.",
            "Supplier name lookup is `s.company_name = 'Tokyo Traders'`.",
            "Return scalar ids/names/properties needed as evidence, not whole nodes.",
            "When a specific term is asked, filter ContractTermEvent by term_type "
            "and return its scalar value field.",
            "For vector follow-up, return supplier_id and document_id.",
        ],
        "business_terms": _business_terms(),
    }


def _vector_slice() -> dict[str, Any]:
    return {
        "store": "qdrant",
        "collection": "contract_chunks",
        "embedding_model": "BAAI/bge-small-en-v1.5",
        "payload_fields": [
            "chunk_id",
            "text",
            "supplier_id",
            "document_id",
            "contract_id",
            "contract_number",
            "chunk_index",
            "source_path",
        ],
        "mandatory_filters": ["supplier_id", "document_id"],
        "filter_source": "Resolved from graph evidence, never directly from user text.",
        "guardrails": ["No generation; embed the question and run scoped retrieval."],
    }
