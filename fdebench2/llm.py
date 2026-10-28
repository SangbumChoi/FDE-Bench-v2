"""One model protocol for everything: OpenAI-compatible Chat Completions.

Every model in the benchmark -- the solver under test, the simulated customer,
the translator, the clarification judges and the extractor -- is reached through
this interface. Any provider that speaks the OpenAI wire format plugs in by
base_url: OpenAI, Azure, Anthropic's and Gemini's OpenAI-compatible endpoints,
DeepSeek, Qwen/DashScope, OpenRouter, and self-hosted open models behind vLLM,
SGLang or Ollama.
"""

from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

import yaml


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str = ""


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0

    def add(self, other: "Usage") -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.calls += other.calls

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def to_dict(self) -> dict[str, int]:
        return {"prompt_tokens": self.prompt_tokens, "completion_tokens": self.completion_tokens,
                "total_tokens": self.total_tokens, "calls": self.calls}


@dataclass
class ChatResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    finish_reason: str | None = None

    def assistant_message(self) -> dict[str, Any]:
        """The message to append to the history so the next turn sees this one."""
        msg: dict[str, Any] = {"role": "assistant", "content": self.content or ""}
        if self.tool_calls:
            msg["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.name, "arguments": tc.raw_arguments or json.dumps(tc.arguments)}}
                for tc in self.tool_calls
            ]
        return msg


class ChatModel(Protocol):
    name: str

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
             **kwargs: Any) -> ChatResponse: ...


@dataclass(frozen=True)
class Endpoint:
    """One OpenAI-compatible endpoint + model id, as declared in configs/models.yaml."""

    name: str
    model: str
    base_url: str | None = None
    api_key_env: str | None = "OPENAI_API_KEY"
    temperature: float | None = None     # wins over a caller's default (e.g. the client's 0)
    sampling_params: bool = True         # false for endpoints that reject temperature (some reasoning models)
    max_tokens: int | None = None
    extra_body: dict[str, Any] = field(default_factory=dict)
    # Price per million tokens, for cost-budget policies. Optional.
    usd_per_mtok_in: float | None = None
    usd_per_mtok_out: float | None = None

    def cost_usd(self, usage: Usage) -> float | None:
        if self.usd_per_mtok_in is None or self.usd_per_mtok_out is None:
            return None
        return (usage.prompt_tokens * self.usd_per_mtok_in
                + usage.completion_tokens * self.usd_per_mtok_out) / 1e6


def _parse_args(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        val = json.loads(raw)
        return val if isinstance(val, dict) else {"_value": val}
    except json.JSONDecodeError:
        # Some open models emit almost-JSON; hand the raw text to the tool so it can complain.
        return {"_unparsed": raw}


class OpenAICompatModel:
    """ChatModel over the official `openai` SDK, pointed at any compatible base_url."""

    RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}

    def __init__(self, endpoint: Endpoint, max_retries: int = 6):
        from openai import OpenAI  # imported lazily so tests run without network config

        self.endpoint = endpoint
        self.name = endpoint.name
        api_key = os.environ.get(endpoint.api_key_env, "") if endpoint.api_key_env else ""
        self._client = OpenAI(base_url=endpoint.base_url, api_key=api_key or "EMPTY", max_retries=0)
        self._max_retries = max_retries

    def chat(self, messages, tools=None, **kwargs) -> ChatResponse:
        params: dict[str, Any] = {"model": self.endpoint.model, "messages": messages}
        if tools:
            params["tools"] = tools
        if self.endpoint.max_tokens is not None:
            params["max_tokens"] = self.endpoint.max_tokens
        if self.endpoint.extra_body:
            params["extra_body"] = self.endpoint.extra_body
        params.update(kwargs)
        if self.endpoint.temperature is not None:
            params["temperature"] = self.endpoint.temperature
        if not self.endpoint.sampling_params:
            params.pop("temperature", None)

        resp = self._with_retries(lambda: self._client.chat.completions.create(**params))
        choice = resp.choices[0]
        msg = choice.message
        calls = [
            ToolCall(id=tc.id or f"call_{i}", name=tc.function.name,
                     arguments=_parse_args(tc.function.arguments), raw_arguments=tc.function.arguments or "")
            for i, tc in enumerate(msg.tool_calls or [])
        ]
        usage = Usage(calls=1)
        if resp.usage is not None:
            usage.prompt_tokens = resp.usage.prompt_tokens or 0
            usage.completion_tokens = resp.usage.completion_tokens or 0
        return ChatResponse(content=msg.content, tool_calls=calls, usage=usage,
                            finish_reason=choice.finish_reason)

    def _with_retries(self, fn: Callable[[], Any]) -> Any:
        import openai

        for attempt in range(self._max_retries + 1):
            try:
                return fn()
            except (openai.APIConnectionError, openai.APITimeoutError):
                if attempt == self._max_retries:
                    raise
            except openai.APIStatusError as e:
                if e.status_code not in self.RETRY_STATUS or attempt == self._max_retries:
                    raise
            time.sleep(min(60.0, 2 ** attempt) + random.random())
        raise AssertionError("unreachable")


