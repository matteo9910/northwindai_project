from __future__ import annotations

from collections.abc import Callable
from typing import Any

from qdrant_client import QdrantClient

from backend.agent.types import (
    StoreTarget,
    WorkerAttempt,
    WorkerResult,
    WorkerStatus,
)
from backend.config import Settings, get_settings
from backend.query.executor import QueryMetrics
from backend.vector.connection import qdrant_client
from backend.vector.embeddings import LocalBgeEmbeddings
from backend.vector.retriever import (
    QueryEmbeddingProvider,
    VectorSearchResult,
    search_vector_chunks,
    validate_vector_search,
)

VectorSearchCallable = Callable[
    [str, str, dict[str, Any], QueryEmbeddingProvider, QdrantClient, int],
    VectorSearchResult,
]


class VectorWorker:
    def __init__(
        self,
        settings: Settings | None = None,
        embeddings: QueryEmbeddingProvider | None = None,
        client: QdrantClient | None = None,
        search: VectorSearchCallable | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.embeddings = embeddings
        self.client = client
        self.search = search or search_vector_chunks

    def run(
        self,
        task_id: str,
        sub_question: str,
        prior_results: list[WorkerResult],
        top_k: int = 3,
    ) -> WorkerResult:
        filters = resolve_vector_filters(prior_results)
        validation = validate_vector_search(
            collection_name=self.settings.qdrant_contract_collection,
            top_k=top_k,
            filters=filters,
        )
        attempt = WorkerAttempt(attempt_number=1, validation=validation)
        if not validation.allowed:
            return WorkerResult(
                task_id=task_id,
                target_store=StoreTarget.VECTOR,
                status=WorkerStatus.FAILURE,
                sub_question=sub_question,
                metrics={"qdrant": QueryMetrics(row_count=0, duration_ms=0.0)},
                validation_results=[validation],
                attempts=[attempt],
                failure_reason="vector_search_requires_graph_resolved_filters",
            )

        result = self.search(
            sub_question,
            self.settings.qdrant_contract_collection,
            filters,
            self.embeddings or LocalBgeEmbeddings(self.settings),
            self.client or qdrant_client(self.settings),
            top_k,
        )
        return WorkerResult(
            task_id=task_id,
            target_store=StoreTarget.VECTOR,
            status=WorkerStatus.SUCCESS,
            sub_question=sub_question,
            chunks=result.chunks,
            documents_used=_documents_used(result.chunks),
            metrics={"qdrant": result.metrics},
            validation_results=[result.validation],
            attempts=[attempt],
        )


def resolve_vector_filters(prior_results: list[WorkerResult]) -> dict[str, Any]:
    for result in prior_results:
        for row in result.rows:
            supplier_id = row.get("supplier_id")
            document_id = row.get("document_id")
            if supplier_id is not None and document_id is not None:
                return {
                    "supplier_id": int(supplier_id),
                    "document_id": int(document_id),
                }
        for path in result.graph_paths:
            document = path.get("document") if isinstance(path, dict) else None
            supplier = path.get("supplier") if isinstance(path, dict) else None
            if document and supplier:
                supplier_id = supplier.get("supplier_id")
                document_id = document.get("document_id")
                if supplier_id is not None and document_id is not None:
                    return {
                        "supplier_id": int(supplier_id),
                        "document_id": int(document_id),
                    }
    return {}


def _documents_used(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    documents: dict[int, dict[str, Any]] = {}
    for chunk in chunks:
        document_id = chunk.get("document_id")
        if document_id is None:
            continue
        documents[int(document_id)] = {
            "document_id": int(document_id),
            "source_path": chunk.get("source_path"),
            "contract_number": chunk.get("contract_number"),
        }
    return list(documents.values())
