from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.config import Settings, get_settings
from backend.health import checks
from backend.health.checks import ServiceHealth

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    services: dict[str, ServiceHealth]


@router.get("/health", response_model=HealthResponse)
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    services = {
        "postgres": checks.check_postgres(settings),
        "neo4j": checks.check_neo4j(settings),
        "qdrant": checks.check_qdrant(settings),
    }
    status = (
        "ok" if all(service.available for service in services.values()) else "degraded"
    )
    return HealthResponse(status=status, services=services)
