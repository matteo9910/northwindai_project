from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from qdrant_client import QdrantClient

from backend.config import Settings, get_settings
from backend.graph.cypher_executor import (
    GraphExecutionResult,
    essential_provenance,
    run_validated_cypher,
)
from backend.graph.cypher_validator import CypherValidationResult, validate_cypher
from backend.graph.projection import (
    CONTRACT_DOCUMENT_RULE_NAME,
    CONTRACT_RULE_NAME,
    CONTRACT_TERM_RULE_NAME,
    HAS_CONTRACT_RULE_NAME,
    HAS_DOCUMENT_RULE_NAME,
    HAS_TERM_RULE_NAME,
)
from backend.ladder.constants import CONTRACT_LEAD_TIMES_COMPANY
from backend.query.executor import QueryMetrics
from backend.query.trace import AnswerTrace, ProvenanceEntry, QueryRoute
from backend.vector.connection import qdrant_client
from backend.vector.embeddings import LocalBgeEmbeddings
from backend.vector.retriever import QueryEmbeddingProvider, search_vector_chunks
from backend.vector.validation import VectorValidationResult

TRACE_OUTPUT_PATH = Path("evaluation/answer_traces/step04_contract_lead_times.json")
CONTRACT_LEAD_TIME_QUERY = "delivery lead time"

CONTRACT_LEAD_TIMES_CYPHER_TEMPLATE = """
MATCH (s:Supplier {company_name: $company_name})-[:HAS_CONTRACT]->(c:Contract)
MATCH (c)-[:HAS_TERM]->(term:ContractTermEvent {term_type: 'lead_time'})
MATCH (c)-[:HAS_DOCUMENT]->(d:Document)
RETURN
  s.supplier_id AS supplier_id,
  s.company_name AS supplier_name,
  properties(s) AS supplier_properties,
  c.contract_id AS contract_id,
  c.contract_number AS contract_number,
  properties(c) AS contract_properties,
  term.lead_time_days AS lead_time_days,
  properties(term) AS term_properties,
  d.document_id AS document_id,
  d.file_path AS file_path,
  d.vector_chunk_ids AS vector_chunk_ids,
  properties(d) AS document_properties
ORDER BY c.contract_id, d.document_id
""".strip()


class RetrievedContractChunk(BaseModel):
    chunk_id: str
    score: float
    text: str
    supplier_id: int
    document_id: int
    contract_id: int | None = None
    contract_number: str | None = None
    chunk_index: int | None = None
    source_path: str | None = None


class ContractLeadTimeAnswer(BaseModel):
    supplier_id: int
    supplier_name: str
    contract_id: int
    contract_number: str
    document_id: int
    structured_lead_time_days: int
    retrieved_evidence: list[RetrievedContractChunk] = Field(default_factory=list)


class ContractLeadTimesResponse(BaseModel):
    answer: ContractLeadTimeAnswer | None
    answer_trace: AnswerTrace


def build_contract_lead_times_cypher() -> str:
    return CONTRACT_LEAD_TIMES_CYPHER_TEMPLATE


def answer_contract_lead_times(
    settings: Settings | None = None,
    company_name: str = CONTRACT_LEAD_TIMES_COMPANY,
    embeddings: QueryEmbeddingProvider | None = None,
    client: QdrantClient | None = None,
) -> ContractLeadTimesResponse:
    settings = settings or get_settings()
    generated_cypher = build_contract_lead_times_cypher()
    cypher_validation = validate_cypher(generated_cypher)
    graph_execution = run_validated_cypher(
        cypher_validation,
        params={"company_name": company_name},
        settings=settings,
    )
    graph_records = graph_execution.records
    if not graph_records:
        vector_validation = VectorValidationResult(
            allowed=False,
            collection_name=settings.qdrant_contract_collection,
            top_k=3,
            filters={},
            violations=["graph_context_required"],
        )
        return ContractLeadTimesResponse(
            answer=None,
            answer_trace=build_answer_trace(
                cypher_validation=cypher_validation,
                graph_execution=graph_execution,
                chunks=[],
                qdrant_metrics=QueryMetrics(row_count=0, duration_ms=0.0),
                vector_validation=vector_validation,
            ),
        )

    first = graph_records[0]
    filters = {
        "supplier_id": int(first["supplier_id"]),
        "document_id": int(first["document_id"]),
    }
    vector_result = search_vector_chunks(
        query_text=CONTRACT_LEAD_TIME_QUERY,
        collection_name=settings.qdrant_contract_collection,
        filters=filters,
        embeddings=embeddings or LocalBgeEmbeddings(settings),
        client=client or qdrant_client(settings),
        top_k=3,
    )
    graph_execution = graph_execution.model_copy(
        update={"graph_paths": build_graph_paths(graph_records)}
    )
    return ContractLeadTimesResponse(
        answer=build_answer(graph_records, vector_result.chunks),
        answer_trace=build_answer_trace(
            cypher_validation=cypher_validation,
            graph_execution=graph_execution,
            chunks=vector_result.chunks,
            qdrant_metrics=vector_result.metrics,
            vector_validation=vector_result.validation,
        ),
    )


