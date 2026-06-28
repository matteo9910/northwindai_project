from __future__ import annotations

from qdrant_client import QdrantClient

from backend.config import Settings, get_settings


def qdrant_client(settings: Settings | None = None) -> QdrantClient:
    settings = settings or get_settings()
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        timeout=30,
        check_compatibility=False,
    )
