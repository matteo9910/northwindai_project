from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field, ValidationError

from backend.agent.catalog import SemanticCatalog
from backend.agent.llm import (
    build_chat_model,
    build_structured_chat_model,
    invoke_structured,
)
from backend.agent.types import AgentRole, ExecutionPlan, ExecutionTask
from backend.config import Settings, get_settings
from backend.query.trace import QueryRoute

_VALID_ROUTES = {route.value for route in QueryRoute}


class PlannerOutput(BaseModel):
    route: str
    tasks: list[ExecutionTask] = Field(default_factory=list)
    rationale: str = ""
    assumptions: list[str] = Field(default_factory=list)
    terminal_action: str | None = None
    terminal_reason: str | None = None
    clarification_question: str | None = None


class Planner:
    def __init__(
        self,
        chat_model: BaseChatModel | None = None,
        catalog: SemanticCatalog | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.chat_model = chat_model
        self.catalog = catalog or SemanticCatalog()
        self.chain = self._build_chain(chat_model) if chat_model is not None else None

    def _build_chain(self, chat_model: BaseChatModel):
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are the NorthwindAI Supervisor planner. Decide an "
                    "explicit ExecutionPlan for an in-domain ERP question. "
                    "Workers are not autonomous: create precise per-store "
                    "sub-questions only. If contract PDF evidence is needed, "
                    "include a cypher task first to resolve supplier/document "
                    "filters, then a vector task depending on that graph task. "
                    "For out-of-domain questions set terminal_action='refuse' "
                    "and no tasks. For genuinely ambiguous questions set "
                    "terminal_action='clarify' with one targeted clarification "
                    "question.",
                ),
                (
                    "human",
                    "Planner Catalog:\n{catalog}\n\n"
                    "Question:\n{question}\n\n"
                    "Feedback from prior iteration:\n{feedback}",
                ),
            ]
        )
        return prompt | build_structured_chat_model(chat_model, PlannerOutput)

    def plan(
        self,
        question: str,
        feedback: str | None = None,
    ) -> ExecutionPlan:
        if self.chain is None:
            self.chat_model = build_chat_model(AgentRole.PLANNER, self.settings)
            self.chain = self._build_chain(self.chat_model)
        response = invoke_structured(
            self.chain,
            {
                "catalog": self.catalog.planner_text(),
                "question": question,
                "feedback": feedback or "none",
            },
        )
        return _parse_plan(response)


def _parse_plan(
    response: PlannerOutput | ExecutionPlan | dict[str, Any],
) -> ExecutionPlan:
    if isinstance(response, ExecutionPlan):
        return response
    if isinstance(response, PlannerOutput):
        response = response.model_dump(mode="json")
    # Terminal plans (refuse/clarify) take no executable route; the model often
    # echoes the terminal action into `route`. Normalize any non-family value to
    # a harmless placeholder so the governed contract still produces a trace.
    if response.get("route") not in _VALID_ROUTES:
        response = {**response, "route": QueryRoute.SQL_ONLY.value}
    try:
        return ExecutionPlan.model_validate(response)
    except ValidationError as exc:
        raise ValueError(f"invalid execution plan from planner: {exc}") from exc