def build_answer(
    records: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
) -> ContractLeadTimeAnswer | None:
    if not records:
        return None
    row = records[0]
    return ContractLeadTimeAnswer(
        supplier_id=int(row["supplier_id"]),
        supplier_name=str(row["supplier_name"]),
        contract_id=int(row["contract_id"]),
        contract_number=str(row["contract_number"]),
        document_id=int(row["document_id"]),
        structured_lead_time_days=int(row["lead_time_days"]),
        retrieved_evidence=[
            RetrievedContractChunk(
                chunk_id=str(chunk["chunk_id"]),
                score=float(chunk["score"]),
                text=str(chunk["text"]),
                supplier_id=int(chunk["supplier_id"]),
                document_id=int(chunk["document_id"]),
                contract_id=_optional_int(chunk.get("contract_id")),
                contract_number=_optional_str(chunk.get("contract_number")),
                chunk_index=_optional_int(chunk.get("chunk_index")),
                source_path=_optional_str(chunk.get("source_path")),
            )
            for chunk in chunks
        ],
    )


def build_graph_paths(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    paths = []
    for row in records:
        supplier_properties = row.get("supplier_properties") or {}
        contract_properties = row.get("contract_properties") or {}
        term_properties = row.get("term_properties") or {}
        document_properties = row.get("document_properties") or {}
        paths.append(
            {
                "supplier": {
                    "supplier_id": row.get("supplier_id"),
                    "company_name": row.get("supplier_name"),
                    **essential_provenance(supplier_properties),
                },
                "contract": {
                    "contract_id": row.get("contract_id"),
                    "contract_number": row.get("contract_number"),
                    **essential_provenance(contract_properties),
                },
                "contract_term_event": {
                    "label": "ContractTermEvent",
                    "term_type": term_properties.get("term_type"),
                    "lead_time_days": row.get("lead_time_days"),
                    **essential_provenance(term_properties),
                },
                "document": {
                    "label": "Document",
                    "document_id": row.get("document_id"),
                    "file_path": row.get("file_path"),
                    "vector_chunk_ids": row.get("vector_chunk_ids") or [],
                    **essential_provenance(document_properties),
                },
                "relationships": [
                    {
                        "type": "HAS_CONTRACT",
                        "rule_name": HAS_CONTRACT_RULE_NAME,
                    },
                    {"type": "HAS_TERM", "rule_name": HAS_TERM_RULE_NAME},
                    {
                        "type": "HAS_DOCUMENT",
                        "rule_name": HAS_DOCUMENT_RULE_NAME,
                    },
                ],
            }
        )
    return paths


def build_answer_trace(
    cypher_validation: CypherValidationResult,
    graph_execution: GraphExecutionResult,
    chunks: list[dict[str, Any]],
    qdrant_metrics: QueryMetrics,
    vector_validation: VectorValidationResult,
) -> AnswerTrace:
    records = graph_execution.records
    graph_paths = graph_execution.graph_paths or build_graph_paths(records)
    return AnswerTrace(
        route=QueryRoute.GRAPH_PLUS_VECTOR,
        generated_cypher=cypher_validation.effective_cypher,
        graph_paths=graph_paths,
        retrieved_chunks=chunks,
        documents_used=_documents_used(records),
        metrics={"neo4j": graph_execution.metrics, "qdrant": qdrant_metrics},
        validation_results=[cypher_validation, vector_validation],
        provenance=[
            ProvenanceEntry(
                source_system="postgresql",
                source_schema="erp_docs",
                source_table="supplier_contracts",
                source_columns=[
                    "contract_id",
                    "supplier_id",
                    "contract_number",
                    "lead_time_days",
                ],
                rule_name=CONTRACT_RULE_NAME,
                rule_version="v1",
            ),
            ProvenanceEntry(
                source_system="postgresql",
                source_schema="erp_docs",
                source_table="supplier_contracts",
                source_columns=["contract_id", "lead_time_days"],
                rule_name=CONTRACT_TERM_RULE_NAME,
                rule_version="v1",
            ),
            ProvenanceEntry(
                source_system="postgresql",
                source_schema="erp_docs",
                source_table="documents",
                source_columns=["document_id", "file_path", "metadata"],
                rule_name=CONTRACT_DOCUMENT_RULE_NAME,
                rule_version="v1",
            ),
        ],
    )


def _documents_used(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    documents = {}
    for row in records:
        document_id = int(row["document_id"])
        documents[document_id] = {
            "document_id": document_id,
            "file_path": row.get("file_path"),
            "vector_chunk_ids": row.get("vector_chunk_ids") or [],
        }
    return list(documents.values())


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


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
    parser = argparse.ArgumentParser(description="Run Step 04 Contract Lead Times.")
    parser.add_argument("--emit-trace", action="store_true")
    parser.add_argument(
        "--trace-path",
        type=Path,
        default=TRACE_OUTPUT_PATH,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    response = answer_contract_lead_times(settings=get_settings())
    if args.emit_trace:
        path = persist_answer_trace(response.answer_trace, args.trace_path)
        print(f"answer_trace written to {path}")
    else:
        print(response.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
