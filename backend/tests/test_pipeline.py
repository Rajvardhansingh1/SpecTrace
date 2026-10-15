import pytest

from app.core.limits import Limits
from app.core.pipeline import analyze, answer_question
from app.errors import InputTooLarge, LimitExceeded, UnsupportedInput


def test_analyze_petstore(v1, v2):
    result = analyze(v1, v2)
    assert [c.key for c in result.changes] == ["schema:Pet"]
    assert len(result.impacts["schema:Pet"]) == 7
    assert result.stats["files_a"] == 2 and result.stats["changes"] == 1
    assert result.stats["elapsed_ms"] >= 0


def test_unsupported_files_are_reported_not_parsed(v1, v2):
    extra = {"logo.png": "binary", "notes.yaml": "name: not openapi\n"}
    result = analyze({**v1, **extra}, {**v2, **extra})
    assert any("logo.png" in u for u in result.unsupported)
    assert any("notes.yaml" in u for u in result.unsupported)


@pytest.mark.parametrize("name", ["../evil.md", "/etc/passwd.md", "C:/x.md", "a/../../b.md"])
def test_unsafe_paths_are_rejected(name):
    with pytest.raises(UnsupportedInput):
        analyze({name: "# x\n"}, {})


def test_file_size_limit():
    with pytest.raises(InputTooLarge):
        analyze({"a.md": "x" * 11}, {}, Limits(max_file_bytes=10))


def test_file_count_limit():
    files = {f"{i}.md": "# x\n" for i in range(3)}
    with pytest.raises(LimitExceeded):
        analyze(files, {}, Limits(max_files=2))


def test_question_answered_with_impacts(v1, v2):
    ans = answer_question(analyze(v1, v2), "What is impacted by the Pet change?")
    assert ans.status == "answered"
    assert ans.matched == ["schema:Pet"]
    assert len(ans.impacts) == 7


def test_question_about_unchanged_entity(v1, v2):
    ans = answer_question(analyze(v1, v2), "What about Owner?")
    assert ans.status == "no_change"
    assert ans.impacts == []


def test_unknown_subject_is_uncertain_not_fabricated(v1, v2):
    ans = answer_question(analyze(v1, v2), "How does billing break?")
    assert ans.status == "uncertain"
    assert ans.impacts == [] and ans.reason
