import hashlib
import logging
import threading
import uuid
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    Uuid,
    create_engine,
    inspect,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import UserDefinedType

from app.core.chunking import Chunk
from app.core.retrieval import cosine

_JSON = JSON().with_variant(JSONB(), "postgresql")
log = logging.getLogger("spectrace")


class _PgVector(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "vector"


class Vector(TypeDecorator):
    """A pgvector column on Postgres and a JSON list everywhere else (SQLite in tests)."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(_PgVector() if dialect.name == "postgresql" else JSON())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return "[" + ",".join(repr(float(x)) for x in value) + "]"
        return [float(x) for x in value]

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            return [float(x) for x in value.strip("[]").split(",") if x.strip()]
        return [float(x) for x in value]


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
    # SHA-256 of the browser's random owner token. A run is visible only to its owner.
    owner_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class ChunkRow(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[str] = mapped_column(String(1))
    key: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(Text)
    file: Mapped[str] = mapped_column(Text)
    line_start: Mapped[int] = mapped_column(Integer)
    line_end: Mapped[int] = mapped_column(Integer)
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(String(64))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(200), nullable=True)


def owner_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


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
    """Create missing tables. On Postgres the schema comes from the migrations in supabase/."""
    for table in Base.metadata.sorted_tables:
        try:
            table.create(engine, checkfirst=True)
        except Exception as exc:  # a missing pgvector extension, for example
            log.warning("could not create table %s (%s)", table.name, type(exc).__name__)


class RunStore:
    def __init__(self, engine: Engine):
        self._engine = engine
        self._sessions = sessionmaker(engine, expire_on_commit=False)
        # The in-memory SQLite engine shares one connection between all worker threads, so a read
        # could end the transaction of a concurrent write. A lock keeps one operation at a time.
        # Postgres has a real connection pool and needs no lock.
        self._lock = threading.RLock() if engine.dialect.name == "sqlite" else nullcontext()

    @property
    def dialect(self) -> str:
        return self._engine.dialect.name

    def has_chunk_table(self) -> bool:
        with self._lock:
            return inspect(self._engine).has_table("chunks")

    def create(
        self,
        label_a: str,
        label_b: str,
        files_a: dict[str, str],
        files_b: dict[str, str],
        owner: str | None = None,
    ) -> RunRow:
        row = RunRow(
            id=str(uuid.uuid4()),
            status="running",
            label_a=label_a,
            label_b=label_b,
            created_at=datetime.now(UTC),
            files_a=files_a,
            files_b=files_b,
            owner_hash=owner,
        )
        with self._lock, self._sessions.begin() as s:
            s.add(row)
        return row

    def finish(self, run_id: str, result: dict[str, Any]) -> None:
        with self._lock, self._sessions.begin() as s:
            row = s.get(RunRow, run_id)
            row.status, row.result, row.finished_at = "done", result, datetime.now(UTC)

    def set_narrative(self, run_id: str, narrative: dict[str, Any]) -> None:
        with self._lock, self._sessions.begin() as s:
            row = s.get(RunRow, run_id)
            # A new dict, so the change is detected and saved.
            row.result = {**(row.result or {}), "narrative": narrative}

    def fail(self, run_id: str, error_code: str) -> None:
        with self._lock, self._sessions.begin() as s:
            row = s.get(RunRow, run_id)
            row.status, row.error_code, row.finished_at = "failed", error_code, datetime.now(UTC)

    def get(self, run_id: str, owner: str | None = None) -> RunRow | None:
        """The run, or None when it does not exist or belongs to someone else."""
        try:
            run_id = str(uuid.UUID(run_id))
        except ValueError:
            return None
        with self._lock, self._sessions() as s:
            row = s.get(RunRow, run_id)
        if row is None or (owner is not None and row.owner_hash != owner):
            return None
        return row

    def delete(self, run_id: str) -> None:
        with self._lock, self._sessions.begin() as s:
            s.query(ChunkRow).filter(ChunkRow.run_id == run_id).delete()
            row = s.get(RunRow, run_id)
            if row is not None:
                s.delete(row)

    def list(self, limit: int = 50, owner: str | None = None) -> list[RunRow]:
        with self._lock, self._sessions() as s:
            q = select(RunRow).order_by(RunRow.created_at.desc()).limit(limit)
            if owner is not None:
                q = q.where(RunRow.owner_hash == owner)
            return list(s.scalars(q))


@dataclass(frozen=True)
class StoredChunk:
    id: int
    chunk: Chunk
    embedding: list[float] | None
    model: str | None


def _to_chunk(row: ChunkRow) -> Chunk:
    return Chunk(
        key=row.key,
        version=row.version,
        kind=row.kind,
        name=row.name,
        file=row.file,
        line_start=row.line_start,
        line_end=row.line_end,
        ordinal=row.ordinal,
        text=row.text,
    )


class ChunkStore:
    """Chunks and their embeddings for one run. On Postgres the vectors live in pgvector."""

    def __init__(self, runs: RunStore):
        self._runs = runs
        self._sessions = runs._sessions
        self._lock = runs._lock

    def replace(
        self,
        run_id: str,
        chunks: list[Chunk],
        vectors: dict[str, list[float]] | None = None,
        model: str | None = None,
    ) -> None:
        vectors = vectors or {}
        with self._lock, self._sessions.begin() as s:
            s.query(ChunkRow).filter(ChunkRow.run_id == run_id).delete()
            s.add_all(
                ChunkRow(
                    run_id=run_id,
                    version=c.version,
                    key=c.key,
                    kind=c.kind,
                    name=c.name,
                    file=c.file,
                    line_start=c.line_start,
                    line_end=c.line_end,
                    ordinal=c.ordinal,
                    text=c.text,
                    text_hash=c.text_hash,
                    embedding=vectors.get(c.text_hash),
                    embedding_model=model if c.text_hash in vectors else None,
                )
                for c in chunks
            )

    def load(self, run_id: str) -> list[StoredChunk]:
        with self._lock, self._sessions() as s:
            rows = s.scalars(
                select(ChunkRow)
                .where(ChunkRow.run_id == run_id)
                .order_by(ChunkRow.version, ChunkRow.key, ChunkRow.ordinal)
            ).all()
        return [StoredChunk(r.id, _to_chunk(r), r.embedding, r.embedding_model) for r in rows]

    def similar(
        self, run_id: str, query: list[float], model: str, k: int = 20
    ) -> list[tuple[int, float]]:
        """(chunk id, cosine similarity), best first, among chunks embedded by this model."""
        if self._runs.dialect == "postgresql":
            literal = "[" + ",".join(repr(float(x)) for x in query) + "]"
            sql = text(
                "SELECT id, 1 - (embedding <=> CAST(:q AS vector)) AS sim FROM chunks "
                "WHERE run_id = CAST(:run AS uuid) AND embedding IS NOT NULL "
                "AND embedding_model = :model ORDER BY embedding <=> CAST(:q AS vector) LIMIT :k"
            )
            with self._sessions() as s:
                rows = s.execute(sql, {"q": literal, "run": run_id, "model": model, "k": k}).all()
            return [(int(r[0]), float(r[1])) for r in rows]
        scored = [
            (c.id, cosine(query, c.embedding))
            for c in self.load(run_id)
            if c.embedding is not None and c.model == model
        ]
        return sorted(scored, key=lambda pair: -pair[1])[:k]
