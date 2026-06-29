from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from backend.agent.graph import AgentSupervisor
from backend.agent.llm import (
    build_chat_model,
    build_structured_chat_model,
    invoke_structured,
)
from backend.agent.types import AgentQueryResponse, AgentRole, JudgeVerdict
from backend.config import get_settings

SUITE_DIR = Path("evaluation/agent/suite")
TRACE_OUTPUT_DIR = Path("evaluation/agent/answer_traces")
RESULTS_PATH = Path("evaluation/agent/results.json")


class AgentEvalSpec(BaseModel):
    id: str
    question: str
    expected_outcome: str = "answered"
    expected_route: str
    required_validation_dialects: list[str] = Field(default_factory=list)
    required_trace_fields: list[str] = Field(default_factory=list)
    forbidden_terms: list[str] = Field(default_factory=list)
    judge_prose: bool = False


class AgentEvalResult(BaseModel):
    id: str
    passed: bool
    deterministic_errors: list[str] = Field(default_factory=list)
    judge_verdict: dict[str, Any] | None = None
    trace_path: str | None = None


def load_specs(suite_dir: Path = SUITE_DIR) -> list[AgentEvalSpec]:
    return [
        AgentEvalSpec.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(suite_dir.glob("*.spec.json"))
    ]


def run_suite(
    suite_dir: Path = SUITE_DIR,
    trace_output_dir: Path = TRACE_OUTPUT_DIR,
    results_path: Path = RESULTS_PATH,
) -> list[AgentEvalResult]:
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required to run live agent evals")
    supervisor = AgentSupervisor(settings=settings)
    trace_output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for spec in load_specs(suite_dir):
        response = supervisor.run(spec.question)
        trace_path = trace_output_dir / f"{spec.id}.json"
        trace_path.write_text(
            json.dumps(response.answer_trace.model_dump(mode="json"), indent=2)
            + "\n",
            encoding="utf-8",
        )
        errors = assert_response_against_spec(response, spec)
        judge_verdict = judge_answer(response, spec) if spec.judge_prose else None
        if judge_verdict and not judge_verdict.get("passed", False):
            errors.append("llm_judge_failed")
        results.append(
            AgentEvalResult(
                id=spec.id,
                passed=not errors,
                deterministic_errors=errors,
                judge_verdict=judge_verdict,
                trace_path=str(trace_path),
            )
        )
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(
        json.dumps([result.model_dump(mode="json") for result in results], indent=2)
        + "\n",
        encoding="utf-8",
    )
    return results


def assert_response_against_spec(
    response: AgentQueryResponse,
    spec: AgentEvalSpec,
) -> list[str]:
    errors = []
    trace = response.answer_trace
    if response.outcome != spec.expected_outcome:
        errors.append(
            f"outcome:{response.outcome}!={spec.expected_outcome}"
        )
    if trace.route != spec.expected_route:
        errors.append(f"route:{trace.route}!={spec.expected_route}")
    for field in spec.required_trace_fields:
        value = getattr(trace, field)
        if not value:
            errors.append(f"missing_trace_field:{field}")
    dialects = {
        validation.dialect
        for validation in trace.validation_results
        if getattr(validation, "allowed", False)
    }
    for dialect in spec.required_validation_dialects:
        if dialect not in dialects:
            errors.append(f"missing_allowed_validation:{dialect}")
    answer_text = " ".join(
        part
        for part in [
            response.answer,
            response.abstention,
            response.clarification,
            response.refusal,
        ]
        if part
    ).lower()
    for term in spec.forbidden_terms:
        if term.lower() in answer_text:
            errors.append(f"forbidden_term_present:{term}")
    return errors


def judge_answer(
    response: AgentQueryResponse,
    spec: AgentEvalSpec,
) -> dict[str, Any] | None:
    if not os.getenv("OPENROUTER_API_KEY"):
        return {"skipped": True, "reason": "OPENROUTER_API_KEY is unset"}
    model = build_chat_model(AgentRole.JUDGE, get_settings())
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are the NorthwindAI evaluation judge. Grade only the prose: "
                "grounded in trace, correct abstention, certain vs plausible.",
            ),
            (
                "human",
                "Spec:\n{spec}\n\nResponse:\n{response}",
            ),
        ]
    )
    chain = prompt | build_structured_chat_model(model, JudgeVerdict)
    verdict = invoke_structured(
        chain,
        {
            "spec": spec.model_dump_json(indent=2),
            "response": response.model_dump_json(indent=2),
        },
    )
    return verdict.model_dump(mode="json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the NorthwindAI agent eval suite."
    )
    parser.add_argument("--suite-dir", type=Path, default=SUITE_DIR)
    parser.add_argument("--trace-output-dir", type=Path, default=TRACE_OUTPUT_DIR)
    parser.add_argument("--results-path", type=Path, default=RESULTS_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results = run_suite(
        suite_dir=args.suite_dir,
        trace_output_dir=args.trace_output_dir,
        results_path=args.results_path,
    )
    passed = sum(1 for result in results if result.passed)
    print(f"{passed}/{len(results)} agent eval specs passed")
    for result in results:
        if not result.passed:
            print(f"{result.id}: {', '.join(result.deterministic_errors)}")


if __name__ == "__main__":
    main()
