from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..llm import Usage
from ..sandbox import DockerSandbox, LocalSandbox
from ..session import Session
from ..transforms.variant import Variant


@dataclass
class RunContext:
    variant: Variant
    session: Session
    sandbox: LocalSandbox | DockerSandbox
    workspace: Path
    run_dir: Path
    system_prompt: str
    user_prompt: str


@dataclass
class AgentResult:
    status: str                      # finished | max_steps | out_of_time | stalled | error
    summary: str = ""
    usage: Usage = field(default_factory=Usage)
    steps: int = 0
    detail: dict[str, Any] = field(default_factory=dict)


class Agent(Protocol):
    name: str

    def run(self, ctx: RunContext) -> AgentResult: ...
