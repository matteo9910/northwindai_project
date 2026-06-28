from __future__ import annotations

import shutil

import psycopg
import pytest
from fastapi.testclient import TestClient
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError
from qdrant_client import QdrantClient

from backend.config import get_settings
from backend.graph.cypher_executor import GraphExecutionResult
from backend.graph.cypher_validator import validate_cypher
from backend.graph.projection import project_all
from backend.ladder.contract_lead_times import (
    ContractLeadTimeAnswer,
    ContractLeadTimesResponse,
    RetrievedContractChunk,
    answer_contract_lead_times,
    build_answer,
    build_answer_trace,
    build_contract_lead_times_cypher,
)
from backend.main import app
from backend.query.executor import QueryMetrics
from backend.query.trace import QueryRoute
from backend.vector.indexer import index_contract_documents
from backend.vector.validation import VectorValidationResult
from data_generation.contract_documents import apply_contract_document_paths
from data_generation.contracts import generate_contract_pdfs


@pytest.fixture(scope="module")
def live_settings():
    settings = get_settings()
    if (
        "__set_me__" in settings.postgres_dsn
        or "<project-ref>" in settings.postgres_dsn
        or "__set_me__" in settings.neo4j_password
    ):
        pytest.skip("Postgres/Neo4j are not configured for live Step 04 probes.")
    if shutil.which("java") is None:
        pytest.skip("Java 11+ is required by OpenDataLoader PDF live parsing.")
    try:
        with psycopg.connect(settings.postgres_dsn, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        with GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            connection_timeout=3,
        ) as driver:
            driver.verify_connectivity()
        QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
            timeout=3,
            check_compatibility=False,
        ).get_collections()
    except (psycopg.OperationalError, Neo4jError, Exception) as exc:
        pytest.skip(f"Postgres/Neo4j/Qdrant are not reachable: {exc}")

    generate_contract_pdfs()
    apply_contract_document_paths(settings=settings)
    project_all(settings=settings)
    try:
        index_contract_documents(settings=settings)
    except Exception as exc:
        pytest.skip(f"Contract indexing prerequisites are unavailable: {exc}")
    return settings


def test_contract_lead_times_cypher_validates():
    validation = validate_cypher(build_contract_lead_times_cypher())

    assert validation.allowed is True
    assert validation.referenced_labels == [
        "Contract",
        "ContractTermEvent",
        "Document",
        "Supplier",
    ]
    assert validation.referenced_relationship_types == [
        "HAS_CONTRACT",
        "HAS_DOCUMENT",
        "HAS_TERM",
    ]


def test_contract_lead_times_answer_is_evidence_first():
    answer = build_answer(
        records=[_record()],
        chunks=[
            {
                "chunk_id": "chunk-1",
                "score": 0.91,
                "text": "The delivery lead time is fourteen business days.",
                "supplier_id": 4,
                "document_id": 3,
            }
        ],
    )

    assert answer == ContractLeadTimeAnswer(
        supplier_id=4,
        supplier_name="Tokyo Traders",
        contract_id=3,
        contract_number="CT-4-2020",
        document_id=3,
        structured_lead_time_days=14,
        retrieved_evidence=[
            RetrievedContractChunk(
                chunk_id="chunk-1",
                score=0.91,
                text="The delivery lead time is fourteen business days.",
                supplier_id=4,
                document_id=3,
            )
        ],
    )


def test_contract_lead_times_trace_includes_graph_and_vector_validation():
    cypher_validation = validate_cypher(build_contract_lead_times_cypher())
    vector_validation = VectorValidationResult(
        allowed=True,
        collection_name="contract_chunks",
        top_k=3,
        filters={"supplier_id": 4, "document_id": 3},
    )
    trace = build_answer_trace(
        cypher_validation=cypher_validation,
        graph_execution=GraphExecutionResult(
            records=[_record()],
            graph_paths=[],
            metrics=QueryMetrics(row_count=1, duration_ms=1.0),
        ),
        chunks=[],
        qdrant_metrics=QueryMetrics(row_count=1, duration_ms=2.0),
        vector_validation=vector_validation,
    )

    assert trace.route == QueryRoute.GRAPH_PLUS_VECTOR
    assert trace.generated_cypher is not None
    assert trace.documents_used[0]["document_id"] == 3
    assert trace.metrics["neo4j"].row_count == 1
    assert trace.metrics["qdrant"].row_count == 1
    assert trace.validation_results == [cypher_validation, vector_validation]


