from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from backend.config import Settings, get_settings
from backend.ladder.top_customers import TopCustomersResponse, answer_top_customers

router = APIRouter(prefix="/ladder", tags=["ladder"])


@router.get("/top-customers", response_model=TopCustomersResponse)
def top_customers(
    settings: Annotated[Settings, Depends(get_settings)],
) -> TopCustomersResponse:
    return answer_top_customers(settings=settings)

