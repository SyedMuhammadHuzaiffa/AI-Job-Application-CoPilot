import time
from typing import Any, Protocol

from openai import OpenAI

from .cache import CacheKey, ResponseCache
from .exceptions import OpenAIConfigError, OpenAIRequestError
from .logging_config import get_logger
from .settings import AppSettings, load_settings


logger = get_logger(__name__)


class ChatClient(Protocol):
    def create_json_chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
    ) -> str:
        """Return the assistant message content for a JSON-oriented chat request."""


class OpenAIChatClient:
    def __init__(
        self,
        settings: AppSettings | None = None,
        cache: ResponseCache | None = None,
        client: Any | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        if not self.settings.openai_api_key:
            raise OpenAIConfigError("OPENAI_API_KEY is not set.")
        self.cache = cache or ResponseCache(self.settings.cache_path, enabled=self.settings.cache_enabled)
        self.client = client or OpenAI(api_key=self.settings.openai_api_key)

    def create_json_chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
    ) -> str:
        cache_key = CacheKey(
            namespace="openai.chat.completions",
            payload={
                "model": model,
                "temperature": temperature,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            },
        )
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.info("Using cached OpenAI response for model=%s", model)
            return cached

        request: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }

        content = self._create_with_retries(request)
        self.cache.set(cache_key, content)
        return content

    def _create_with_retries(self, request: dict[str, Any]) -> str:
        attempts = max(1, self.settings.retry_attempts)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                response = self.client.chat.completions.create(**request)
                return response.choices[0].message.content or "{}"
            except Exception as exc:
                last_error = exc
                message = str(exc).lower()
                if "response_format" in message or "json_object" in message:
                    logger.info("Retrying OpenAI request without response_format because the model rejected JSON mode.")
                    fallback_request = dict(request)
                    fallback_request.pop("response_format", None)
                    response = self.client.chat.completions.create(**fallback_request)
                    return response.choices[0].message.content or "{}"
                if attempt >= attempts:
                    break
                delay = self.settings.retry_backoff_seconds * (2 ** (attempt - 1))
                logger.warning("OpenAI request failed on attempt %s/%s: %s", attempt, attempts, exc)
                time.sleep(delay)
        raise OpenAIRequestError(f"OpenAI request failed after {attempts} attempt(s): {last_error}")


def get_default_chat_client(settings: AppSettings | None = None) -> OpenAIChatClient:
    return OpenAIChatClient(settings=settings)
