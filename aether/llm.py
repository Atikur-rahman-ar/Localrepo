"""LLM backends.

Two providers are supported:

* ``openai_compatible`` - any server exposing POST {base_url}/chat/completions
  with OpenAI-style tool calling (Z.ai, OpenRouter, Groq, vLLM, llama.cpp...).
* ``ollama`` - a local Ollama daemon (POST {base_url}/api/chat).

Both are normalised to one internal message format:

    {"role": ..., "content": str | None,
     "tool_calls": [{"id", "name", "arguments"(str)}] | None}
"""

from __future__ import annotations

import json
import time
import uuid

import requests

from .config import Config


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()

    # ------------------------------------------------------------------ public
    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """Send the conversation; return a normalised assistant message."""
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                if self.config.provider == "ollama":
                    return self._chat_ollama(messages, tools)
                return self._chat_openai(messages, tools)
            except (requests.RequestException, LLMError) as exc:
                last_error = exc
                time.sleep(1.5 * (attempt + 1))
        raise LLMError(f"LLM request failed after 3 attempts: {last_error}")

    # ------------------------------------------------------- openai-compatible
    def _chat_openai(self, messages: list[dict], tools: list[dict] | None) -> dict:
        url = self.config.base_url.rstrip("/")
        if not url.endswith("/chat/completions"):
            url += "/chat/completions"

        payload: dict = {
            "model": self.config.model,
            "messages": [_wire(m, ollama=False) for m in messages],
            "temperature": self.config.temperature,
        }
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]

        resp = self.session.post(url, json=payload, headers=self._headers(), timeout=180)
        if resp.status_code >= 400:
            raise LLMError(f"HTTP {resp.status_code}: {resp.text[:500]}")

        data = resp.json()
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected response shape: {json.dumps(data)[:500]}") from exc
        return _normalise(message)

    # ------------------------------------------------------------------ ollama
    def _chat_ollama(self, messages: list[dict], tools: list[dict] | None) -> dict:
        base = self.config.base_url.rstrip("/")
        if not base.endswith("/api"):
            base += "/api"
        url = base + "/chat"

        payload: dict = {
            "model": self.config.model,
            "messages": [_wire(m, ollama=True) for m in messages],
            "stream": False,
            "options": {"temperature": self.config.temperature},
        }
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]

        resp = self.session.post(url, json=payload, timeout=600)
        if resp.status_code >= 400:
            raise LLMError(f"HTTP {resp.status_code}: {resp.text[:500]}")

        message = resp.json().get("message", {})
        tool_calls = []
        for call in message.get("tool_calls") or []:
            fn = call.get("function", {})
            args = fn.get("arguments")
            if not isinstance(args, str):
                args = json.dumps(args or {})
            tool_calls.append(
                {
                    "id": call.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                    "name": fn.get("name", ""),
                    "arguments": args,
                }
            )
        return {"content": message.get("content") or None, "tool_calls": tool_calls or None}

    # ----------------------------------------------------------------- helpers
    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers


def _normalise(message: dict) -> dict:
    tool_calls = []
    for call in message.get("tool_calls") or []:
        fn = call.get("function", {})
        tool_calls.append(
            {
                "id": call.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                "name": fn.get("name", ""),
                "arguments": fn.get("arguments") or "{}",
            }
        )
    return {"content": message.get("content") or None, "tool_calls": tool_calls or None}


def _wire(msg: dict, ollama: bool = False) -> dict:
    """Convert the internal history format into the provider wire format."""
    role = msg["role"]

    if role == "assistant" and msg.get("tool_calls"):
        calls = []
        for call in msg["tool_calls"]:
            fn = {"name": call["name"], "arguments": call["arguments"]}
            if ollama:
                try:
                    fn["arguments"] = json.loads(fn["arguments"])
                except (json.JSONDecodeError, TypeError):
                    fn["arguments"] = {}
                calls.append({"function": fn})
            else:
                calls.append({"id": call["id"], "type": "function", "function": fn})
        return {
            "role": "assistant",
            "content": msg.get("content") or "",
            "tool_calls": calls,
        }

    if role == "tool":
        if ollama:
            return {"role": "tool", "content": msg.get("content") or ""}
        return {
            "role": "tool",
            "tool_call_id": msg.get("tool_call_id", ""),
            "content": msg.get("content") or "",
        }

    return {"role": role, "content": msg.get("content") or ""}
