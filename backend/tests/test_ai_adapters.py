import json

import httpx
import pytest

from app.adapters.llm import (
    AI,
    HashingEmbedder,
    OpenAICompatChat,
    OpenAICompatEmbedder,
    TestChat,
    build_ai,
)
from app.config import Settings
from app.core.llm import CallBudget, ChatMessage
from app.errors import (
    BudgetExceeded,
    LLMBadOutput,
    LLMRateLimited,
    LLMTimeout,
    LLMUnavailable,
)

MSG = [ChatMessage("system", "s"), ChatMessage("user", "u")]


def client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def ok_chat(text="hi"):
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": text}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
        },
    )


def chat(handler, retries=2, sleeps=None):
    return OpenAICompatChat(
        "https://example.test/v1",
        "SECRET-KEY",
        "m1",
        retries=retries,
        client=client_for(handler),
        sleep=(sleeps.append if sleeps is not None else lambda s: None),
    )


class TestChatAdapter:
    def test_sends_openai_shaped_request_and_returns_text_and_usage(self):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            seen["auth"] = request.headers["authorization"]
            seen["body"] = json.loads(request.content)
            return ok_chat("answer")

        result = chat(handler).complete(MSG, max_tokens=50, temperature=0.2)
        assert (result.text, result.prompt_tokens, result.completion_tokens) == ("answer", 3, 2)
        assert seen["url"] == "https://example.test/v1/chat/completions"
        assert seen["auth"] == "Bearer SECRET-KEY"
        assert seen["body"]["model"] == "m1" and seen["body"]["max_tokens"] == 50
        assert seen["body"]["messages"][1] == {"role": "user", "content": "u"}

    def test_retries_rate_limits_and_server_errors_then_succeeds(self):
        calls = []

        def handler(request):
            calls.append(1)
            if len(calls) == 1:
                return httpx.Response(429, headers={"retry-after": "1"})
            if len(calls) == 2:
                return httpx.Response(503)
            return ok_chat()

        sleeps: list[float] = []
        assert chat(handler, sleeps=sleeps).complete(MSG, max_tokens=5).text == "hi"
        assert len(calls) == 3 and len(sleeps) == 2 and sleeps[0] == 1.0

    def test_retries_are_bounded(self):
        calls = []

        def handler(request):
            calls.append(1)
            return httpx.Response(429)

        with pytest.raises(LLMRateLimited):
            chat(handler, retries=2).complete(MSG, max_tokens=5)
        assert len(calls) == 3

    def test_bad_key_and_bad_request_are_not_retried_and_hide_details(self):
        calls = []

        def unauthorized(request):
            calls.append(1)
            return httpx.Response(401, text="prompt text echoed SECRET-DOC")

        with pytest.raises(LLMUnavailable) as err:
            chat(unauthorized).complete(MSG, max_tokens=5)
        assert len(calls) == 1
        assert "SECRET" not in err.value.message

        with pytest.raises(LLMUnavailable) as err2:
            chat(lambda r: httpx.Response(400, text="SECRET-DOC")).complete(MSG, max_tokens=5)
        assert "HTTP 400" in err2.value.message and "SECRET" not in err2.value.message

    def test_timeout_and_connection_failure_map_to_stable_errors(self):
        def slow(request):
            raise httpx.ReadTimeout("t")

        def down(request):
            raise httpx.ConnectError("c")

        with pytest.raises(LLMTimeout):
            chat(slow, retries=1).complete(MSG, max_tokens=5)
        with pytest.raises(LLMUnavailable):
            chat(down, retries=0).complete(MSG, max_tokens=5)

    @pytest.mark.parametrize(
        "response",
        [
            httpx.Response(200, text="not json"),
            httpx.Response(200, json=[1, 2]),
            httpx.Response(200, json={"choices": []}),
            httpx.Response(200, json={"choices": [{"message": {"content": None}}]}),
            httpx.Response(200, json={"choices": [{"message": {"content": "  "}}]}),
        ],
    )
    def test_malformed_replies_are_bad_output(self, response):
        with pytest.raises(LLMBadOutput):
            chat(lambda r: response).complete(MSG, max_tokens=5)


class TestEmbedderAdapter:
    def make(self, handler, batch=2):
        return OpenAICompatEmbedder(
            "https://example.test/v1",
            "K",
            "emb",
            batch_size=batch,
            retries=0,
            client=client_for(handler),
        )

    def test_batches_and_restores_order(self):
        sizes = []

        def handler(request):
            texts = json.loads(request.content)["input"]
            sizes.append(len(texts))
            # Returned out of order on purpose.
            data = [{"index": i, "embedding": [float(len(t)), 1.0]} for i, t in enumerate(texts)]
            return httpx.Response(200, json={"data": data[::-1]})

        vectors = self.make(handler).embed(["a", "bb", "ccc"])
        assert sizes == [2, 1]
        assert [v[0] for v in vectors] == [1.0, 2.0, 3.0]

    @pytest.mark.parametrize(
        "body",
        [
            {"data": []},
            {"data": [{"index": 0, "embedding": []}]},
            {"data": [{"index": 0, "embedding": [1.0, "x"]}]},
            {"data": [{"index": 0, "embedding": [1e999]}]},
            {"nothing": 1},
        ],
    )
    def test_invalid_vectors_are_rejected(self, body):
        raw = json.dumps(body)
        with pytest.raises(LLMBadOutput):
            self.make(lambda r: httpx.Response(200, content=raw)).embed(["a"])

    def test_inconsistent_sizes_are_rejected(self):
        calls = []

        def handler(request):
            calls.append(1)
            dim = 2 if len(calls) == 1 else 3
            return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1] * dim}]})

        with pytest.raises(LLMBadOutput):
            self.make(handler, batch=1).embed(["a", "b"])


