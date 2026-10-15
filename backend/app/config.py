from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPECTRACE_", env_file=".env", extra="ignore")

    database_url: str | None = None
    cors_origins: list[str] = ["http://localhost:3000"]
    max_request_bytes: int = 12_000_000
