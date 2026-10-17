"""Splits parsed entities into chunks for retrieval.

The entities already follow the structure of the documents (a section, a requirement, an endpoint,
a schema, an example), so chunks respect those boundaries instead of cutting by a fixed window.
Only an entity longer than the limit is split, and then at line boundaries.
"""

import hashlib
from dataclasses import dataclass

from app.core.models import Entity, EntityKind

DEFAULT_MAX_CHARS = 1_200


@dataclass(frozen=True)
class Chunk:
    key: str
    version: str  # "a" or "b"
    kind: str
    name: str
    file: str
    line_start: int
    line_end: int
    ordinal: int
    text: str

    @property
    def text_hash(self) -> str:
        return hashlib.sha256(self.embed_text.encode()).hexdigest()

    @property
    def embed_text(self) -> str:
        """What is embedded: the text with its name and kind, so a snippet keeps its context."""
        return f"{self.name} ({self.kind})\n{self.text}"


def chunk_entities(
    entities: dict[str, Entity], version: str, max_chars: int = DEFAULT_MAX_CHARS
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for key in sorted(entities):
        entity = entities[key]
        if not entity.text.strip():
            continue
        exact_lines = entity.kind is not EntityKind.SECTION
        for ordinal, (text, first, last) in enumerate(_split(entity, max_chars, exact_lines)):
            chunks.append(
                Chunk(
                    key=entity.key,
                    version=version,
                    kind=entity.kind.value,
                    name=entity.name,
                    file=entity.location.file,
                    line_start=first,
                    line_end=last,
                    ordinal=ordinal,
                    text=text,
                )
            )
    return chunks


def _split(entity: Entity, max_chars: int, exact_lines: bool) -> list[tuple[str, int, int]]:
    """Pieces of the entity text with the lines they came from.

    A section's text leaves out its requirement and example lines, so its pieces cannot be mapped
    to exact lines; they all cite the whole section range instead.
    """
    base = entity.location.line_start
    groups: list[tuple[list[str], int, int]] = []  # (lines, first index, last index)
    buffer: list[str] = []
    size = start = last = 0
    for index, line in enumerate(entity.text.splitlines()):
        # A single very long line is cut so that no piece exceeds the limit.
        for part in [line[i : i + max_chars] for i in range(0, len(line), max_chars)] or [""]:
            if buffer and size + len(part) + 1 > max_chars:
                groups.append((buffer, start, last))
                buffer, size = [], 0
            if not buffer:
                start = index
            buffer.append(part)
            size += len(part) + 1
            last = index
    if buffer:
        groups.append((buffer, start, last))

    pieces = []
    for lines, first, end in groups:
        text = "\n".join(lines)
        if not text.strip():
            continue
        if exact_lines:
            pieces.append((text, base + first, base + end))
        else:
            pieces.append((text, entity.location.line_start, entity.location.line_end))
    return pieces