def test_contract_lead_times_endpoint_returns_answer_and_trace(monkeypatch):
    response_model = ContractLeadTimesResponse(
        answer=ContractLeadTimeAnswer(
            supplier_id=4,
            supplier_name="Tokyo Traders",
            contract_id=3,
            contract_number="CT-4-2020",
            document_id=3,
            structured_lead_time_days=14,
            retrieved_evidence=[],
        ),
        answer_trace=build_answer_trace(
            cypher_validation=validate_cypher(build_contract_lead_times_cypher()),
            graph_execution=GraphExecutionResult(
                records=[_record()],
                graph_paths=[],
                metrics=QueryMetrics(row_count=1, duration_ms=1.0),
            ),
            chunks=[],
            qdrant_metrics=QueryMetrics(row_count=0, duration_ms=1.0),
            vector_validation=VectorValidationResult(
                allowed=True,
                collection_name="contract_chunks",
                top_k=3,
                filters={"supplier_id": 4, "document_id": 3},
            ),
        ),
    )
    monkeypatch.setattr(
        "backend.ladder.router.answer_contract_lead_times",
        lambda settings: response_model,
    )

    response = TestClient(app).get("/ladder/contract-lead-times")

    assert response.status_code == 200
    assert response.json()["answer"]["structured_lead_time_days"] == 14
    assert response.json()["answer_trace"]["route"] == "graph_plus_vector"


def test_contract_lead_times_live_graph_plus_vector(live_settings):
    response = answer_contract_lead_times(settings=live_settings)

    assert response.answer is not None
    assert response.answer.supplier_name == "Tokyo Traders"
    assert response.answer.structured_lead_time_days == 14
    assert response.answer.retrieved_evidence
    assert any(
        "fourteen business days" in chunk.text
        for chunk in response.answer.retrieved_evidence
    )
    assert response.answer_trace.route == QueryRoute.GRAPH_PLUS_VECTOR
    assert response.answer_trace.retrieved_chunks
    assert response.answer_trace.documents_used[0]["document_id"] == 3


def test_contract_lead_times_live_semantic_retrieval_hard_case(live_settings):
    # Exotic Liquids (supplier 1) is the deliberate hard case: its contract PDF
    # never spells out the phrase "lead time" (it says "delivery window" /
    # "fulfilment period"), so retrieval must surface the relevant clause by
    # *meaning*, not by keyword match.
    response = answer_contract_lead_times(
        settings=live_settings,
        company_name="Exotic Liquids",
    )

    assert response.answer is not None
    assert response.answer.supplier_name == "Exotic Liquids"
    # The numeric lead time still comes from supplier_contracts.lead_time_days (=12),
    # even though the PDF expresses it only in prose.
    assert response.answer.structured_lead_time_days == 12
    assert response.answer.retrieved_evidence
    evidence_text = " ".join(
        chunk.text.lower() for chunk in response.answer.retrieved_evidence
    )
    # The trap: the literal phrase is absent from the scoped document...
    assert "lead time" not in evidence_text
    # ...yet the semantically-equivalent delivery clause is retrieved.
    assert "delivery window" in evidence_text or "fulfilment" in evidence_text
    assert response.answer_trace.route == QueryRoute.GRAPH_PLUS_VECTOR
    assert all(
        chunk.supplier_id == response.answer.supplier_id
        for chunk in response.answer.retrieved_evidence
    )


def _record():
    return {
        "supplier_id": 4,
        "supplier_name": "Tokyo Traders",
        "supplier_properties": {"source_table": "suppliers"},
        "contract_id": 3,
        "contract_number": "CT-4-2020",
        "contract_properties": {"source_table": "supplier_contracts"},
        "lead_time_days": 14,
        "term_properties": {"source_table": "supplier_contracts"},
        "document_id": 3,
        "file_path": "data/contracts/CT-4-2020.pdf",
        "vector_chunk_ids": ["chunk-1"],
        "document_properties": {"source_table": "documents"},
    }
