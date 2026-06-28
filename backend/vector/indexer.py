from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import psycopg
from neo4j import Driver
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import PointStruct

from backend.config import Settings, get_settings
from backend.graph.connection import neo4j_driver
from backend.vector.connection import qdrant_client
from backend.vector.embeddings import LocalBgeEmbeddings
from backend.vector.pdf_loader import load_pdf_text

CHUNK_SIZE = 700
CHUNK_OVERLAP = 100
POINT_NAMESPACE = uuid.UUID("f3ef8b21-31f9-4c62-9e83-bc4dbfb5f7c8")

CONTRACT_DOCUMENT_RECORDS_SQL = """
select d.document_id,
       d.supplier_id,
       sc.contract_id,
       sc.contract_number,
       d.file_path
from erp_docs.documents d
join erp_docs.supplier_contracts sc
  on sc.supplier_id = d.supplier_id
 and sc.contract_number = d.metadata->>'contract_number'
where d.doc_type = 'supplier_contract'
  and d.file_path is not null
order by d.document_id
""".strip()


class EmbeddingProvider(Protocol):
    dimension: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed document chunks."""


@dataclass(frozen=True)
class ContractDocumentRecord:
    document_id: int
    supplier_id: int
    contract_id: int
    contract_number: str
    file_path: str


class ContractIndexingSummary(BaseModel):
    collection_name: str
    documents_indexed: int
    chunks_indexed: int


def split_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return []
    chunks = []
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        chunks.append(normalized[start:end])
        if end == len(normalized):
            break
        start = max(end - chunk_overlap, start + 1)
    return chunks


def build_contract_chunk_points(
    document: ContractDocumentRecord,
    text: str,
    embeddings: EmbeddingProvider,
) -> list[PointStruct]:
    chunks = split_text(text)
    vectors = embeddings.embed_documents(chunks)
    points = []
    for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
        point_id = str(
            uuid.uuid5(
                POINT_NAMESPACE,
                f"{document.document_id}:{index}",
            )
        )
        points.append(
            PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "supplier_id": document.supplier_id,
                    "contract_id": document.contract_id,
                    "document_id": document.document_id,
                    "contract_number": document.contract_number,
                    "chunk_index": index,
                    "source_path": document.file_path,
                    "text": chunk,
                },
            )
        )
    return points


def index_contract_documents(
    settings: Settings | None = None,
    embeddings: EmbeddingProvider | None = None,
    client: QdrantClient | None = None,
    pdf_loader: Callable[[Path], str] = load_pdf_text,
) -> ContractIndexingSummary:
    settings = settings or get_settings()
    embeddings = embeddings or LocalBgeEmbeddings(settings)
    client = client or qdrant_client(settings)
    collection_name = settings.qdrant_contract_collection
    _ensure_collection(client, collection_name, embeddings.dimension)

    documents = _fetch_contract_document_records(settings)
    chunk_count = 0
    chunk_ids_by_document: dict[int, list[str]] = {}
    for document in documents:
        text = pdf_loader(Path(document.file_path))
        if not text.strip():
            raise RuntimeError(
                f"OpenDataLoader returned no text for {document.file_path}"
            )
        points = build_contract_chunk_points(document, text, embeddings)
        if not points:
            chunk_ids_by_document[document.document_id] = []
            continue
        client.upsert(collection_name=collection_name, points=points, wait=True)
        point_ids = [str(point.id) for point in points]
        chunk_ids_by_document[document.document_id] = point_ids
        chunk_count += len(points)

    _update_document_chunk_ids(settings, chunk_ids_by_document)
    return ContractIndexingSummary(
        collection_name=collection_name,
        documents_indexed=len(documents),
        chunks_indexed=chunk_count,
    )


def _fetch_contract_document_records(
    settings: Settings,
) -> list[ContractDocumentRecord]:
    with psycopg.connect(settings.postgres_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(CONTRACT_DOCUMENT_RECORDS_SQL)
            return [
                ContractDocumentRecord(
                    document_id=int(row[0]),
                    supplier_id=int(row[1]),
                    contract_id=int(row[2]),
                    contract_number=str(row[3]),
                    file_path=str(row[4]),
                )
                for row in cur.fetchall()
            ]


def _ensure_collection(
    client: QdrantClient,
    collection_name: str,
    vector_size: int,
) -> None:
    if client.collection_exists(collection_name):
        return
    client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(
            size=vector_size,
            distance=models.Distance.COSINE,
        ),
    )


def _update_document_chunk_ids(
    settings: Settings,
    chunk_ids_by_document: dict[int, list[str]],
) -> None:
    if not chunk_ids_by_document:
        return
    with neo4j_driver(settings) as driver:
        _write_document_chunk_ids(driver, chunk_ids_by_document)


def _write_document_chunk_ids(
    driver: Driver,
    chunk_ids_by_document: dict[int, list[str]],
) -> None:
    rows = [
        {"document_id": document_id, "vector_chunk_ids": chunk_ids}
        for document_id, chunk_ids in chunk_ids_by_document.items()
    ]
    with driver.session() as session:
        session.run(
            """
            UNWIND $rows AS row
            MATCH (d:Document {document_id: row.document_id})
            SET d.vector_chunk_ids = row.vector_chunk_ids
            """,
            {"rows": rows},
        ).consume()


def main() -> None:
    summary = index_contract_documents(settings=get_settings())
    print(summary.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
