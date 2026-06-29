from backend.agent.types import AgentOutcome, AgentQueryResponse
from backend.query.trace import AnswerTrace, QueryRoute
from evaluation.agent.runner import AgentEvalSpec, assert_response_against_spec


def test_eval_assertions_accept_matching_trace():
    spec = AgentEvalSpec(
        id="case",
        question="Top customers?",
        expected_route="sql_only",
        required_trace_fields=["generated_sql"],
    )
    response = AgentQueryResponse(
        outcome=AgentOutcome.ANSWERED,
        answer="SQL ha restituito 1 righe.",
        answer_trace=AnswerTrace(
            route=QueryRoute.SQL_ONLY,
            generated_sql="select customer_id from erp_core.orders limit 1",
        ),
    )

    assert assert_response_against_spec(response, spec) == []


def test_eval_assertions_report_route_and_missing_field():
    spec = AgentEvalSpec(
        id="case",
        question="Top customers?",
        expected_route="graph_only",
        required_trace_fields=["generated_cypher"],
    )
    response = AgentQueryResponse(
        outcome=AgentOutcome.ANSWERED,
        answer="SQL ha restituito 1 righe.",
        answer_trace=AnswerTrace(route=QueryRoute.SQL_ONLY),
    )

    errors = assert_response_against_spec(response, spec)

    assert "route:sql_only!=graph_only" in errors
    assert "missing_trace_field:generated_cypher" in errors

