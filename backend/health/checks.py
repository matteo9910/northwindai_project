from collections.abc import Callable

import psycopg
from neo4j import GraphDatabase
from pydantic import BaseModel
from qdrant_client import QdrantClient

from backend.config import Settings


class ServiceHealth(BaseModel):
    available: bool
    detail: str


def _is_placeholder(value: str) -> bool:
    return not value or "__set_me__" in value or "<project-ref>" in value


def check_postgres(settings: Settings) -> ServiceHealth:
    if _is_placeholder(settings.supabase_db_host) or _is_placeholder(
        settings.supabase_db_password
    ):
        return ServiceHealth(
            available=False,
            detail="Supabase connection is not configured",
        )

    try:
        with psycopg.connect(settings.postgres_dsn, connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
    except Exception as exc:
        return ServiceHealth(available=False, detail=f"PostgreSQL unavailable: {exc}")

    return ServiceHealth(available=True, detail="northwindai reachable")


def check_neo4j(settings: Settings) -> ServiceHealth:
    if _is_placeholder(settings.neo4j_password):
        return ServiceHealth(
            available=False,
            detail="Neo4j password is not configured",
        )

    try:
        with GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            connection_timeout=3,
        ) as driver:
            driver.verify_connectivity()
            with driver.session() as session:
                session.run("RETURN 1").consume()
    except Exception as exc:
        return ServiceHealth(available=False, detail=f"Neo4j unavailable: {exc}")

    return ServiceHealth(available=True, detail="bolt ok")


def check_qdrant(settings: Settings) -> ServiceHealth:
    try:
        client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
            timeout=3,
        )
        client.get_collections()
    except Exception as exc:
        return ServiceHealth(available=False, detail=f"Qdrant unavailable: {exc}")

    return ServiceHealth(available=True, detail="6333 ok")


HealthCheck = Callable[[Settings], ServiceHealth]

