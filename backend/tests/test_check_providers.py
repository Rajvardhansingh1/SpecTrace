import httpx

from app.adapters.llm import AI, HashingEmbedder, OpenAICompatChat, TestChat
from app.errors import LLMUnavailable
from scripts import check_providers


def test_nothing_configured_is_reported_and_is_a_failure(capsys):
    assert check_providers.check(AI(None, None, "none", "none", [])) == 1
    assert "No provider is configured" in capsys.readouterr().out


def test_working_local_providers_pass_and_say_nothing_leaves_the_server(capsys):
    assert check_providers.check(AI(TestChat(), HashingEmbedder(64), "test", "hashing", [])) == 0
    out = capsys.readouterr().out
    assert "chat       ok" in out and "dimensions=64" in out
    assert "Nothing would be sent to a third party." in out


def test_a_rejected_key_is_a_failure_that_shows_the_code_but_never_the_key(capsys):
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(401, text="SECRET-BODY"))
    )
    chat = OpenAICompatChat("https://x.test/v1", "SECRET-KEY-1", "m", retries=0, client=client)
    assert check_providers.check(AI(chat, None, "groq", "none", ["Groq"])) == 2
    out = capsys.readouterr().out
    assert "chat       FAIL" in out and "llm_unavailable" in out
    assert "SECRET" not in out and "Document text would be sent to: Groq" in out


def test_a_setup_error_is_reported_cleanly(monkeypatch, capsys):
    def broken(_settings):
        raise LLMUnavailable("The language model needs a base URL and a model name.")

    monkeypatch.setattr(check_providers, "build_ai", broken)
    assert check_providers.main() == 2
    assert "setup FAIL  llm_unavailable" in capsys.readouterr().out
