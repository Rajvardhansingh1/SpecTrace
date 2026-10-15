from pathlib import Path

import pytest

SAMPLES = Path(__file__).resolve().parents[2] / "samples" / "petstore"


def load_version(version: str) -> dict[str, str]:
    root = SAMPLES / version
    return {
        p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@pytest.fixture
def v1() -> dict[str, str]:
    return load_version("v1")


@pytest.fixture
def v2() -> dict[str, str]:
    return load_version("v2")
