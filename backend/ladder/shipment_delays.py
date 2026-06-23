from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import BaseModel

from backend.config import Settings, get_settings
from backend.graph.cypher_executor import (
    GraphExecutionResult,
    essential_provenance,
    run_validated_cypher,
)
from backend.graph.cypher_validator import CypherValidationResult, validate_cypher
from backend.graph.projection import (
    CONTAINS_RULE_NAME,
    FULFILLED_BY_RULE_NAME,
    ORDER_RULE_NAME,
    SHIPMENT_DELAY_RULE_NAME,
    SHIPMENT_RULE_NAME,
)
from backend.ladder.constants import SHIPMENT_DELAYS_COMPANY
from backend.query.trace import AnswerTrace, ProvenanceEntry, QueryRoute

TRACE_OUTPUT_PATH = Path("evaluation/answer_traces/step03_shipment_delays.json")

SHIPMENT_DELAYS_CYPHER_TEMPLATE = """
MATCH (s:Supplier {company_name: $company_name})-[:SUPPLIES]->(p:Product)
      <-[:CONTAINS]-(o:Order)-[:FULFILLED_BY]->(sh:Shipment)
      -[:HAS_DELAY_EVENT]->(e:ShipmentDelayEvent)
RETURN
  s.supplier_id AS supplier_id,
  s.company_name AS supplier_name,
  properties(s) AS supplier_properties,
  p.product_id AS product_id,
  p.product_name AS product_name,
  properties(p) AS product_properties,
  o.order_id AS order_id,
  properties(o) AS order_properties,
  sh.shipment_id AS shipment_id,
  properties(sh) AS shipment_properties,
  e.delay_days AS delay_days,
  properties(e) AS event_properties
ORDER BY e.delay_days DESC, o.order_id, sh.shipment_id, p.product_id
""".strip()


class ShipmentDelay(BaseModel):
    order_id: int
    shipment_id: int
    delay_days: int
    expected_delivery_date: str | None = None
    actual_delivery_date: str | None = None


class ShipmentDelaysResponse(BaseModel):
    answer: list[ShipmentDelay]
    answer_trace: AnswerTrace


def build_shipment_delays_cypher() -> str:
    return SHIPMENT_DELAYS_CYPHER_TEMPLATE


def answer_shipment_delays(
    settings: Settings | None = None,
    company_name: str = SHIPMENT_DELAYS_COMPANY,
) -> ShipmentDelaysResponse:
    generated_cypher = build_shipment_delays_cypher()
    validation = validate_cypher(generated_cypher)
    execution = run_validated_cypher(
        validation,
        params={"company_name": company_name},
        settings=settings,
    )
    graph_paths = build_graph_paths(execution.records)
    execution_with_paths = execution.model_copy(update={"graph_paths": graph_paths})
    return ShipmentDelaysResponse(
        answer=build_answer(execution.records),
        answer_trace=build_answer_trace(validation, execution_with_paths),
    )


def build_answer(records: list[dict]) -> list[ShipmentDelay]:
    by_shipment: dict[tuple[int, int], ShipmentDelay] = {}
    for row in records:
        order_id = int(row["order_id"])
        shipment_id = int(row["shipment_id"])
        key = (order_id, shipment_id)
        if key in by_shipment:
            continue
        shipment_properties = row.get("shipment_properties") or {}
        event_properties = row.get("event_properties") or {}
        by_shipment[key] = ShipmentDelay(
            order_id=order_id,
            shipment_id=shipment_id,
            delay_days=int(row["delay_days"]),
            expected_delivery_date=shipment_properties.get(
                "expected_delivery_date",
                event_properties.get("expected_delivery_date"),
            ),
            actual_delivery_date=shipment_properties.get(
                "actual_delivery_date",
                event_properties.get("actual_delivery_date"),
            ),
        )
    return sorted(
        by_shipment.values(),
        key=lambda item: (-item.delay_days, item.order_id, item.shipment_id),
    )


