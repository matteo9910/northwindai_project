from __future__ import annotations

import json
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from backend.agent.llm import (
    build_chat_model,
    build_structured_chat_model,
    invoke_structured,
)
from backend.agent.types import (
    AgentOutcome,
    AgentRole,
    EvidenceBundle,
    SufficiencyDecision,
    SynthesisOutput,
)
from backend.config import Settings, get_settings


class SynthesisResult:
    def __init__(
        self,
        outcome: AgentOutcome,
        answer: str | None = None,
        clarification: str | None = None,
        abstention: str | None = None,
        refusal: str | None = None,
        citations: list[dict[str, Any]] | None = None,
    ) -> None:
        self.outcome = outcome
        self.answer = answer
        self.clarification = clarification
        self.abstention = abstention
        self.refusal = refusal
        self.citations = citations or []


class EvidenceFirstSynthesizer:
    def __init__(
        self,
        chat_model: BaseChatModel | None = None,
        settings: Settings | None = None,
        use_default_model: bool = False,
    ) -> None:
        self.settings = settings or get_settings()
        self.chat_model = chat_model
        self.use_default_model = use_default_model
        self.chain = self._build_chain(chat_model) if chat_model is not None else None

    def _build_chain(self, chat_model: BaseChatModel):
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are the NorthwindAI evidence-first synthesis writer. "
                    "Use only the provided evidence. Every claim must be grounded "
                    "in a cited SQL row, graph path, or vector chunk. Distinguish "
                    "certain facts from plausible relationships. Do not use "
                    "outside knowledge.",
                ),
                (
                    "human",
                    "Question: {question}\n\nEvidence:\n{evidence}",
                ),
            ]
        )
        return prompt | build_structured_chat_model(chat_model, SynthesisOutput)

    @classmethod
    def with_default_model(
        cls,
        settings: Settings | None = None,
    ) -> EvidenceFirstSynthesizer:
        settings = settings or get_settings()
        return cls(settings=settings, use_default_model=True)

    def synthesize(
        self,
        bundle: EvidenceBundle,
        decision: SufficiencyDecision,
    ) -> SynthesisResult:
        if decision.action == "clarify":
            return SynthesisResult(
                outcome=AgentOutcome.NEEDS_CLARIFICATION,
                clarification=decision.clarification_question
                or "Quale perimetro vuoi analizzare?",
            )
        if decision.action == "refuse":
            return SynthesisResult(
                outcome=AgentOutcome.REFUSED,
                refusal=decision.reason,
            )
        if decision.action == "abstain":
            missing = "; ".join(decision.missing_evidence) or decision.reason
            return SynthesisResult(
                outcome=AgentOutcome.ABSTAINED,
                abstention=f"Non posso determinarlo dai dati disponibili: {missing}",
            )
        if self.chain is None and self.use_default_model:
            self.chat_model = build_chat_model(AgentRole.SYNTHESIS, self.settings)
            self.chain = self._build_chain(self.chat_model)
        if self.chain is None:
            return _deterministic_answer(bundle)

        response = invoke_structured(
            self.chain,
            {"question": bundle.question, "evidence": _evidence_json(bundle)},
        )
        citations = [item.model_dump(mode="json") for item in response.citations]
        return SynthesisResult(
            outcome=AgentOutcome.ANSWERED,
            answer=response.answer.strip(),
            citations=citations,
        )


def _deterministic_answer(bundle: EvidenceBundle) -> SynthesisResult:
    sql_rows = [
        row
        for result in bundle.worker_results
        if result.target_store == "sql"
        for row in result.rows
    ]
    graph_rows = [
        row
        for result in bundle.worker_results
        if result.target_store == "cypher"
        for row in result.rows
    ]
    chunks = [
        chunk
        for result in bundle.worker_results
        if result.target_store == "vector"
        for chunk in result.chunks
    ]
    parts = []
    if sql_rows:
        parts.append(f"SQL ha restituito {len(sql_rows)} righe.")
    if graph_rows:
        parts.append(f"Neo4j ha restituito {len(graph_rows)} record.")
    if chunks:
        parts.append(f"Qdrant ha restituito {len(chunks)} chunk contrattuali.")
    if not parts:
        return SynthesisResult(
            outcome=AgentOutcome.ABSTAINED,
            abstention="Non ci sono evidenze sufficienti nei risultati raccolti.",
        )
    return SynthesisResult(
        outcome=AgentOutcome.ANSWERED,
        answer=" ".join(parts),
        citations=_basic_citations(sql_rows, graph_rows, chunks),
    )


def _basic_citations(
    sql_rows: list[dict[str, Any]],
    graph_rows: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    if sql_rows:
        citations.append(
            {"source_type": "sql_row", "source_index": 0, "claim": "SQL rows"}
        )
    if graph_rows:
        citations.append(
            {"source_type": "graph_path", "source_index": 0, "claim": "Graph rows"}
        )
    if chunks:
        citations.append(
            {
                "source_type": "vector_chunk",
                "source_index": 0,
                "claim": "Contract chunk evidence",
            }
        )
    return citations


def _evidence_json(bundle: EvidenceBundle) -> str:
    return json.dumps(bundle.evidence_items(), indent=2, default=str)
