"""OpenRouter chat completions with a pinned provider and retries."""

import os
import time
from dataclasses import dataclass

import requests

URL = "https://openrouter.ai/api/v1/chat/completions"
RETRIES = 8


@dataclass(frozen=True)
class Reply:
    text: str
    finish: str
    prompt_tokens: int
    completion_tokens: int
    provider: str
    seconds: float
    response_id: str
    served_model: str
    created: int
    cost: float = 0.0
    reasoning_tokens: int = 0


class OpenRouter:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {os.environ['OPENROUTER_API_KEY']}"

    def chat(
        self,
        model: str,
        provider: str,
        messages: list[dict],
        temperature: float | None,
        max_tokens: int,
        seed: int | None,
    ) -> Reply:
        """temperature or seed None: the parameter is not sent (endpoints that do not support it)."""
        body = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "provider": {"order": [provider], "allow_fallbacks": False},
            "usage": {"include": True},
        }
        if temperature is not None:
            body["temperature"] = temperature
        if seed is not None:
            body["seed"] = seed
        start = time.perf_counter()
        for attempt in range(RETRIES):
            try:
                response = self.session.post(URL, json=body, timeout=300)
                data = response.json()
            except (requests.RequestException, ValueError):
                time.sleep(min(2**attempt, 60))
                continue
            if response.status_code == 200 and data.get("choices"):
                choice = data["choices"][0]
                usage = data.get("usage") or {}
                return Reply(
                    choice["message"].get("content") or "",
                    choice.get("finish_reason") or "",
                    usage.get("prompt_tokens", 0),
                    usage.get("completion_tokens", 0),
                    data.get("provider", ""),
                    time.perf_counter() - start,
                    data.get("id", ""),
                    data.get("model", ""),
                    data.get("created", 0),
                    float(usage.get("cost") or 0.0),
                    int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0),
                )
            time.sleep(min(2**attempt, 60))
        raise RuntimeError(f"{model}: no reply after {RETRIES} attempts")
