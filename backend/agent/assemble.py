from __future__ import annotations

from typing import Any

from backend.agent.types import EvidenceBundle, WorkerResult
from backend.query.trace import AnswerTrace, ProvenanceEntry


def build_answer_trace(bundle: EvidenceBundle) -> AnswerTrace:
    return AnswerTrace(
        route=bundle.plan.route,
        generated_sql=_first_query(bundle.worker_results, "sql"),
        generated_cypher=_first_query(bundle.worker_results, "cypher"),
        execution_plan=bundle.plan.model_dump(mode="json"),
        worker_results=[
            result.model_dump(mode="json") for result in bundle.worker_results
        ],
        sufficiency_decisions=[
            decision.model_dump(mode="json")
            for decision in bundle.sufficiency_decisions
        ],
        graph_paths=_collect_graph_paths(bundle.worker_results),
        retrieved_chunks=_collect_chunks(bundle.worker_results),
        documents_used=_collect_documents(bundle.worker_results),
        metrics=_collect_metrics(bundle.worker_results),
        validation_results=_collect_validations(bundle.worker_results),
        provenance=_collect_provenance(bundle),
    )


def _first_query(results: list[WorkerResult], store: str) -> str | None:
    for result in results:
        if result.target_store == store and result.generated_query:
            return result.generated_query
    return None


def _collect_graph_paths(results: list[WorkerResult]) -> list[dict[str, Any]]:
    paths: list[dict[str, Any]] = []
    for result in results:
        paths.extend(result.graph_paths)
    return paths


def _collect_chunks(results: list[WorkerResult]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for result in results:
        chunks.extend(result.chunks)
    return chunks


def _collect_documents(results: list[WorkerResult]) -> list[dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    for result in results:
        for document in result.documents_used:
            key = str(document.get("document_id", document))
            documents[key] = document
    return list(documents.values())


def _collect_metrics(results: list[WorkerResult]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for index, result in enumerate(results, start=1):
        for name, value in result.metrics.items():
            key = name if name not in metrics else f"{name}_{index}"
            metrics[key] = value
    return metrics


def _collect_validations(results: list[WorkerResult]) -> list[Any]:
    validations: list[Any] = []
    for result in results:
        validations.extend(result.validation_results)
    return validations


def _collect_provenance(bundle: EvidenceBundle) -> list[ProvenanceEntry]:
    """Derive provenance from what each query actually referenced.

    The validators already extract the schemas/tables (SQL), labels (Cypher) and
    collection/filters (vector) touched by the generated query; we surface those
    instead of static per-store placeholders.
    """
    entries: list[ProvenanceEntry] = []
    for result in bundle.worker_results:
        for validation in result.validation_results:
            entries.extend(_provenance_for(validation))
    return entries


def _provenance_for(validation: Any) -> list[ProvenanceEntry]:
    dialect = getattr(validation, "dialect", None)
    if dialect == "sql":
        default_schema = "/".join(validation.referenced_schemas) or "erp_core/erp_docs"
        tables = validation.referenced_tables or ["generated_query_tables"]
        return [
            ProvenanceEntry(
                source_system="postgresql",
                source_schema=_schema_of(table, default_schema),
                source_table=table,
                source_columns=[],
                rule_name="agent_sql_worker",
                rule_version="v1",
            )
            for table in tables
        ]
    if dialect == "cypher":
        labels = validation.referenced_labels or ["generated_graph_traversal"]
        return [
            ProvenanceEntry(
                source_system="neo4j",
                source_schema="erp_domain_graph",
                source_table=label,
                source_columns=validation.referenced_relationship_types,
                rule_name="agent_cypher_worker",
                rule_version="v1",
            )
            for label in labels
        ]
    if dialect == "vector":
        return [
            ProvenanceEntry(
                source_system="qdrant",
                source_schema=validation.collection_name or "contract_chunks",
                source_table="vector_payload",
                source_columns=sorted(validation.filters) or ["text"],
                rule_name="agent_vector_worker",
                rule_version="v1",
            )
        ]
    return []


def _schema_of(table: str, default_schema: str) -> str:
    return table.split(".", 1)[0] if "." in table else default_schema

