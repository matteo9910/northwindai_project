from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from backend.graph.cypher_validator import CypherValidationResult
from backend.query.executor import QueryMetrics
from backend.query.trace import QueryRoute
from backend.query.validator import SqlValidationResult
from backend.vector.validation import VectorValidationResult


class AgentRole(StrEnum):
    PLANNER = "planner"
    SQL_WORKER = "sql_worker"
    CYPHER_WORKER = "cypher_worker"
    SYNTHESIS = "synthesis"
    JUDGE = "judge"


class StoreTarget(StrEnum):
    SQL = "sql"
    CYPHER = "cypher"
    VECTOR = "vector"


class WorkerStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class AgentOutcome(StrEnum):
    ANSWERED = "answered"
    NEEDS_CLARIFICATION = "needs_clarification"
    ABSTAINED = "abstained"
    REFUSED = "refused"


ValidationUnion = Annotated[
    SqlValidationResult | CypherValidationResult | VectorValidationResult,
    Field(discriminator="dialect"),
]


class WorkerAttempt(BaseModel):
    attempt_number: int
    generated_query: str | None = None
    validation: ValidationUnion | None = None
    execution_error: str | None = None
    repair_prompt: str | None = None


class WorkerResult(BaseModel):
    task_id: str
    target_store: StoreTarget
    status: WorkerStatus
    sub_question: str
    generated_query: str | None = None
    rows: list[dict[str, Any]] = Field(default_factory=list)
    graph_paths: list[dict[str, Any]] = Field(default_factory=list)
    chunks: list[dict[str, Any]] = Field(default_factory=list)
    documents_used: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, QueryMetrics] = Field(default_factory=dict)
    validation_results: list[ValidationUnion] = Field(default_factory=list)
    attempts: list[WorkerAttempt] = Field(default_factory=list)
    failure_reason: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == WorkerStatus.SUCCESS


class ExecutionTask(BaseModel):
    task_id: str
    target_store: StoreTarget
    sub_question: str
    depends_on: list[str] = Field(default_factory=list)
    top_k: int = 3


class ExecutionPlan(BaseModel):
    route: QueryRoute
    tasks: list[ExecutionTask] = Field(default_factory=list)
    rationale: str = ""
    assumptions: list[str] = Field(default_factory=list)
    terminal_action: Literal["clarify", "refuse"] | None = None
    terminal_reason: str | None = None
    clarification_question: str | None = None


class GeneratedQuery(BaseModel):
    query: str
    rationale: str = ""


class SufficiencyDecision(BaseModel):
    action: Literal["answer", "replan", "clarify", "abstain", "refuse"]
    reason: str
    missing_evidence: list[str] = Field(default_factory=list)
    clarification_question: str | None = None


class EvidenceBundle(BaseModel):
    question: str
    plan: ExecutionPlan
    worker_results: list[WorkerResult] = Field(default_factory=list)
    sufficiency_decisions: list[SufficiencyDecision] = Field(default_factory=list)


class Citation(BaseModel):
    source_type: Literal["sql_row", "graph_path", "vector_chunk"]
    source_index: int
    claim: str


class SynthesisOutput(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)


class JudgeVerdict(BaseModel):
    passed: bool
    reason: str


class AgentQueryRequest(BaseModel):
    question: str
    emit_trace: bool = False


class AgentQueryResponse(BaseModel):
    outcome: AgentOutcome
    answer: str | None = None
    clarification: str | None = None
    abstention: str | None = None
    refusal: str | None = None
    answer_trace: Any
