import json
from typing import Annotated, Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPECTRACE_", env_file=".env", extra="ignore")

    database_url: str | None = None
    # A JSON list or a comma-separated string; hosting dashboards often get either.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    max_request_bytes: int = 12_000_000
    rate_limit_per_minute: int = 120
    rate_limit_heavy_per_minute: int = 10
    # Only enable behind a proxy you control (Render): the client IP is then read from the
    # last X-Forwarded-For entry, which that proxy appended. Otherwise clients could spoof it.
    trust_proxy_headers: bool = False

    # ---- language model (optional; everything works without it) ----
    # "openrouter" and "groq" set the base URL; "openai_compatible" needs llm_base_url.
    # "test" is a deterministic stand-in for tests and demos and must not be used in production.
    llm_provider: Literal["none", "openrouter", "groq", "openai_compatible", "test"] = "none"
    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = None
    llm_model: str | None = None
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 2
    # Models that think before answering spend part of this limit on the thinking.
    llm_max_output_tokens: int = 3000
    # Characters of document text placed in one prompt.
    llm_context_chars: int = 24_000
    # Cost guards: calls per owner per hour and per process per day.
    llm_calls_per_owner_per_hour: int = 30
    llm_calls_per_day: int = 1000

    # ---- embeddings (optional; without them retrieval is keyword and graph based) ----
    embedding_provider: Literal[
        "none", "openrouter", "jina", "openai_compatible", "hashing", "fastembed"
    ] = "none"
    embedding_base_url: str | None = None
    embedding_api_key: SecretStr | None = None
    embedding_model: str | None = None
    embedding_batch_size: int = 64
    embedding_max_chunks_per_run: int = 2000

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_origins(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        text = value.strip()
        if text.startswith("["):
            try:
                return json.loads(text)
            except ValueError:
                text = text.strip("[]")
        # Strip quotes and a trailing slash: browsers send origins without one.
        items = [part.strip().strip("\"'").rstrip("/") for part in text.split(",")]
        return [item for item in items if item] or ["http://localhost:3000"]

    @field_validator("llm_base_url", "embedding_base_url")
    @classmethod
    def _no_trailing_slash(cls, url: str | None) -> str | None:
        return url.rstrip("/") if url else None

    @field_validator("database_url")
    @classmethod
    def _use_psycopg3_driver(cls, url: str | None) -> str | None:
        # Supabase hands out postgresql:// URLs; SQLAlchemy would then look for psycopg2.
        if url:
            for plain in ("postgresql://", "postgres://"):
                if url.startswith(plain):
                    return "postgresql+psycopg://" + url[len(plain) :]
        return url or None
