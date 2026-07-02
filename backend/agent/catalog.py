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
                        "capabilities": [
                            "point lookups and aggregations over transactional "
                            "facts (counts, sums, rankings, time-windowed metrics)",
                            "direct reads and joins within the erp_core and "
                            "erp_docs tables",
                            "answers that are a direct computation over rows",
                        ],
                        "not_for": [
                            "multi-hop relationships, derived events, or temporal "
                            "causality chains -> use cypher",
                            "free-text clauses inside contract PDFs -> use vector",
                        ],
                        "examples": [
                            "top customers by net revenue",
                            "order counts per quarter",
                        ],
                    },
                    "cypher": {
                        "capabilities": [
                            "multi-hop traversals across the ERP domain graph "
                            "(Supplier-Product-Order-Shipment)",
                            "analysis of derived Event Nodes (shipment delays, "
                            "complaints, stock-outs, contract terms)",
                            "relationship/path questions and contract/document "
                            "metadata traversal",
                        ],
                        "not_for": [
                            "plain aggregates or point reads with no relationship "
                            "traversal -> use sql",
                            "retrieving the text of contract clauses -> use vector",
                        ],
                        "examples": [
                            "which Tokyo Traders orders had delays",
                            "complaints plausibly related to shipment delays",
                        ],
                    },
                    "vector": {
                        "capabilities": [
                            "semantic retrieval of contract PDF clause text",
                        ],
                        "not_for": [
                            "structured facts already in postgres or neo4j "
                            "-> use sql/cypher",
                        ],
                        "requires_filters_from_graph": ["supplier_id", "document_id"],
                        "usage_note": (
                            "must run after a cypher task resolves the document "
                            "scope (supplier_id, document_id)"
                        ),
                        "examples": [
                            "what the contract says about lead-time penalties",
                        ],
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
                "columns": {
                    "order_id": "smallint",
                    "customer_id": "varchar",
                    "employee_id": "smallint",
                    "order_date": "date",
                    "required_date": "date",
                    "shipped_date": "date",
                    "ship_via": "smallint",
                    "freight": "real",
                    "ship_name": "varchar",
                    "ship_address": "varchar",
                    "ship_city": "varchar",
                    "ship_region": "varchar",
                    "ship_postal_code": "varchar",
                    "ship_country": "varchar",
                },
                "meaning": (
                    "customer orders; join order_details by order_id; "
                    "ship_via -> shippers.shipper_id."
                ),
            },
            "erp_core.order_details": {
                "columns": {
                    "order_id": "smallint",
                    "product_id": "smallint",
                    "unit_price": "real",
                    "quantity": "smallint",
                    "discount": "real",
                },
                "meaning": (
                    "line-level revenue facts; net revenue = unit_price * "
                    "quantity * (1 - discount)."
                ),
            },
            "erp_core.customers": {
                "columns": {
                    "customer_id": "varchar",
                    "company_name": "varchar",
                    "contact_name": "varchar",
                    "contact_title": "varchar",
                    "address": "varchar",
                    "city": "varchar",
                    "region": "varchar",
                    "postal_code": "varchar",
                    "country": "varchar",
                    "phone": "varchar",
                    "fax": "varchar",
                },
                "meaning": "customer master data; customer_id is a 5-letter code.",
            },
            "erp_core.products": {
                "columns": {
                    "product_id": "smallint",
                    "product_name": "varchar",
                    "supplier_id": "smallint",
                    "category_id": "smallint",
                    "quantity_per_unit": "varchar",
                    "unit_price": "real",
                    "units_in_stock": "smallint",
                    "units_on_order": "smallint",
                    "reorder_level": "smallint",
                    "discontinued": "integer",
                },
                "meaning": (
                    "product master data; supplier_id -> suppliers, "
                    "category_id -> categories."
                ),
            },
            "erp_core.suppliers": {
                "columns": {
                    "supplier_id": "smallint",
                    "company_name": "varchar",
                    "contact_name": "varchar",
                    "contact_title": "varchar",
                    "address": "varchar",
                    "city": "varchar",
                    "region": "varchar",
                    "postal_code": "varchar",
                    "country": "varchar",
                    "phone": "varchar",
                    "fax": "varchar",
                    "homepage": "text",
                },
                "meaning": "supplier master data.",
            },
            "erp_core.categories": {
                "columns": {
                    "category_id": "smallint",
                    "category_name": "varchar",
                    "description": "text",
                    "picture": "bytea",
                },
                "meaning": "product categories.",
            },
            "erp_core.employees": {
                "columns": {
                    "employee_id": "smallint",
                    "last_name": "varchar",
                    "first_name": "varchar",
                    "title": "varchar",
                    "title_of_courtesy": "varchar",
                    "birth_date": "date",
                    "hire_date": "date",
                    "address": "varchar",
                    "city": "varchar",
                    "region": "varchar",
                    "postal_code": "varchar",
                    "country": "varchar",
                    "home_phone": "varchar",
                    "extension": "varchar",
                    "photo": "bytea",
                    "notes": "text",
                    "reports_to": "smallint",
                    "photo_path": "varchar",
                },
                "meaning": (
                    "employee master data; reports_to -> employees.employee_id "
                    "(self-reference); orders.employee_id -> employees."
                ),
            },
            "erp_core.shippers": {
                "columns": {
                    "shipper_id": "smallint",
                    "company_name": "varchar",
                    "phone": "varchar",
                },
                "meaning": "shipping carriers.",
            },
            "erp_core.shipments": {
                "columns": {
                    "shipment_id": "bigint",
                    "order_id": "smallint",
                    "carrier": "text",
                    "shipper_id": "smallint",
                    "expected_delivery_date": "date",
                    "shipped_date": "date",
                    "actual_delivery_date": "date",
                    "delay_days": "integer",
                    "status": "text",
                    "created_at": "timestamptz",
                },
                "meaning": "shipment facts; delay_days > 0 indicates a late shipment.",
            },
            "erp_core.invoices": {
                "columns": {
                    "invoice_id": "bigint",
                    "invoice_number": "text",
                    "order_id": "smallint",
                    "invoice_date": "date",
                    "due_date": "date",
                    "payment_date": "date",
                    "amount": "numeric",
                    "tax_amount": "numeric",
                    "total_amount": "numeric",
                    "status": "text",
                    "payment_method": "text",
                    "created_at": "timestamptz",
                },
                "meaning": (
                    "invoices per order; status='overdue' or payment_date>due_date "
                    "indicates a late payment; order_id -> orders."
                ),
            },
            "erp_core.warehouses": {
                "columns": {
                    "warehouse_id": "bigint",
                    "code": "text",
                    "name": "text",
                    "location": "text",
                    "warehouse_type": "text",
                    "capacity_units": "integer",
                    "created_at": "timestamptz",
                },
                "meaning": "warehouse master data.",
            },
            "erp_core.inventory_movements": {
                "columns": {
                    "movement_id": "bigint",
                    "product_id": "smallint",
                    "warehouse_id": "bigint",
                    "movement_type": "text",
                    "quantity": "integer",
                    "movement_date": "timestamptz",
                    "reference": "text",
                    "created_at": "timestamptz",
                },
                "meaning": (
                    "stock movements; product_id -> products, "
                    "warehouse_id -> warehouses."
                ),
            },
            "erp_core.price_history": {
                "columns": {
                    "price_history_id": "bigint",
                    "product_id": "smallint",
                    "old_price": "numeric",
                    "new_price": "numeric",
                    "effective_date": "date",
                    "created_at": "timestamptz",
                },
                "meaning": "product price changes over time; product_id -> products.",
            },
            "erp_core.region": {
                "columns": {
                    "region_id": "smallint",
                    "region_description": "varchar",
                },
                "meaning": "sales regions lookup.",
            },
            "erp_core.territories": {
                "columns": {
                    "territory_id": "varchar",
                    "territory_description": "varchar",
                    "region_id": "smallint",
                },
                "meaning": "sales territories; region_id -> region.",
            },
            "erp_core.employee_territories": {
                "columns": {
                    "employee_id": "smallint",
                    "territory_id": "varchar",
                },
                "meaning": "link table employees <-> territories.",
            },
            "erp_core.us_states": {
                "columns": {
                    "state_id": "smallint",
                    "state_name": "varchar",
                    "state_abbr": "varchar",
                    "state_region": "varchar",
                },
                "meaning": "US states lookup.",
            },
            "erp_core.customer_demographics": {
                "columns": {
                    "customer_type_id": "varchar",
                    "customer_desc": "text",
                },
                "meaning": "customer demographic segments.",
            },
            "erp_core.customer_customer_demo": {
                "columns": {
                    "customer_id": "varchar",
                    "customer_type_id": "varchar",
                },
                "meaning": "link table customers <-> customer_demographics.",
            },
            "erp_docs.customer_communications": {
                "columns": {
                    "communication_id": "bigint",
                    "customer_id": "varchar",
                    "order_id": "smallint",
                    "product_id": "smallint",
                    "channel": "text",
                    "contact_reason": "text",
                    "subject": "text",
                    "body": "text",
                    "sentiment": "text",
                    "occurred_at": "timestamptz",
                    "created_at": "timestamptz",
                },
                "meaning": (
                    "customer communications; subject is the structured issue "
                    "classification; contact_reason='complaint' marks complaints."
                ),
            },
            "erp_docs.supplier_contracts": {
                "columns": {
                    "contract_id": "bigint",
                    "supplier_id": "smallint",
                    "contract_number": "text",
                    "lead_time_days": "integer",
                    "start_date": "date",
                    "end_date": "date",
                    "minimum_order_value": "numeric",
                    "status": "text",
                    "created_at": "timestamptz",
                },
                "meaning": (
                    "structured supplier contract facts; supplier_id -> suppliers."
                ),
            },
            "erp_docs.documents": {
                "columns": {
                    "document_id": "bigint",
                    "doc_type": "text",
                    "title": "text",
                    "order_id": "smallint",
                    "supplier_id": "smallint",
                    "customer_id": "varchar",
                    "file_path": "text",
                    "status": "text",
                    "metadata": "jsonb",
                    "created_at": "timestamptz",
                },
                "meaning": (
                    "document references; full text and embeddings live outside "
                    "PostgreSQL/Neo4j (in Qdrant)."
                ),
            },
            "erp_docs.document_entities": {
                "columns": {
                    "document_entity_id": "bigint",
                    "document_id": "bigint",
                    "entity_type": "text",
                    "entity_ref": "text",
                    "mention": "text",
                    "confidence": "numeric",
                    "created_at": "timestamptz",
                },
                "meaning": (
                    "entities extracted from documents; document_id -> documents."
                ),
            },
            "erp_docs.product_specifications": {
                "columns": {
                    "spec_id": "bigint",
                    "product_id": "smallint",
                    "title": "text",
                    "spec_text": "text",
                    "attributes": "jsonb",
                    "created_at": "timestamptz",
                },
                "meaning": "product specification documents; product_id -> products.",
            },
        },
        "join_paths": [
            "orders.order_id -> order_details.order_id",
            "order_details.product_id -> products.product_id",
            "products.supplier_id -> suppliers.supplier_id",
            "products.category_id -> categories.category_id",
            "orders.customer_id -> customers.customer_id",
            "orders.employee_id -> employees.employee_id",
            "orders.ship_via -> shippers.shipper_id",
            "orders.order_id -> shipments.order_id",
            "shipments.shipper_id -> shippers.shipper_id",
            "orders.order_id -> invoices.order_id",
            "inventory_movements.product_id -> products.product_id",
            "inventory_movements.warehouse_id -> warehouses.warehouse_id",
            "price_history.product_id -> products.product_id",
            "customer_communications.order_id -> orders.order_id",
            "customer_communications.product_id -> products.product_id",
            "customer_communications.customer_id -> customers.customer_id",
            "supplier_contracts.supplier_id -> suppliers.supplier_id",
            "documents.supplier_id -> suppliers.supplier_id",
            "documents.order_id -> orders.order_id",
            "document_entities.document_id -> documents.document_id",
            "product_specifications.product_id -> products.product_id",
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
                "body",
                "sentiment",
                "channel",
                "contact_reason",
                "occurred_at",
            ],
            "DeliveryDelayComplaintEvent": [
                "communication_id",
                "customer_id",
                "order_id",
                "product_id",
                "issue_type",
                "subject",
                "body",
                "sentiment",
                "occurred_at",
            ],
            "PackagingQualityComplaintEvent": [
                "communication_id",
                "customer_id",
                "order_id",
                "product_id",
                "issue_type",
                "subject",
                "body",
                "sentiment",
                "occurred_at",
            ],
            "ProductQualityComplaintEvent": [
                "communication_id",
                "customer_id",
                "order_id",
                "product_id",
                "issue_type",
                "subject",
                "body",
                "sentiment",
                "occurred_at",
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
                "start_date",
                "status",
            ],
            "Document": [
                "document_id",
                "supplier_id",
                "doc_type",
                "title",
                "contract_number",
                "file_path",
                "status",
                "lead_time_days",
                "vector_chunk_ids",
            ],
        },
        "provenance_properties": {
            "properties": [
                "source_system",
                "source_schema",
                "source_table",
                "source_pk",
                "projection_version",
                "rule_name",
                "rule_version",
                "derived_from",
            ],
            "note": (
                "Every node and relationship also carries this provenance set "
                "(ADR 0005); 'derived_from' is present only on derived/event "
                "nodes. These are for traceability, not business filtering."
            ),
        },
        "property_notes": {
            "ContractTermEvent": (
                "One node per term type. Filter by term_type "
                "('lead_time', 'minimum_order_value', 'contract_validity') and "
                "return the matching scalar value (lead_time_days for lead_time, "
                "minimum_order_value for minimum_order_value)."
            ),
            "Customer": "Customer.customer_id is the 5-letter code (e.g. 'ALFKI').",
            "complaint_events": (
                "CustomerComplaintEvent is the generic complaint; "
                "Delivery/Packaging/ProductQuality variants are subject-classified "
                "issue events linked via CLASSIFIED_AS. issue_type is the "
                "normalized class (delivery_delay, packaging_quality, "
                "product_quality)."
            ),
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
