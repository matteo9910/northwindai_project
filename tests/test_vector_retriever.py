from __future__ import annotations

from backend.vector.retriever import search_vector_chunks, validate_vector_search


class FakeEmbeddings:
    def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class FakePoint:
    id = "chunk-1"
    score = 0.88
    payload = {
        "text": "The delivery lead time is fourteen business days.",
        "supplier_id": 4,
        "document_id": 3,
    }


class FakeResponse:
    points = [FakePoint()]


class FakeClient:
    def __init__(self):
        self.calls = []

    def query_points(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse()


def test_vector_search_validation_accepts_scoped_contract_search():
    validation = validate_vector_search(
        collection_name="contract_chunks",
        top_k=3,
        filters={"supplier_id": 4, "document_id": 3},
    )

    assert validation.allowed is True
    assert validation.dialect == "vector"
    assert validation.collection_name == "contract_chunks"
    assert validation.top_k == 3
    assert validation.filters == {"supplier_id": 4, "document_id": 3}
    assert validation.violations == []


def test_vector_search_validation_rejects_unscoped_or_disallowed_search():
    validation = validate_vector_search(
        collection_name="other_chunks",
        top_k=99,
        filters={},
    )

    assert validation.allowed is False
    assert "collection_not_allowed:other_chunks" in validation.violations
    assert "top_k_exceeded:99>5" in validation.violations
    assert "metadata_filter_required" in validation.violations


def test_vector_search_returns_scoped_chunks_and_metrics():
    client = FakeClient()
    result = search_vector_chunks(
        query_text="delivery lead time",
        collection_name="contract_chunks",
        filters={"supplier_id": 4, "document_id": 3},
        embeddings=FakeEmbeddings(),
        client=client,
        top_k=3,
    )

    assert result.validation.allowed is True
    assert result.metrics.row_count == 1
    assert result.chunks == [
        {
            "chunk_id": "chunk-1",
            "score": 0.88,
            "text": "The delivery lead time is fourteen business days.",
            "supplier_id": 4,
            "document_id": 3,
        }
    ]
    assert client.calls[0]["collection_name"] == "contract_chunks"
    assert client.calls[0]["limit"] == 3
    assert client.calls[0]["with_vectors"] is False
