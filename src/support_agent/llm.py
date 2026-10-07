"""OpenRouter client (OpenAI-compatible chat completions). Optional: the agent works without it."""
import os
import time
from dataclasses import dataclass

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-sonnet-5"


class LLMError(Exception):
    pass


@dataclass
class LLMResult:
    text: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    cost_usd: float | None
    latency_ms: int


def llm_configured() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY"))


def complete(messages: list[dict], model: str | None = None, temperature: float = 0.1,
             client: httpx.Client | None = None, timeout: float = 45.0) -> LLMResult:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise LLMError("OPENROUTER_API_KEY is not set")
    model = model or os.environ.get("SA_MODEL", DEFAULT_MODEL)
    payload = {"model": model, "messages": messages, "temperature": temperature, "usage": {"include": True}}
    headers = {"Authorization": f"Bearer {key}", "X-Title": "support-agent"}
    started = time.perf_counter()
    try:
        if client is not None:
            response = client.post(OPENROUTER_URL, json=payload, headers=headers)
        else:
            with httpx.Client(timeout=timeout) as http:
                response = http.post(OPENROUTER_URL, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise LLMError(f"request failed: {exc}") from exc
    latency = int((time.perf_counter() - started) * 1000)
    if response.status_code >= 400:
        raise LLMError(f"OpenRouter returned {response.status_code}: {response.text[:200]}")
    try:
        body = response.json()
        choices = body.get("choices") or []
        text = (choices[0]["message"].get("content") or "").strip() if choices else ""
        usage = body.get("usage") or {}
    except (ValueError, AttributeError, KeyError, TypeError) as exc:
        raise LLMError(f"malformed response body: {response.text[:200]}") from exc
    if not text:
        raise LLMError("empty completion")
    return LLMResult(text, body.get("model", model), usage.get("prompt_tokens"),
                     usage.get("completion_tokens"), usage.get("cost"), latency)
