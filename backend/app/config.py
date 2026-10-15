from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPECTRACE_", env_file=".env", extra="ignore")

    database_url: str | None = None
    cors_origins: list[str] = ["http://localhost:3000"]
    max_request_bytes: int = 12_000_000

    @field_validator("database_url")
    @classmethod
    def _use_psycopg3_driver(cls, url: str | None) -> str | None:
        # Supabase hands out postgresql:// URLs; SQLAlchemy would then look for psycopg2.
        if url:
            for plain in ("postgresql://", "postgres://"):
                if url.startswith(plain):
                    return "postgresql+psycopg://" + url[len(plain) :]
        return url or None
