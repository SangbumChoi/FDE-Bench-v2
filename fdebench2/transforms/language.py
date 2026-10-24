"""Language axis: localize customer-facing text and detect the language an agent used.

Two independent variables:
  customer_locale  -- the language of the request, the hidden requirements, the
                      customer's answers and every event message.
  agent_locale     -- the language of the agent's own instructions (the
                      "protocol language" the FDE agent is deployed with).

Business data files are never translated: a real FDE gets the customer's
spreadsheets as they are, so translated text must keep file, sheet, column and
code names verbatim.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..llm import ChatModel, Usage, complete_text

SOURCE_LOCALE = "zh"  # every v1 case is authored in Chinese
LOCALES = {
    "zh": "Simplified Chinese",
    "en": "English",
    "ko": "Korean",
    "ja": "Japanese",
    "es": "Spanish",
}
# How a business customer writes in each language; the translator and the
# simulated customer both follow it.
REGISTER = {
    "zh": "ordinary business Chinese as written in workplace chat",
    "en": "plain professional English",
    "ko": "business-polite Korean (합니다/해요체 as in workplace messenger), natural Korean business terms",
    "ja": "business Japanese with です/ます and light 敬語, natural Japanese business terms",
    "es": "professional Spanish using usted, neutral (not region-specific) vocabulary",
}


def resolve(locale: str) -> str:
    return SOURCE_LOCALE if locale in ("source", "", None) else locale


def check_locale(locale: str) -> str:
    loc = resolve(locale)
    if loc not in LOCALES:
        raise ValueError(f"unsupported locale {locale!r}; supported: {sorted(LOCALES)}")
    return loc


_TRANSLATE_SYSTEM = """You translate business documents for a benchmark of forward-deployed engineering agents.
Rules:
- Translate from {src} into {dst}. Write it the way a real customer would: {register}.
- Keep the meaning exact. Do not add, drop, soften, clarify or resolve anything. If the source is vague, the translation stays exactly as vague.
- Keep every file name, sheet name, column/field name, ID, code value, number, unit and formula verbatim. If such a name is in {src} and a reader of {dst} needs it, you may add a translation in parentheses after the verbatim name, e.g. `仓到店LT` (warehouse-to-store lead time).
- Preserve Markdown structure, lists and code blocks.
- Output only the translation."""


class Translator:
    """LLM translation with a content-addressed on-disk cache.

    The cache lives in the user's own working tree (`.cache/`, git-ignored):
    translations of v1 text are adaptations of CC BY-NC-ND material and must not
    be committed or shared.
    """

    def __init__(self, model: ChatModel | None, cache_dir: str | Path):
        self.model = model
        self.cache_dir = Path(cache_dir)
        self.usage = Usage()

    def _key(self, text: str, src: str, dst: str, kind: str) -> str:
        model = self.model.name if self.model else "none"
        h = hashlib.sha256(json.dumps([model, src, dst, kind, text], ensure_ascii=False).encode()).hexdigest()
        return h[:32]

    def translate(self, text: str, dst: str, src: str = SOURCE_LOCALE, kind: str = "document") -> str:
        src, dst = check_locale(src), check_locale(dst)
        if src == dst or not text.strip():
            return text
        path = self.cache_dir / dst / f"{self._key(text, src, dst, kind)}.txt"
        if path.is_file():
            return path.read_text(encoding="utf-8")
        if self.model is None:
            raise RuntimeError(f"translation {src}->{dst} not cached and no translator model configured")
        system = _TRANSLATE_SYSTEM.format(src=LOCALES[src], dst=LOCALES[dst], register=REGISTER[dst])
        out, usage = complete_text(self.model, system, text)
        self.usage.add(usage)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(out, encoding="utf-8")
        return out


# ── language identification ─────────────────────────────────────────────────

_ES_MARKERS = ("ñ", "¿", "¡", " el ", " los ", " las ", " del ", " para ", " que ", " una ", " está", " por ")
_EN_MARKERS = (" the ", " and ", " is ", " are ", " of ", " to ", " what ", " which ", " should ")


def detect_locale(text: str) -> str | None:
    """Cheap script-based language ID for the five benchmark locales.

    Good enough to tell whether an agent answered a Korean customer in Korean;
    not a general-purpose detector. Returns None for text with no letters.
    """
    hangul = kana = han = latin = 0
    for ch in text:
        o = ord(ch)
        if 0xAC00 <= o <= 0xD7A3 or 0x1100 <= o <= 0x11FF or 0x3130 <= o <= 0x318F:
            hangul += 1
        elif 0x3040 <= o <= 0x30FF:
            kana += 1
        elif 0x4E00 <= o <= 0x9FFF:
            han += 1
        elif ch.isascii() and ch.isalpha() or ch in "áéíóúñü":
            latin += 1
    total = hangul + kana + han + latin
    if total == 0:
        return None
    # Code, file names and column names are Latin in every language, so CJK
    # scripts win as soon as they make up a meaningful share of the letters.
    cjk = hangul + kana + han
    if cjk >= 0.15 * total:
        if hangul >= max(kana, han * 0.5):
            return "ko"
        if kana >= 0.1 * (kana + han):
            return "ja"
        return "zh"
    lower = f" {text.lower()} "
    es = sum(lower.count(m) for m in _ES_MARKERS)
    en = sum(lower.count(m) for m in _EN_MARKERS)
    return "es" if es > en else "en"


def language_fidelity(texts: list[str], expected: str) -> float | None:
    """Share of non-trivial texts written in the expected locale (None if nothing to judge)."""
    expected = resolve(expected)
    verdicts = [detect_locale(t) for t in texts if t and len(t.strip()) >= 8]
    verdicts = [v for v in verdicts if v is not None]
    if not verdicts:
        return None
    return sum(v == expected for v in verdicts) / len(verdicts)
