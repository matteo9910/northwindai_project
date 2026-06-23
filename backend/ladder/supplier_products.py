from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import BaseModel

from backend.config import Settings, get_settings
from backend.graph.cypher_executor import GraphExecutionResult, run_validated_cypher
from backend.graph.cypher_validator import CypherValidationResult, validate_cypher
from backend.graph.projection import SUPPLIES_RULE_NAME
from backend.ladder.constants import SUPPLIER_PRODUCTS_COMPANY
from backend.query.trace import AnswerTrace, ProvenanceEntry, QueryRoute

TRACE_OUTPUT_PATH = Path("evaluation/answer_traces/step02_supplier_products.json")

SUPPLIER_PRODUCTS_CYPHER_TEMPLATE = """
MATCH (s:Supplier {company_name: $company_name})-[r:SUPPLIES]->(p:Product)
RETURN
  s.supplier_id AS supplier_id,
  s.company_name AS supplier_name,
  properties(s) AS supplier_properties,
  type(r) AS relationship_type,
  properties(r) AS relationship_properties,
  p.product_id AS product_id,
  p.product_name AS product_name,
  properties(p) AS product_properties
ORDER BY p.product_name
""".strip()


class SupplierProduct(BaseModel):
    product_id: int
    product_name: str


class SupplierProductsResponse(BaseModel):
    answer: list[SupplierProduct]
    answer_trace: AnswerTrace


def build_supplier_products_cypher() -> str:
    return SUPPLIER_PRODUCTS_CYPHER_TEMPLATE


def answer_supplier_products(
    settings: Settings | None = None,
    company_name: str = SUPPLIER_PRODUCTS_COMPANY,
) -> SupplierProductsResponse:
    generated_cypher = build_supplier_products_cypher()
    validation = validate_cypher(generated_cypher)
    execution = run_validated_cypher(
        validation,
        params={"company_name": company_name},
        settings=settings,
    )
    answer = [
        SupplierProduct(
            product_id=int(row["product_id"]),
            product_name=str(row["product_name"]),
        )
        for row in execution.records
    ]
    return SupplierProductsResponse(
        answer=answer,
        answer_trace=build_answer_trace(validation, execution),
    )


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
                source_table="suppliers",
                source_columns=["supplier_id", "company_name"],
                rule_name="supplier_projection",
                rule_version="v1",
            ),
            ProvenanceEntry(
                source_system="postgresql",
                source_schema="erp_core",
                source_table="products",
                source_columns=["product_id", "product_name", "supplier_id"],
                rule_name="product_projection",
                rule_version="v1",
            ),
            ProvenanceEntry(
                source_system="postgresql",
                source_schema="erp_core",
                source_table="products",
                source_columns=["product_id", "supplier_id"],
                rule_name=SUPPLIES_RULE_NAME,
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
    parser = argparse.ArgumentParser(description="Run Step 02 Supplier Products.")
    parser.add_argument("--emit-trace", action="store_true")
    parser.add_argument(
        "--trace-path",
        type=Path,
        default=TRACE_OUTPUT_PATH,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    response = answer_supplier_products(settings=get_settings())
    if args.emit_trace:
        path = persist_answer_trace(response.answer_trace, args.trace_path)
        print(f"answer_trace written to {path}")
    else:
        print(response.model_dump_json(indent=2))


if __name__ == "__main__":
    main()

