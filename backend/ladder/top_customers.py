from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel

from backend.config import Settings, get_settings
from backend.ladder.constants import (
    ANALYSIS_AS_OF,
    LAST_12M_START,
    TOP_CUSTOMERS_LIMIT,
)
from backend.query.executor import QueryExecutionResult, run_validated_sql
from backend.query.trace import AnswerTrace, ProvenanceEntry, QueryRoute
from backend.query.validator import ValidationResult, validate_sql

TRACE_OUTPUT_PATH = Path("evaluation/answer_traces/step01_top_customers.json")

# Net revenue must match Phase 03 data_generation.scenarios.TOP_CUSTOMERS_SQL.
TOP_CUSTOMERS_SQL_TEMPLATE = """
select o.customer_id,
       sum(od.unit_price * od.quantity * (1 - od.discount)) as net_revenue
from erp_core.orders o
join erp_core.order_details od on od.order_id = o.order_id
where o.order_date >= date '{start}' and o.order_date <= date '{end}'
group by o.customer_id
order by net_revenue desc
limit {limit}
""".strip()


class TopCustomer(BaseModel):
    customer_id: str
    net_revenue: Decimal


class TopCustomersResponse(BaseModel):
    answer: list[TopCustomer]
    answer_trace: AnswerTrace


def build_top_customers_sql() -> str:
    return TOP_CUSTOMERS_SQL_TEMPLATE.format(
        start=LAST_12M_START.isoformat(),
        end=ANALYSIS_AS_OF.isoformat(),
        limit=TOP_CUSTOMERS_LIMIT,
    )


def answer_top_customers(settings: Settings | None = None) -> TopCustomersResponse:
    generated_sql = build_top_customers_sql()
    validation = validate_sql(generated_sql)
    execution = run_validated_sql(validation, settings=settings)
    answer = [
        TopCustomer(
            customer_id=str(row["customer_id"]),
            net_revenue=Decimal(str(row["net_revenue"])),
        )
        for row in execution.rows
    ]
    return TopCustomersResponse(
        answer=answer,
        answer_trace=build_answer_trace(validation, execution),
    )


def build_answer_trace(
    validation: ValidationResult,
    execution: QueryExecutionResult,
) -> AnswerTrace:
    return AnswerTrace(
        route=QueryRoute.SQL_ONLY,
        generated_sql=validation.effective_sql,
        metrics={"postgresql": execution.metrics},
        validation_results=[validation],
        provenance=[
            ProvenanceEntry(
                source_system="postgresql",
                source_schema="erp_core",
                source_table="orders",
                source_columns=["customer_id", "order_date", "order_id"],
                rule_name="top_customers",
                rule_version="v1",
            ),
            ProvenanceEntry(
                source_system="postgresql",
                source_schema="erp_core",
                source_table="order_details",
                source_columns=["unit_price", "quantity", "discount", "order_id"],
                rule_name="top_customers",
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
    parser = argparse.ArgumentParser(description="Run Step 01 Top Customers.")
    parser.add_argument("--emit-trace", action="store_true")
    parser.add_argument(
        "--trace-path",
        type=Path,
        default=TRACE_OUTPUT_PATH,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    response = answer_top_customers(settings=get_settings())
    if args.emit_trace:
        path = persist_answer_trace(response.answer_trace, args.trace_path)
        print(f"answer_trace written to {path}")
    else:
        print(response.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
