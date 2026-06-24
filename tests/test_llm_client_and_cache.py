from dataclasses import replace
from pathlib import Path
from typing import Any

from job_copilot.cache import CacheKey, ResponseCache
from job_copilot.llm_client import OpenAIChatClient
from job_copilot.settings import load_settings


class _Message:
    content = '{"ok": true}'


class _Choice:
    message = _Message()


class _Response:
    choices = [_Choice()]


class FakeCompletions:
    def __init__(self) -> None:
        self.calls = 0

    def create(self, **kwargs: Any) -> _Response:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary failure")
        return _Response()


class FakeClient:
    def __init__(self) -> None:
        self.chat = type("Chat", (), {"completions": FakeCompletions()})()


def test_response_cache_roundtrip(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path / "cache.json")
    key = CacheKey("unit", {"prompt": "hello"})
    assert cache.get(key) is None
    cache.set(key, "cached")
    assert cache.get(key) == "cached"


def test_openai_chat_client_retries_and_returns_content(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("job_copilot.llm_client.time.sleep", lambda _: None)
    settings = replace(
        load_settings(),
        openai_api_key="test-key",
        retry_attempts=2,
        retry_backoff_seconds=0,
        cache_enabled=False,
        cache_path=tmp_path / "cache.json",
    )
    fake = FakeClient()
    client = OpenAIChatClient(settings=settings, client=fake)
    content = client.create_json_chat(
        system_prompt="system",
        user_prompt="user",
        model="gpt-test",
        temperature=0,
    )
    assert content == '{"ok": true}'
    assert fake.chat.completions.calls == 2
