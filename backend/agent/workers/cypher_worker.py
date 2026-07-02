from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired

from backend.agent.catalog import SemanticCatalog
from backend.agent.llm import (
    build_chat_model,
    build_structured_chat_model,
    invoke_structured,
)
from backend.agent.types import (
    AgentRole,
    GeneratedQuery,
    StoreTarget,
    WorkerAttempt,
    WorkerResult,
    WorkerStatus,
)
from backend.config import Settings, get_settings
from backend.graph.cypher_executor import (
    GraphExecutionResult,
    run_validated_cypher,
)
from backend.graph.cypher_validator import CypherValidationResult, validate_cypher

CypherExecutor = Callable[
    [CypherValidationResult, dict[str, Any] | None, Settings | None],
    GraphExecutionResult,
]


class CypherWorker:
    def __init__(
        self,
        chat_model: BaseChatModel | None = None,
        catalog: SemanticCatalog | None = None,
        settings: Settings | None = None,
        executor: CypherExecutor | None = None,
    ) -> None:
        self.catalog = catalog or SemanticCatalog()
        self.settings = settings or get_settings()
        self.chat_model = chat_model
        self.executor = executor or _execute_cypher
        self.chain = self._build_chain(chat_model) if chat_model is not None else None

    def _build_chain(self, chat_model: BaseChatModel):
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are the NorthwindAI Cypher Specialized Worker. "
                    "Generate exactly one read-only Cypher query for the "
                    "sub-question. Use only the provided Semantic Catalog. Do "
                    "not include comments or semicolons.",
                ),
                (
                    "human",
                    "Semantic Catalog:\n{catalog}\n\n"
                    "Sub-question:\n{sub_question}\n\n"
                    "Repair context:\n{repair_context}",
                ),
            ]
        )
        return prompt | build_structured_chat_model(chat_model, GeneratedQuery)

    def run(
        self,
        task_id: str,
        sub_question: str,
        params: dict[str, Any] | None = None,
    ) -> WorkerResult:
        attempts: list[WorkerAttempt] = []
        repair_context = ""
        max_attempts = self.settings.max_repair_attempts + 1
        last_validation: CypherValidationResult | None = None
        last_query: str | None = None
        for attempt_number in range(1, max_attempts + 1):
            generated = self._generate_query(sub_question, repair_context)
            last_query = generated
            validation = validate_cypher(generated)
            last_validation = validation
            attempt = WorkerAttempt(
                attempt_number=attempt_number,
                generated_query=generated,
                validation=validation,
                repair_prompt=repair_context or None,
            )
            if not validation.allowed:
                attempts.append(attempt)
                repair_context = _repair_context(validation.violations)
                continue
            try:
                execution = self.executor(validation, params, self.settings)
            except (ServiceUnavailable, SessionExpired, AuthError) as exc:
                # Infrastructure failure (Neo4j unreachable/timeout/auth): regenerating
                # the query cannot fix it, so fail fast instead of burning LLM calls.
                attempt.execution_error = str(exc)
                attempts.append(attempt)
                return WorkerResult(
                    task_id=task_id,
                    target_store=StoreTarget.CYPHER,
                    status=WorkerStatus.FAILURE,
                    sub_question=sub_question,
                    generated_query=validation.effective_cypher,
                    validation_results=[validation],
                    attempts=attempts,
                    failure_reason="cypher_execution_infrastructure_error",
                )
            except Exception as exc:  # noqa: BLE001 - worker returns structured failure.
                attempt.execution_error = str(exc)
                attempts.append(attempt)
                repair_context = f"Execution error from Neo4j: {exc}"
                continue
            attempts.append(attempt)
            return WorkerResult(
                task_id=task_id,
                target_store=StoreTarget.CYPHER,
                status=WorkerStatus.SUCCESS,
                sub_question=sub_question,
                generated_query=validation.effective_cypher,
                rows=execution.records,
                # Agent Cypher has an LLM-chosen RETURN shape, so there are no
                # structured multi-hop paths to expose beyond the records already
                # in `rows`; only surface graph_paths when the executor builds them.
                graph_paths=execution.graph_paths,
                metrics={"neo4j": execution.metrics},
                validation_results=[validation],
                attempts=attempts,
            )

        return WorkerResult(
            task_id=task_id,
            target_store=StoreTarget.CYPHER,
            status=WorkerStatus.FAILURE,
            sub_question=sub_question,
            generated_query=last_query,
            validation_results=[last_validation] if last_validation else [],
            attempts=attempts,
            failure_reason="cypher_generation_failed_within_repair_cap",
        )

    def _generate_query(self, sub_question: str, repair_context: str) -> str:
        if self.chain is None:
            self.chat_model = build_chat_model(AgentRole.CYPHER_WORKER, self.settings)
            self.chain = self._build_chain(self.chat_model)
        generated = invoke_structured(
            self.chain,
            {
                "catalog": self.catalog.text_for("cypher"),
                "sub_question": sub_question,
                "repair_context": repair_context or "none",
            },
        )
        return generated.query.strip()


def _execute_cypher(
    validation: CypherValidationResult,
    params: dict[str, Any] | None,
    settings: Settings | None,
) -> GraphExecutionResult:
    return run_validated_cypher(validation, params=params, settings=settings)


def _repair_context(violations: list[str]) -> str:
    return "Validation failed. Repair the Cypher. Violations: " + ", ".join(
        violations
    )
