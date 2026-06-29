from __future__ import annotations

from collections.abc import Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from psycopg import OperationalError as PsycopgOperationalError

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
from backend.query.executor import QueryExecutionResult, run_validated_sql
from backend.query.validator import SqlValidationResult, validate_sql

SqlExecutor = Callable[[SqlValidationResult, Settings | None], QueryExecutionResult]


class SqlWorker:
    def __init__(
        self,
        chat_model: BaseChatModel | None = None,
        catalog: SemanticCatalog | None = None,
        settings: Settings | None = None,
        executor: SqlExecutor | None = None,
    ) -> None:
        self.catalog = catalog or SemanticCatalog()
        self.settings = settings or get_settings()
        self.chat_model = chat_model
        self.executor = executor or _execute_sql
        self.chain = self._build_chain(chat_model) if chat_model is not None else None

    def _build_chain(self, chat_model: BaseChatModel):
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are the NorthwindAI SQL Specialized Worker. Generate "
                    "exactly one PostgreSQL SELECT for the sub-question. Use "
                    "only the provided Semantic Catalog. Do not include comments "
                    "or semicolons.",
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

    def run(self, task_id: str, sub_question: str) -> WorkerResult:
        attempts: list[WorkerAttempt] = []
        repair_context = ""
        max_attempts = self.settings.max_repair_attempts + 1
        last_validation: SqlValidationResult | None = None
        last_query: str | None = None
        for attempt_number in range(1, max_attempts + 1):
            generated = self._generate_query(sub_question, repair_context)
            last_query = generated
            validation = validate_sql(generated)
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
                execution = self.executor(validation, self.settings)
            except PsycopgOperationalError as exc:
                # Infrastructure failure (database unreachable/timeout): regenerating
                # the query cannot fix it, so fail fast instead of burning LLM calls.
                attempt.execution_error = str(exc)
                attempts.append(attempt)
                return WorkerResult(
                    task_id=task_id,
                    target_store=StoreTarget.SQL,
                    status=WorkerStatus.FAILURE,
                    sub_question=sub_question,
                    generated_query=validation.effective_sql,
                    validation_results=[validation],
                    attempts=attempts,
                    failure_reason="sql_execution_infrastructure_error",
                )
            except Exception as exc:  # noqa: BLE001 - worker returns structured failure.
                attempt.execution_error = str(exc)
                attempts.append(attempt)
                repair_context = f"Execution error from PostgreSQL: {exc}"
                continue
            attempts.append(attempt)
            return WorkerResult(
                task_id=task_id,
                target_store=StoreTarget.SQL,
                status=WorkerStatus.SUCCESS,
                sub_question=sub_question,
                generated_query=validation.effective_sql,
                rows=execution.rows,
                metrics={"postgresql": execution.metrics},
                validation_results=[validation],
                attempts=attempts,
            )

        return WorkerResult(
            task_id=task_id,
            target_store=StoreTarget.SQL,
            status=WorkerStatus.FAILURE,
            sub_question=sub_question,
            generated_query=last_query,
            validation_results=[last_validation] if last_validation else [],
            attempts=attempts,
            failure_reason="sql_generation_failed_within_repair_cap",
        )

    def _generate_query(self, sub_question: str, repair_context: str) -> str:
        if self.chain is None:
            self.chat_model = build_chat_model(AgentRole.SQL_WORKER, self.settings)
            self.chain = self._build_chain(self.chat_model)
        generated = invoke_structured(
            self.chain,
            {
                "catalog": self.catalog.text_for("sql"),
                "sub_question": sub_question,
                "repair_context": repair_context or "none",
            },
        )
        return generated.query.strip()


def _execute_sql(
    validation: SqlValidationResult,
    settings: Settings | None,
) -> QueryExecutionResult:
    return run_validated_sql(validation, settings=settings)


def _repair_context(violations: list[str]) -> str:
    return "Validation failed. Repair the SQL. Violations: " + ", ".join(violations)
