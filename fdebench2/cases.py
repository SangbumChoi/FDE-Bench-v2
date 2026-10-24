"""Read-only access to FDE-Bench v1 cases.

v2 never edits or redistributes v1 case files (they are CC BY-NC-ND 4.0). It
reads them from a local checkout and writes every transformed view into a run
directory that stays on the user's machine.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# v1 annotates clarification targets in Chinese field names.
_GT_TEXT = "澄清问题"
_GT_KIND = "问题类型"
_GT_DOMAIN = "内容域"


@dataclass(frozen=True)
class Target:
    """One hidden requirement the agent should uncover (a v1 gt.json entry, or one v2 adds)."""

    id: str
    text: str                 # in the variant's customer locale
    source_text: str          # as annotated (v1: Chinese)
    kind: str = ""            # v1 问题类型: 歧义 / 缺失 / ...
    domain: str = ""          # v1 内容域: 数据语义 / 计算口径 / 评分口径 ...
    origin: str = "v1"        # "v1" or the v2 transform that introduced it

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class V1Case:
    id: str
    root: Path
    instruction: str
    information: str
    targets: list[Target]
    metadata: dict[str, Any] = field(default_factory=dict)
    schema: dict[str, Any] | None = None

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def tests_dir(self) -> Path:
        return self.root / "tests"

    @property
    def evaluator(self) -> Path:
        return self.tests_dir / "evaluator.py"

    @property
    def task_type(self) -> str:
        return str(self.metadata.get("task_type", "")).strip()

    @property
    def submission_files(self) -> list[str]:
        if not self.schema:
            return []
        return [f["name"] for f in self.schema.get("files", []) if f.get("name")]

    def data_files(self) -> list[Path]:
        if not self.data_dir.is_dir():
            return []
        return sorted(p for p in self.data_dir.rglob("*") if p.is_file())

    @classmethod
    def load(cls, root: str | Path) -> "V1Case":
        root = Path(root).resolve()
        task = tomllib.loads((root / "task.toml").read_text(encoding="utf-8")) if (root / "task.toml").is_file() else {}
        gt = json.loads((root / "gt.json").read_text(encoding="utf-8")) if (root / "gt.json").is_file() else {}
        schema_path = root / "tests" / "submission_schema.json"
        return cls(
            id=root.name,
            root=root,
            instruction=(root / "instruction.md").read_text(encoding="utf-8").strip(),
            information=(root / "information.md").read_text(encoding="utf-8").strip(),
            targets=parse_gt(gt),
            metadata=task.get("metadata", {}),
            schema=json.loads(schema_path.read_text(encoding="utf-8")) if schema_path.is_file() else None,
        )


def parse_gt(gt: dict[str, Any]) -> list[Target]:
    out = []
    for key, val in gt.items():
        if isinstance(val, dict):
            text = str(val.get(_GT_TEXT) or next((v for v in val.values() if isinstance(v, str)), ""))
            kind, domain = str(val.get(_GT_KIND) or ""), str(val.get(_GT_DOMAIN) or "")
        else:
            text, kind, domain = str(val), "", ""
        out.append(Target(id=key, text=text, source_text=text, kind=kind, domain=domain))
    return out


def discover(v1_root: str | Path) -> dict[str, V1Case]:
    """Every case under <v1_root>/case (or v1_root itself if it already is the case dir)."""
    base = Path(v1_root)
    if (base / "case").is_dir():
        base = base / "case"
    return {p.name: V1Case.load(p) for p in sorted(base.iterdir()) if (p / "instruction.md").is_file()}
