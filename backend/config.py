from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_db_host: str = "db.<project-ref>.supabase.co"
    supabase_db_port: int = 5432
    supabase_db_name: str = "postgres"
    supabase_db_user: str = "postgres"
    supabase_db_password: str = "__set_me__"
    supabase_url: str = "https://<project-ref>.supabase.co"
    supabase_anon_key: str = "__set_me__"

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "__set_me__"

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""

    openrouter_api_key: str = ""
    huggingface_api_token: str = ""
    ollama_base_url: str = Field(default="http://localhost:11434")

    @property
    def postgres_dsn(self) -> str:
        return (
            f"host={self.supabase_db_host} "
            f"port={self.supabase_db_port} "
            f"dbname={self.supabase_db_name} "
            f"user={self.supabase_db_user} "
            f"password={self.supabase_db_password}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()

