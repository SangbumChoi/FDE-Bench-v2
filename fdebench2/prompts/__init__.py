"""Render the agent's task prompt in the agent locale (the "protocol language")."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from ..transforms.variant import Variant

_DIR = Path(__file__).resolve().parent / "agent"


@lru_cache(maxsize=None)
def blocks(locale: str) -> dict[str, str]:
    return yaml.safe_load((_DIR / f"{locale}.yaml").read_text(encoding="utf-8"))


def render_task_prompt(variant: Variant, workspace_label: str, data_files: list[str]) -> tuple[str, str]:
    """Return (system, user) messages. CLI harnesses get them joined into one prompt."""
    b = blocks(variant.agent_locale)
    parts = [
        b["task"].format(workspace=workspace_label,
                         data_files="\n".join(f"- {f}" for f in data_files) or "- (none)",
                         request=variant.instruction).strip(),
        b[variant.condition].format(information=variant.information).strip(),
    ]
    if variant.events:
        parts.append(b["events"].strip())
    if variant.policy_brief:
        parts.append(variant.policy_brief.strip())
    parts.append(b["delivering"].strip())
    return b["role"].strip(), "\n\n".join(parts) + "\n"
