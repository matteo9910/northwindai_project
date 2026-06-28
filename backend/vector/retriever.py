from __future__ import annotations

import time
from typing import Any

import httpx
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse

from backend.query.executor import QueryMetrics
from backend.vector.validation import VectorValidationResult

ALLOWED_COLLECTIONS = {"contract_chunks"}
DEFAULT_MAX_TOP_K = 5


class QueryEmbeddingProvider:
    def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError


class VectorSearchResult(BaseModel):
    chunks: list[dict[str, Any]] = Field(default_factory=list)
    metrics: QueryMetrics
    validation: VectorValidationResult


def validate_vector_search(
    collection_name: str,
    top_k: int,
    filters: dict[str, Any],
    max_top_k: int = DEFAULT_MAX_TOP_K,
) -> VectorValidationResult:
    violations = []
    if collection_name not in ALLOWED_COLLECTIONS:
        violations.append(f"collection_not_allowed:{collection_name}")
    if top_k > max_top_k:
        violations.append(f"top_k_exceeded:{top_k}>{max_top_k}")
    if top_k < 1:
        violations.append("top_k_below_minimum")
    if not filters:
        violations.append("metadata_filter_required")

    return VectorValidationResult(
        allowed=not violations,
        collection_name=collection_name,
        top_k=top_k,
        filters=filters,
        violations=violations,
    )


def search_vector_chunks(
    query_text: str,
    collection_name: str,
    filters: dict[str, Any],
    embeddings: QueryEmbeddingProvider,
    client: QdrantClient,
    top_k: int = 3,
) -> VectorSearchResult:
    validation = validate_vector_search(
        collection_name=collection_name,
        top_k=top_k,
        filters=filters,
    )
    if not validation.allowed:
        raise ValueError("refusing to execute vector search that failed validation")

    query_vector = embeddings.embed_query(query_text)
    start = time.perf_counter()
    points = _query_points_compat(
        client=client,
        collection_name=collection_name,
        query_vector=query_vector,
        filters=filters,
        top_k=top_k,
    )
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    chunks = [_chunk_from_point(point) for point in points]
    return VectorSearchResult(
        chunks=chunks,
        metrics=QueryMetrics(row_count=len(chunks), duration_ms=duration_ms),
        validation=validation,
    )


def _metadata_filter(filters: dict[str, Any]) -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(
                key=key,
                match=models.MatchValue(value=value),
            )
            for key, value in filters.items()
        ]
    )


def _query_points_compat(
    client: QdrantClient,
    collection_name: str,
    query_vector: list[float],
    filters: dict[str, Any],
    top_k: int,
) -> list[Any]:
    try:
        response = client.query_points(
            collection_name=collection_name,
            query=query_vector,
            query_filter=_metadata_filter(filters),
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )
        return list(response.points)
    except UnexpectedResponse as exc:
        if exc.status_code != 404:
            raise
    rest_uri = getattr(client._client, "rest_uri", None)
    if rest_uri is None:
        raise RuntimeError("Qdrant REST URI is unavailable for compatibility search")
    response = httpx.post(
        f"{rest_uri}/collections/{collection_name}/points/search",
        json={
            "vector": query_vector,
            "filter": _rest_metadata_filter(filters),
            "limit": top_k,
            "with_payload": True,
            "with_vector": False,
        },
        timeout=30,
    )
    response.raise_for_status()
    return list(response.json().get("result", []))


def _rest_metadata_filter(filters: dict[str, Any]) -> dict[str, Any]:
    return {
        "must": [
            {"key": key, "match": {"value": value}}
            for key, value in filters.items()
        ]
    }


def _chunk_from_point(point: Any) -> dict[str, Any]:
    if isinstance(point, dict):
        payload = dict(point.get("payload") or {})
        return {
            "chunk_id": str(point.get("id")),
            "score": point.get("score"),
            **payload,
        }
    payload = dict(point.payload or {})
    return {
        "chunk_id": str(point.id),
        "score": point.score,
        **payload,
    }