def build_graph_paths(records: list[dict]) -> list[dict]:
    paths = []
    for row in records:
        supplier_properties = row.get("supplier_properties") or {}
        product_properties = row.get("product_properties") or {}
        order_properties = row.get("order_properties") or {}
        shipment_properties = row.get("shipment_properties") or {}
        event_properties = row.get("event_properties") or {}
        paths.append(
            {
                "supplier": {
                    "supplier_id": row.get("supplier_id"),
                    "company_name": row.get("supplier_name"),
                    **essential_provenance(supplier_properties),
                },
                "product": {
                    "product_id": row.get("product_id"),
                    "product_name": row.get("product_name"),
                    **essential_provenance(product_properties),
                },
                "order": {
                    "order_id": row.get("order_id"),
                    "customer_id": order_properties.get("customer_id"),
                    "order_date": order_properties.get("order_date"),
                    **essential_provenance(order_properties),
                },
                "shipment": {
                    "shipment_id": row.get("shipment_id"),
                    "delay_days": shipment_properties.get("delay_days"),
                    "expected_delivery_date": shipment_properties.get(
                        "expected_delivery_date"
                    ),
                    "actual_delivery_date": shipment_properties.get(
                        "actual_delivery_date"
                    ),
                    **essential_provenance(shipment_properties),
                },
                "event": {
                    "label": "ShipmentDelayEvent",
                    "shipment_id": event_properties.get("shipment_id"),
                    "delay_days": row.get("delay_days"),
                    "derived_from": event_properties.get("derived_from"),
                    **essential_provenance(event_properties),
                },
                "relationships": [
                    {"type": "SUPPLIES"},
                    {"type": "CONTAINS", "rule_name": CONTAINS_RULE_NAME},
                    {"type": "FULFILLED_BY", "rule_name": FULFILLED_BY_RULE_NAME},
                    {
                        "type": "HAS_DELAY_EVENT",
                        "rule_name": SHIPMENT_DELAY_RULE_NAME,
                    },
                ],
            }
        )
    return paths


def build_answer_trace(
    validation: CypherValidationResult,
    execution: GraphExecutionResult,
) -> AnswerTrace:
    return AnswerTrace(
        route=QueryRoute.GRAPH_ONLY,
        generated_cypher=validation.effective_cypher,
        graph_paths=execution.graph_paths,
        metrics={"neo4j": execution.metrics},
        validation_results=[validation],
        provenance=[
            ProvenanceEntry(
                source_system="postgresql",
                source_schema="erp_core",
                source_table="orders",
                source_columns=["order_id", "customer_id", "order_date"],
                rule_name=ORDER_RULE_NAME,
                rule_version="v1",
            ),
            ProvenanceEntry(
                source_system="postgresql",
                source_schema="erp_core",
                source_table="order_details",
                source_columns=["order_id", "product_id"],
                rule_name=CONTAINS_RULE_NAME,
                rule_version="v1",
            ),
            ProvenanceEntry(
                source_system="postgresql",
                source_schema="erp_core",
                source_table="products",
                source_columns=["product_id", "supplier_id"],
                rule_name=CONTAINS_RULE_NAME,
                rule_version="v1",
            ),
            ProvenanceEntry(
                source_system="postgresql",
                source_schema="erp_core",
                source_table="shipments",
                source_columns=[
                    "shipment_id",
                    "order_id",
                    "expected_delivery_date",
                    "actual_delivery_date",
                    "delay_days",
                ],
                rule_name=SHIPMENT_RULE_NAME,
                rule_version="v1",
            ),
            ProvenanceEntry(
                source_system="postgresql",
                source_schema="erp_core",
                source_table="shipments",
                source_columns=[
                    "shipment_id",
                    "expected_delivery_date",
                    "actual_delivery_date",
                    "delay_days",
                ],
                rule_name=SHIPMENT_DELAY_RULE_NAME,
                rule_version="v1",
            ),
        ],
    )


def persist_answer_trace(
    trace: AnswerTrace,
    output_path: Path = TRACE_OUTPUT_PATH,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(trace.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Step 03 Shipment Delays.")
    parser.add_argument("--emit-trace", action="store_true")
    parser.add_argument(
        "--trace-path",
        type=Path,
        default=TRACE_OUTPUT_PATH,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    response = answer_shipment_delays(settings=get_settings())
    if args.emit_trace:
        path = persist_answer_trace(response.answer_trace, args.trace_path)
        print(f"answer_trace written to {path}")
    else:
        print(response.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
