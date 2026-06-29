from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from backend.agent.graph import AgentSupervisor
from backend.agent.llm import LLMConfigurationError, LLMProviderError
from backend.agent.types import AgentQueryRequest, AgentQueryResponse
from backend.config import Settings, get_settings

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/query", response_model=AgentQueryResponse)
def query_agent(
    request: AgentQueryRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgentQueryResponse:
    try:
        return AgentSupervisor(settings=settings).run(request.question)
    except (LLMConfigurationError, LLMProviderError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
