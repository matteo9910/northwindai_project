from __future__ import annotations

from fastapi.testclient import TestClient

from backend.agent.sufficiency import SufficiencyChecker
from backend.agent.synthesis import EvidenceFirstSynthesizer
from backend.agent.types import (
    AgentOutcome,
    ExecutionPlan,
    ExecutionTask,
    StoreTarget,
    WorkerResult,
    WorkerStatus,
)
from backend.config import Settings
from backend.main import app
from backend.query.executor import QueryMetrics
from backend.query.trace import QueryRoute


class FakePlanner:
    def __init__(self, plan: ExecutionPlan):
        self.execution_plan = plan
        self.calls = 0

    def plan(self, question: str, feedback: str | None = None) -> ExecutionPlan:
        self.calls += 1
        return self.execution_plan


class FakeSqlWorker:
    def run(self, task_id: str, sub_question: str) -> WorkerResult:
        return WorkerResult(
            task_id=task_id,
            target_store=StoreTarget.SQL,
            status=WorkerStatus.SUCCESS,
            sub_question=sub_question,
            rows=[{"customer_id": "ALFKI", "net_revenue": "100.00"}],
            metrics={"postgresql": QueryMetrics(row_count=1, duration_ms=1.0)},
        )


def test_supervisor_dispatches_plan_and_builds_trace():
    from backend.agent.graph import AgentSupervisor

    supervisor = AgentSupervisor(
        settings=Settings(),
        planner=FakePlanner(
            ExecutionPlan(
                route=QueryRoute.SQL_ONLY,
                tasks=[
                    ExecutionTask(
                        task_id="sql_1",
                        target_store=StoreTarget.SQL,
                        sub_question="Top customers",
                    )
                ],
            )
        ),
        sql_worker=FakeSqlWorker(),
        sufficiency=SufficiencyChecker(),
        synthesizer=EvidenceFirstSynthesizer(),
    )

    response = supervisor.run("Who are the top customers?")

    assert response.outcome == AgentOutcome.ANSWERED
    assert response.answer_trace.route == QueryRoute.SQL_ONLY
    assert response.answer_trace.execution_plan["tasks"][0]["task_id"] == "sql_1"
    assert response.answer_trace.worker_results[0]["status"] == "success"
    assert response.answer_trace.sufficiency_decisions[0]["action"] == "answer"


def test_sufficiency_checker_enforces_replan_cap():
    plan = ExecutionPlan(
        route=QueryRoute.SQL_ONLY,
        tasks=[
            ExecutionTask(
                task_id="sql_1",
                target_store=StoreTarget.SQL,
                sub_question="No evidence",
            )
        ],
    )
    bundle = _bundle(plan)
    checker = SufficiencyChecker()

    first = checker.check(bundle, iteration=0, max_replans=1)
    capped = checker.check(bundle, iteration=1, max_replans=1)

    assert first.action == "replan"
    assert capped.action == "abstain"


def test_agent_endpoint_uses_supervisor(monkeypatch):
    class FakeSupervisor:
        def __init__(self, settings):
            pass

        def run(self, question: str):
            from backend.agent.types import AgentQueryResponse
            from backend.query.trace import AnswerTrace

            return AgentQueryResponse(
                outcome=AgentOutcome.ANSWERED,
                answer=f"answered: {question}",
                answer_trace=AnswerTrace(route=QueryRoute.SQL_ONLY),
            )

    monkeypatch.setattr("backend.agent.router.AgentSupervisor", FakeSupervisor)

    response = TestClient(app).post(
        "/agent/query",
        json={"question": "Top customers?"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "answered: Top customers?"


def test_agent_endpoint_reports_missing_llm_configuration(monkeypatch):
    from backend.agent.llm import LLMConfigurationError

    class FakeSupervisor:
        def __init__(self, settings):
            pass

        def run(self, question: str):
            raise LLMConfigurationError("OPENROUTER_API_KEY is not configured")

    monkeypatch.setattr("backend.agent.router.AgentSupervisor", FakeSupervisor)

    response = TestClient(app).post(
        "/agent/query",
        json={"question": "Top customers?"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "OPENROUTER_API_KEY is not configured"


def test_agent_endpoint_reports_provider_error(monkeypatch):
    from backend.agent.llm import LLMProviderError

    class FakeSupervisor:
        def __init__(self, settings):
            pass

        def run(self, question: str):
            raise LLMProviderError("OpenRouter request failed with HTTP 402")

    monkeypatch.setattr("backend.agent.router.AgentSupervisor", FakeSupervisor)

    response = TestClient(app).post(
        "/agent/query",
        json={"question": "Top customers?"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "OpenRouter request failed with HTTP 402"


def _bundle(plan: ExecutionPlan):
    from backend.agent.types import EvidenceBundle

    return EvidenceBundle(
        question="No evidence",
        plan=plan,
        worker_results=[
            WorkerResult(
                task_id="sql_1",
                target_store=StoreTarget.SQL,
                status=WorkerStatus.SUCCESS,
                sub_question="No evidence",
            )
        ],
    )
