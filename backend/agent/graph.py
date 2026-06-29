from __future__ import annotations

import json
import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.agent.assemble import build_answer_trace
from backend.agent.catalog import SemanticCatalog
from backend.agent.planner import Planner
from backend.agent.sufficiency import SufficiencyChecker
from backend.agent.synthesis import EvidenceFirstSynthesizer, SynthesisResult
from backend.agent.types import (
    AgentQueryResponse,
    EvidenceBundle,
    ExecutionPlan,
    ExecutionTask,
    StoreTarget,
    SufficiencyDecision,
    WorkerResult,
)
from backend.agent.workers.cypher_worker import CypherWorker
from backend.agent.workers.sql_worker import SqlWorker
from backend.agent.workers.vector_worker import VectorWorker
from backend.config import Settings, get_settings


class AgentState(TypedDict, total=False):
    question: str
    plan: ExecutionPlan
    worker_results: list[WorkerResult]
    # Accumulate across replan iterations so the trace keeps the full reflection
    # history (worker_results is intentionally left replace-only: each dispatch
    # gathers fresh evidence).
    sufficiency_decisions: Annotated[list[SufficiencyDecision], operator.add]
    iteration: int
    feedback: str | None
    synthesis: SynthesisResult
    response: AgentQueryResponse


class AgentSupervisor:
    def __init__(
        self,
        settings: Settings | None = None,
        planner: Planner | None = None,
        sql_worker: SqlWorker | None = None,
        cypher_worker: CypherWorker | None = None,
        vector_worker: VectorWorker | None = None,
        sufficiency: SufficiencyChecker | None = None,
        synthesizer: EvidenceFirstSynthesizer | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        catalog = SemanticCatalog()
        self.planner = planner or Planner(catalog=catalog, settings=self.settings)
        self.sql_worker = sql_worker or SqlWorker(
            catalog=catalog,
            settings=self.settings,
        )
        self.cypher_worker = cypher_worker or CypherWorker(
            catalog=catalog,
            settings=self.settings,
        )
        self.vector_worker = vector_worker or VectorWorker(self.settings)
        self.sufficiency = sufficiency or SufficiencyChecker.with_default_model(
            self.settings,
        )
        self.synthesizer = (
            synthesizer or EvidenceFirstSynthesizer.with_default_model(self.settings)
        )
        self.graph = self._compile_graph()

    def run(self, question: str) -> AgentQueryResponse:
        state = self.graph.invoke(
            {
                "question": question,
                "iteration": 0,
                "feedback": None,
                "worker_results": [],
                "sufficiency_decisions": [],
            },
            config={"recursion_limit": self._recursion_limit()},
        )
        return state["response"]

    def _compile_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("plan", self._plan_node)
        graph.add_node("terminal_decision", self._terminal_decision_node)
        graph.add_node("dispatch", self._dispatch_node)
        graph.add_node("sufficiency", self._sufficiency_node)
        graph.add_node("synthesize", self._synthesize_node)
        graph.add_node("assemble", self._assemble_node)

        graph.add_edge(START, "plan")
        graph.add_conditional_edges(
            "plan",
            self._after_plan,
            {
                "terminal": "terminal_decision",
                "dispatch": "dispatch",
            },
        )
        graph.add_edge("terminal_decision", "synthesize")
        graph.add_edge("dispatch", "sufficiency")
        graph.add_conditional_edges(
            "sufficiency",
            self._after_sufficiency,
            {
                "replan": "plan",
                "synthesize": "synthesize",
            },
        )
        graph.add_edge("synthesize", "assemble")
        graph.add_edge("assemble", END)
        return graph.compile()

    def _plan_node(self, state: AgentState) -> AgentState:
        return {
            "plan": self.planner.plan(
                state["question"],
                feedback=state.get("feedback"),
            )
        }

    def _terminal_decision_node(self, state: AgentState) -> AgentState:
        decision = self._terminal_decision(state["plan"])
        if decision is None:
            raise ValueError("terminal_decision_node reached without terminal plan")
        return {"sufficiency_decisions": [decision], "worker_results": []}

    def _dispatch_node(self, state: AgentState) -> AgentState:
        return {"worker_results": self._dispatch(state["plan"])}

    def _sufficiency_node(self, state: AgentState) -> AgentState:
        bundle = EvidenceBundle(
            question=state["question"],
            plan=state["plan"],
            worker_results=state.get("worker_results", []),
        )
        iteration = state.get("iteration", 0)
        decision = self.sufficiency.check(
            bundle,
            iteration=iteration,
            max_replans=self.settings.max_supervisor_replans,
        )
        update: AgentState = {"sufficiency_decisions": [decision]}
        if decision.action == "replan":
            update["feedback"] = decision.reason + ": " + "; ".join(
                decision.missing_evidence
            )
            update["iteration"] = iteration + 1
        return update

    def _synthesize_node(self, state: AgentState) -> AgentState:
        bundle = EvidenceBundle(
            question=state["question"],
            plan=state["plan"],
            worker_results=state.get("worker_results", []),
            sufficiency_decisions=state.get("sufficiency_decisions", []),
        )
        decision = bundle.sufficiency_decisions[-1]
        return {"synthesis": self.synthesizer.synthesize(bundle, decision)}

    def _assemble_node(self, state: AgentState) -> AgentState:
        bundle = EvidenceBundle(
            question=state["question"],
            plan=state["plan"],
            worker_results=state.get("worker_results", []),
            sufficiency_decisions=state.get("sufficiency_decisions", []),
        )
        synthesis = state["synthesis"]
        trace = build_answer_trace(bundle)
        trace.citations = synthesis.citations
        return {
            "response": AgentQueryResponse(
                outcome=synthesis.outcome,
                answer=synthesis.answer,
                clarification=synthesis.clarification,
                abstention=synthesis.abstention,
                refusal=synthesis.refusal,
                answer_trace=trace,
            )
        }

    def _after_plan(self, state: AgentState) -> str:
        return "terminal" if self._terminal_decision(state["plan"]) else "dispatch"

    def _after_sufficiency(self, state: AgentState) -> str:
        decision = state["sufficiency_decisions"][-1]
        return "replan" if decision.action == "replan" else "synthesize"

    def _dispatch(self, plan: ExecutionPlan) -> list[WorkerResult]:
        results: list[WorkerResult] = []
        for task in plan.tasks:
            results.append(self._dispatch_task(task, results))
        return results

    def _dispatch_task(
        self,
        task: ExecutionTask,
        prior_results: list[WorkerResult],
    ) -> WorkerResult:
        if task.target_store == StoreTarget.SQL:
            return self.sql_worker.run(
                task.task_id,
                _augment_sub_question(task, prior_results),
            )
        if task.target_store == StoreTarget.CYPHER:
            return self.cypher_worker.run(
                task.task_id,
                _augment_sub_question(task, prior_results),
            )
        if task.target_store == StoreTarget.VECTOR:
            return self.vector_worker.run(
                task.task_id,
                task.sub_question,
                prior_results=prior_results,
                top_k=task.top_k,
            )
        raise ValueError(f"unsupported target store: {task.target_store}")

    def _terminal_decision(self, plan: ExecutionPlan) -> SufficiencyDecision | None:
        if plan.terminal_action == "clarify":
            return SufficiencyDecision(
                action="clarify",
                reason=plan.terminal_reason or "question_requires_clarification",
                clarification_question=plan.clarification_question,
            )
        if plan.terminal_action == "refuse":
            return SufficiencyDecision(
                action="refuse",
                reason=plan.terminal_reason or "question_out_of_domain",
            )
        return None

    def _recursion_limit(self) -> int:
        return (self.settings.max_supervisor_replans + 1) * 6 + 4


_MAX_UPSTREAM_ROWS = 25


def _augment_sub_question(
    task: ExecutionTask,
    prior_results: list[WorkerResult],
) -> str:
    """Ground a dependent sub-task with the concrete values it depends on."""
    if not task.depends_on:
        return task.sub_question
    blocks: list[str] = []
    for result in prior_results:
        if result.task_id not in task.depends_on or not result.succeeded:
            continue
        rows = result.rows[:_MAX_UPSTREAM_ROWS]
        if not rows:
            continue
        blocks.append(
            f"From sub-task {result.task_id} ({result.target_store}): "
            f"{json.dumps(rows, default=str)}"
        )
    if not blocks:
        return task.sub_question
    return (
        f"{task.sub_question}\n\nConcrete values resolved from prior sub-tasks "
        "(use these exact values to filter; do not re-derive them):\n"
        + "\n".join(blocks)
    )