class ScriptedModel:
    """Deterministic stand-in for tests and dry runs.

    `script` is either a list of ChatResponse (consumed in order) or a function
    of the message list returning a ChatResponse.
    """

    def __init__(self, script: list[ChatResponse] | Callable[[list[dict[str, Any]]], ChatResponse],
                 name: str = "scripted"):
        self.name = name
        self._script = script
        self.calls: list[list[dict[str, Any]]] = []

    def chat(self, messages, tools=None, **kwargs) -> ChatResponse:
        self.calls.append([dict(m) for m in messages])
        if callable(self._script):
            return self._script(messages)
        if not self._script:
            return ChatResponse(content="(script exhausted)")
        return self._script.pop(0)


def complete_text(model: ChatModel, system: str, user: str, **kwargs: Any) -> tuple[str, Usage]:
    resp = model.chat([{"role": "system", "content": system}, {"role": "user", "content": user}], **kwargs)
    return (resp.content or "").strip(), resp.usage


def parse_json_reply(text: str) -> Any:
    """Pull the first JSON object out of a model reply (tolerates code fences and chatter)."""
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    raise ValueError(f"no JSON object in reply: {text[:200]!r}")


class ModelRegistry:
    """Loads configs/models.yaml: named endpoints plus the fixed evaluation roles."""

    ROLES = ("customer", "translator", "extractor", "judges")

    def __init__(self, endpoints: dict[str, Endpoint], roles: dict[str, Any]):
        self.endpoints = endpoints
        self.roles = roles
        self._cache: dict[str, ChatModel] = {}

    @classmethod
    def load(cls, path: str | Path) -> "ModelRegistry":
        doc = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        endpoints = {name: Endpoint(name=name, **spec) for name, spec in (doc.get("endpoints") or {}).items()}
        return cls(endpoints, doc.get("roles") or {})

    def get(self, name: str) -> ChatModel:
        if name not in self._cache:
            if name not in self.endpoints:
                raise KeyError(f"unknown endpoint {name!r}; declared: {sorted(self.endpoints)}")
            self._cache[name] = OpenAICompatModel(self.endpoints[name])
        return self._cache[name]

    def role(self, role: str) -> ChatModel:
        name = self.roles.get(role)
        if not name or isinstance(name, list):
            raise KeyError(f"role {role!r} must name exactly one endpoint in models.yaml")
        return self.get(name)

    def judges(self) -> list[ChatModel]:
        names = self.roles.get("judges") or []
        if isinstance(names, str):
            names = [names]
        return [self.get(n) for n in names]

    def fingerprint(self) -> dict[str, Any]:
        """Evaluation-side models are part of the setting; record them with every result."""
        out: dict[str, Any] = {}
        for role in self.ROLES:
            names = self.roles.get(role)
            if names is None:
                continue
            names = names if isinstance(names, list) else [names]
            out[role] = [f"{n}={self.endpoints[n].model}" for n in names if n in self.endpoints]
        return out
