"""Localize the messages FDE-Bench v2 generates itself.

A message is {"t": <English template>, "p": {params}} (see transforms.events.msg).
The template is looked up in prompts/messages.yaml; parameters that are messages
(or lists of messages) are localized recursively, then the template is formatted.
A template missing from the catalog (e.g. a custom policy's statement) falls back
to the run-time translator if one is given, else stays English.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import yaml

_CATALOG = Path(__file__).resolve().parent / "prompts" / "messages.yaml"
_LIST_SEP = {"zh": "；", "ja": "、", "en": "; ", "ko": "; ", "es": "; "}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


@lru_cache(maxsize=1)
def catalog() -> dict[str, dict[str, str]]:
    doc = yaml.safe_load(_CATALOG.read_text(encoding="utf-8")) or {}
    return {_norm(k): v for k, v in doc.items()}


def template(text: str, lang: str, fallback: Callable[[str], str] | None = None) -> str:
    if lang == "en":
        return text
    entry = catalog().get(_norm(text))
    if entry and lang in entry:
        return entry[lang]
    return fallback(text) if fallback else text


def render(message: Any, lang: str, fallback: Callable[[str], str] | None = None) -> str:
    if isinstance(message, list):
        return _LIST_SEP.get(lang, "; ").join(render(m, lang, fallback) for m in message)
    if not isinstance(message, dict) or "t" not in message:
        return str(message)
    params = {k: render(v, lang, fallback) if isinstance(v, (dict, list)) else v
              for k, v in (message.get("p") or {}).items()}
    return template(message["t"], lang, fallback).format(**params)


def missing(lang: str, messages: list[Any]) -> list[str]:
    """Templates (recursively) that the catalog lacks for `lang`; used by tests and the case validator."""
    out: list[str] = []
    for m in messages:
        if isinstance(m, list):
            out += missing(lang, m)
        elif isinstance(m, dict) and "t" in m:
            if lang != "en" and lang not in catalog().get(_norm(m["t"]), {}):
                out.append(m["t"])
            out += missing(lang, [v for v in (m.get("p") or {}).values() if isinstance(v, (dict, list))])
    return out
