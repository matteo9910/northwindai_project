from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.agent.graph import AgentSupervisor
from backend.agent.llm import LLMConfigurationError, LLMProviderError
from backend.config import get_settings

DEFAULT_TRACE_PATH = Path("evaluation/answer_traces/agent_last_trace.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the NorthwindAI agent.")
    parser.add_argument(
        "-q",
        "--question",
        help="Question to ask. If omitted, starts interactive mode.",
    )
    parser.add_argument("--emit-trace", action="store_true")
    parser.add_argument("--trace-path", type=Path, default=DEFAULT_TRACE_PATH)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full JSON response.",
    )
    return parser.parse_args()


def main() -> None:
    _configure_stdout()
    args = parse_args()
    supervisor = AgentSupervisor(settings=get_settings())
    if args.question:
        _run_question(
            supervisor,
            args.question,
            args.emit_trace,
            args.trace_path,
            args.json,
        )
        return
    print("NorthwindAI agent. Empty input exits.")
    while True:
        question = input("> ").strip()
        if not question:
            break
        _run_question(supervisor, question, args.emit_trace, args.trace_path, args.json)


def _run_question(
    supervisor: AgentSupervisor,
    question: str,
    emit_trace: bool,
    trace_path: Path,
    as_json: bool,
) -> None:
    try:
        response = supervisor.run(question)
    except (LLMConfigurationError, LLMProviderError) as exc:
        print(f"Configuration error: {exc}")
        return
    if emit_trace:
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text(
            json.dumps(response.answer_trace.model_dump(mode="json"), indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"answer_trace written to {trace_path}")
    if as_json:
        print(response.model_dump_json(indent=2))
        return
    print(
        response.answer
        or response.clarification
        or response.abstention
        or response.refusal
    )


def _configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    main()
