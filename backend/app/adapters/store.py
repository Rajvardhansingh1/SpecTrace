import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, Uuid, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

_JSON = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class RunRow(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    status: Mapped[str] = mapped_column(String(16))
    label_a: Mapped[str] = mapped_column(String(100))
    label_b: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    files_a: Mapped[dict[str, str]] = mapped_column(_JSON)
    files_b: Mapped[dict[str, str]] = mapped_column(_JSON)
    result: Mapped[dict[str, Any] | None] = mapped_column(_JSON, nullable=True)


def make_engine(database_url: str | None) -> Engine:
    if database_url is None:
        # No URL configured: in-memory SQLite on one shared connection. Nothing survives a restart.
        return create_engine(
            "sqlite+pysqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
    return create_engine(database_url, pool_pre_ping=True)


def init_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)


class RunStore:
    def __init__(self, engine: Engine):
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def create(
        self, label_a: str, label_b: str, files_a: dict[str, str], files_b: dict[str, str]
    ) -> RunRow:
        row = RunRow(
            id=str(uuid.uuid4()),
            status="running",
            label_a=label_a,
            label_b=label_b,
            created_at=datetime.now(UTC),
            files_a=files_a,
            files_b=files_b,
        )
        with self._sessions.begin() as s:
            s.add(row)
        return row

    def finish(self, run_id: str, result: dict[str, Any]) -> None:
        with self._sessions.begin() as s:
            row = s.get(RunRow, run_id)
            row.status, row.result, row.finished_at = "done", result, datetime.now(UTC)

    def fail(self, run_id: str, error_code: str) -> None:
        with self._sessions.begin() as s:
            row = s.get(RunRow, run_id)
            row.status, row.error_code, row.finished_at = "failed", error_code, datetime.now(UTC)

    def get(self, run_id: str) -> RunRow | None:
        try:
            run_id = str(uuid.UUID(run_id))
        except ValueError:
            return None
        with self._sessions() as s:
            return s.get(RunRow, run_id)

    def delete(self, run_id: str) -> None:
        with self._sessions.begin() as s:
            row = s.get(RunRow, run_id)
            if row is not None:
                s.delete(row)

    def list(self, limit: int = 50) -> list[RunRow]:
        with self._sessions() as s:
            q = select(RunRow).order_by(RunRow.created_at.desc()).limit(limit)
            return list(s.scalars(q))
