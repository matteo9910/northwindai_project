from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from neo4j import Driver, GraphDatabase

from backend.config import Settings, get_settings


@contextmanager
def neo4j_driver(settings: Settings | None = None) -> Iterator[Driver]:
    settings = settings or get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        yield driver
    finally:
        driver.close()

