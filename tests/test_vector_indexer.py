from __future__ import annotations

from backend.vector.indexer import ContractDocumentRecord, build_contract_chunk_points


class FakeEmbeddings:
    dimension = 3

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(index), 0.1, 0.2] for index, _text in enumerate(texts)]


def test_contract_chunk_points_are_deterministic_and_metadata_scoped():
    document = ContractDocumentRecord(
        document_id=3,
        supplier_id=4,
        contract_id=3,
        contract_number="CT-4-2020",
        file_path="data/contracts/CT-4-2020.pdf",
    )
    text = "Tokyo Traders delivery lead time is fourteen business days. " * 20

    first = build_contract_chunk_points(document, text, FakeEmbeddings())
    second = build_contract_chunk_points(document, text, FakeEmbeddings())

    assert [point.id for point in first] == [point.id for point in second]
    assert len(first) > 1
    assert first[0].vector == [0.0, 0.1, 0.2]
    assert first[0].payload["supplier_id"] == 4
    assert first[0].payload["contract_id"] == 3
    assert first[0].payload["document_id"] == 3
    assert first[0].payload["contract_number"] == "CT-4-2020"
    assert first[0].payload["source_path"] == "data/contracts/CT-4-2020.pdf"
    assert "fourteen business days" in first[0].payload["text"]
