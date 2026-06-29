from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from backend.agent.llm import (
    build_chat_model,
    build_structured_chat_model,
    invoke_structured,
)
from backend.agent.types import (
    AgentRole,
    EvidenceBundle,
    SufficiencyDecision,
    WorkerStatus,
)
from backend.config import Settings, get_settings


class SufficiencyChecker:
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
                    "You are the NorthwindAI Sufficiency Check. Judge whether "
                    "the gathered evidence is enough to answer the question. Do "
                    "not add facts. Choose one action: answer, replan, clarify, "
                    "abstain, refuse.",
                ),
                ("human", "Evidence bundle:\n{evidence_bundle}"),
            ]
        )
        return prompt | build_structured_chat_model(chat_model, SufficiencyDecision)

    @classmethod
    def with_default_model(cls, settings: Settings | None = None) -> SufficiencyChecker:
        settings = settings or get_settings()
        return cls(settings=settings, use_default_model=True)

    def check(
        self,
        bundle: EvidenceBundle,
        iteration: int,
        max_replans: int,
    ) -> SufficiencyDecision:
        failures = [
            result
            for result in bundle.worker_results
            if result.status == WorkerStatus.FAILURE
        ]
        if failures and iteration >= max_replans:
            return SufficiencyDecision(
                action="abstain",
                reason="worker_failure_at_replan_cap",
                missing_evidence=[
                    result.failure_reason or result.task_id for result in failures
                ],
            )
        if failures:
            return SufficiencyDecision(
                action="replan",
                reason="worker_failure_needs_targeted_replan",
                missing_evidence=[
                    result.failure_reason or result.task_id for result in failures
                ],
            )

        if not _has_any_evidence(bundle):
            if iteration >= max_replans:
                return SufficiencyDecision(
                    action="abstain",
                    reason="no_evidence_at_replan_cap",
                    missing_evidence=["No worker returned rows, paths, or chunks."],
                )
            return SufficiencyDecision(
                action="replan",
                reason="no_evidence_returned",
                missing_evidence=["No worker returned rows, paths, or chunks."],
            )

        if self.chain is None and self.use_default_model:
            self.chat_model = build_chat_model(AgentRole.PLANNER, self.settings)
            self.chain = self._build_chain(self.chat_model)
        if self.chain is None:
            return SufficiencyDecision(
                action="answer",
                reason="deterministic_evidence_available",
            )

        decision = invoke_structured(
            self.chain,
            {"evidence_bundle": bundle.model_dump_json(indent=2)},
        )
        if decision.action == "replan" and iteration >= max_replans:
            return SufficiencyDecision(
                action="abstain",
                reason="llm_requested_replan_at_cap",
                missing_evidence=decision.missing_evidence,
            )
        return decision


def _has_any_evidence(bundle: EvidenceBundle) -> bool:
    return any(
        result.rows or result.graph_paths or result.chunks
        for result in bundle.worker_results
    )
