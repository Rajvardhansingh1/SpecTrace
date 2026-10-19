"""One tiny call to each configured provider: `python -m scripts.check_providers`.

Run it after filling in `backend/.env` to learn whether the key, the model name and the base URL
work, before using the interface. It sends a fixed one-word prompt and one fixed word to embed, so
no document text is involved. It prints names, sizes and timings, never keys or replies.
"""

import sys
import time

from app.adapters.llm import AI, KEY_REQUIRED, build_ai
from app.config import Settings
from app.core.llm import ChatMessage
from app.errors import SpecTraceError


def check(ai: AI) -> int:
    if ai.chat is None and ai.embedder is None:
        print("Nothing is switched on yet, so there is nothing to check.")
        return 1
    status = 0
    if ai.chat is not None:
        started = time.perf_counter()
        try:
            # Room for models that think before they answer; a tiny limit would return nothing.
            out = ai.chat.complete(
                [ChatMessage("user", "Reply with the single word: ok")],
                max_tokens=400,
                temperature=0,
            )
            ms = (time.perf_counter() - started) * 1000
            print(
                f"chat       ok   model={out.model or ai.chat.name}  {ms:.0f} ms  "
                f"tokens in/out={out.prompt_tokens}/{out.completion_tokens}  "
                f"reply length={len(out.text)}"
            )
        except SpecTraceError as exc:
            print(f"chat       FAIL model={ai.chat.name}  {exc.code}: {exc.message}")
            status = 2
    if ai.embedder is not None:
        started = time.perf_counter()
        try:
            vector = ai.embedder.embed(["hello"])[0]
            ms = (time.perf_counter() - started) * 1000
            print(
                f"embeddings ok   model={ai.embedder.name}  {ms:.0f} ms  dimensions={len(vector)}"
            )
        except SpecTraceError as exc:
            print(f"embeddings FAIL model={ai.embedder.name}  {exc.code}: {exc.message}")
            status = 2
    if ai.recipients:
        print(f"Document text would be sent to: {', '.join(ai.recipients)}")
    else:
        print("Nothing would be sent to a third party.")
    return status


def missing_keys(settings: Settings, ai: AI) -> list[str]:
    """Names the key lines that are empty although their provider needs one."""
    missing = []
    if ai.chat is None and settings.llm_provider in KEY_REQUIRED:
        missing.append("SPECTRACE_LLM_API_KEY")
    reuses_chat_key = settings.embedding_provider == settings.llm_provider == "openrouter"
    if ai.embedder is None and settings.embedding_provider in KEY_REQUIRED:
        # OpenRouter embeddings reuse the chat key, so one pasted key fixes both.
        if not (reuses_chat_key and "SPECTRACE_LLM_API_KEY" in missing):
            missing.append("SPECTRACE_EMBEDDING_API_KEY")
    return missing


def main() -> int:
    settings = Settings()
    try:
        ai = build_ai(settings)
    except SpecTraceError as exc:
        print(f"setup FAIL  {exc.code}: {exc.message}")
        return 2
    for name in missing_keys(settings, ai):
        print(
            f"{name} is empty in backend/.env, so that part is off. Paste the key after the = sign."
        )
    return check(ai)


if __name__ == "__main__":
    sys.exit(main())
