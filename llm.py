"""OpenAI-compatible LLM client with throttling, capped retries and a fallback provider.

Run `python llm.py --list-models` to print the model IDs your key can use.
"""
import argparse
import random
import time
from dataclasses import dataclass, field
from typing import Iterator

import openai
import requests
from openai import OpenAI

import config


class LLMBudgetExceeded(RuntimeError):
    """Raised when the per-run request budget is used up."""


@dataclass
class Provider:
    """One OpenAI-compatible endpoint (Gemini, Groq, Mistral, Ollama, OpenRouter...)."""
    name: str
    base_url: str
    api_key: str
    model: str
    attempts: int
    json_mode_ok: bool = True
    client: OpenAI = field(init=False, repr=False)

    def __post_init__(self):
        # max_retries=0: we do our own capped retries so failed calls don't burn quota.
        self.client = OpenAI(base_url=self.base_url, api_key=self.api_key or "not-needed",
                             timeout=config.LLM_TIMEOUT_SECONDS, max_retries=0)


def is_retryable(exc: Exception) -> bool:
    """429, 5xx, timeouts and connection errors are worth retrying / failing over."""
    if isinstance(exc, (openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError)):
        return True
    return isinstance(exc, openai.APIStatusError) and exc.status_code >= 500


class LLM:
    """Primary provider (up to 3 attempts) plus an optional fallback provider (1 attempt)."""

    def __init__(self, delay: float = config.LLM_DELAY_SECONDS, max_calls: int | None = None):
        self.delay = delay
        self.max_calls = max_calls
        self.calls = 0
        self._last_call = 0.0
        self.providers = [Provider("primary", config.LLM_BASE_URL, config.LLM_API_KEY,
                                   config.LLM_MODEL, config.LLM_MAX_ATTEMPTS)]
        if config.LLM_FALLBACK_BASE_URL and config.LLM_FALLBACK_MODEL:
            self.providers.append(Provider("fallback", config.LLM_FALLBACK_BASE_URL,
                                           config.LLM_FALLBACK_API_KEY, config.LLM_FALLBACK_MODEL, 1))

    def _throttle(self):
        """Enforce the request budget and the delay between calls."""
        if self.max_calls is not None and self.calls >= self.max_calls:
            raise LLMBudgetExceeded(f"LLM request budget of {self.max_calls} reached")
        wait = self.delay - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()
        self.calls += 1

    @staticmethod
    def _backoff(attempt: int):
        time.sleep(config.LLM_BACKOFF_SECONDS * (2 ** attempt) + random.uniform(0, 1))

    def _create(self, p: Provider, messages, json_mode, temperature, max_tokens, stream=False):
        """One API request; tries JSON mode first and drops it if the provider rejects it."""
        kwargs = dict(model=p.model, messages=messages, temperature=temperature, stream=stream)
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if json_mode and p.json_mode_ok:
            self._throttle()
            try:
                return p.client.chat.completions.create(response_format={"type": "json_object"}, **kwargs)
            except openai.BadRequestError:
                print(f"  ! {p.name} rejected JSON mode; retrying as a plain request")
                p.json_mode_ok = False
        self._throttle()
        return p.client.chat.completions.create(**kwargs)

    def _attempts(self):
        """Yield (provider, attempt) pairs across the fallback chain."""
        for p in self.providers:
            for attempt in range(p.attempts):
                yield p, attempt

    def _on_failure(self, p: Provider, attempt: int, exc: Exception):
        print(f"  ! {p.name} ({p.model}) attempt {attempt + 1}/{p.attempts} failed: {type(exc).__name__}")
        if attempt + 1 < p.attempts:
            self._backoff(attempt)

    def complete(self, messages: list[dict], json_mode: bool = False,
                 temperature: float = 0.2, max_tokens: int | None = None) -> str:
        """Return the full text of one completion, failing over between providers."""
        last_error: Exception | None = None
        for p, attempt in self._attempts():
            try:
                resp = self._create(p, messages, json_mode, temperature, max_tokens)
                print(f"  · LLM answered by {p.name} ({p.model})")
                return (resp.choices[0].message.content or "").strip()
            except Exception as exc:
                if not is_retryable(exc):
                    raise
                last_error = exc
                self._on_failure(p, attempt, exc)
        raise last_error or RuntimeError("No LLM provider configured")

    def stream(self, messages: list[dict], temperature: float = 0.3,
               max_tokens: int | None = None) -> Iterator[str]:
        """Yield text chunks; fails over only if nothing has been streamed yet."""
        last_error: Exception | None = None
        for p, attempt in self._attempts():
            started = False
            try:
                resp = self._create(p, messages, False, temperature, max_tokens, stream=True)
                for chunk in resp:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                    if delta:
                        started = True
                        yield delta
                print(f"  · LLM answered by {p.name} ({p.model})")
                return
            except Exception as exc:
                if started or not is_retryable(exc):
                    raise
                last_error = exc
                self._on_failure(p, attempt, exc)
        raise last_error or RuntimeError("No LLM provider configured")


def list_models() -> list[str]:
    """GET {LLM_BASE_URL}/models with the key and return the model IDs."""
    url = config.LLM_BASE_URL.rstrip("/") + "/models"
    resp = requests.get(url, headers={"Authorization": f"Bearer {config.LLM_API_KEY}"}, timeout=30)
    resp.raise_for_status()
    return sorted(m.get("id", "").removeprefix("models/") for m in resp.json().get("data", []))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LLM helper")
    parser.add_argument("--list-models", action="store_true", help="print model IDs for your key")
    args = parser.parse_args()
    if args.list_models:
        for model_id in list_models():
            print(model_id)
    else:
        print(LLM(delay=0).complete([{"role": "user", "content": "Say hello in five words."}]))