class TestLocalComponents:
    def test_hashing_embedder_is_deterministic_normalized_and_prefers_shared_words(self):
        e = HashingEmbedder(128)
        a, b, c = e.embed(["list all pets", "list all pets quickly", "invoice payment terms"])
        assert e.embed(["list all pets"])[0] == a
        assert abs(sum(x * x for x in a) - 1.0) < 1e-9

        def dot(u, v):
            return sum(x * y for x, y in zip(u, v, strict=True))

        assert dot(a, b) > dot(a, c)
        assert e.embed([""])[0] == [0.0] * 128

    def test_test_chat_cites_context_and_abstains_without_it(self):
        sys_ = ChatMessage("system", "TASK:answer")
        ctx = ChatMessage("user", "[C1] x\n[C2] y\n[C3] z")
        out = json.loads(TestChat().complete([sys_, ctx], max_tokens=9).text)
        assert out["citations"] == ["C1", "C2"] and not out["abstain"]
        bare = ChatMessage("user", "no context")
        none = json.loads(TestChat().complete([sys_, bare], max_tokens=9).text)
        assert none["abstain"] is True
        summary_msgs = [ChatMessage("system", "TASK:summary"), ChatMessage("user", "[C1] x")]
        summary = json.loads(TestChat().complete(summary_msgs, max_tokens=9).text)
        assert summary["citations"] == ["C1"]


class TestFactory:
    def settings(self, **kw):
        return Settings(_env_file=None, **kw)

    def test_everything_off_by_default(self):
        ai = build_ai(self.settings())
        assert isinstance(ai, AI)
        assert ai.chat is None and ai.embedder is None and ai.recipients == []

    def test_presets_set_the_base_url_and_name_the_recipient(self):
        ai = build_ai(self.settings(llm_provider="groq", llm_api_key="k", llm_model="llama"))
        assert ai.chat.name == "llama" and ai.recipients == ["Groq"]
        both = self.settings(
            llm_provider="openrouter",
            llm_api_key="k",
            llm_model="x/y",
            embedding_provider="openrouter",
            embedding_model="e",
        )
        ai = build_ai(both)
        assert ai.recipients == ["OpenRouter"] and ai.embedder.name == "e"

    def test_generic_provider_is_named_by_its_host(self):
        s = self.settings(
            llm_provider="openai_compatible",
            llm_base_url="https://llm.corp.example/v1/",
            llm_api_key="k",
            llm_model="m",
        )
        assert build_ai(s).recipients == ["llm.corp.example"]

    def test_local_parts_send_nothing_anywhere(self):
        ai = build_ai(self.settings(llm_provider="test", embedding_provider="hashing"))
        assert ai.recipients == [] and ai.chat.name == "test-model"
        assert ai.embedder.name == "hashing-384"

    def test_missing_model_or_url_is_a_clear_error(self):
        with pytest.raises(LLMUnavailable):
            build_ai(self.settings(llm_provider="groq", llm_api_key="k"))
        with pytest.raises(LLMUnavailable):
            build_ai(self.settings(llm_provider="openai_compatible", llm_model="m"))
        with pytest.raises(LLMUnavailable):
            build_ai(self.settings(embedding_provider="jina"))

    def test_the_api_key_is_never_shown_when_settings_are_printed(self):
        s = self.settings(llm_provider="groq", llm_api_key="SECRET-KEY-123", llm_model="m")
        assert "SECRET-KEY-123" not in repr(s) and "SECRET-KEY-123" not in str(s.model_dump())


class TestBudget:
    def test_per_owner_and_daily_limits(self):
        now = [0.0]
        b = CallBudget(per_owner_per_hour=2, per_day=3, clock=lambda: now[0])
        b.charge("a")
        b.charge("a")
        with pytest.raises(BudgetExceeded):
            b.charge("a")
        b.charge("b")
        with pytest.raises(BudgetExceeded):  # the daily cap of 3 is reached
            b.charge("c")
        b2 = CallBudget(per_owner_per_hour=1, per_day=10, clock=lambda: now[0])
        b2.charge("a")
        now[0] += 3_601
        b2.charge("a")  # the hour has passed

    def test_a_charge_that_would_exceed_is_not_partially_counted(self):
        b = CallBudget(per_owner_per_hour=3, per_day=100)
        with pytest.raises(BudgetExceeded):
            b.charge("a", calls=4)
        b.charge("a", calls=3)
