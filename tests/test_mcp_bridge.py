import asyncio
import json
import time

import pytest

pytest.importorskip("mcp")

from fdebench2.cases import NativeCase
from fdebench2.llm import ChatResponse, ScriptedModel
from fdebench2.mcp_bridge import build_server
from fdebench2.session import Session, read_transcript
from fdebench2.transforms.language import Translator
from fdebench2.transforms.variant import VariantSpec, build_variant


def test_bridge_exposes_client_channel(cases_root, tmp_path):
    case = NativeCase(cases_root / "logistics_bakery_routing")
    run_dir = tmp_path / "run"
    v = build_variant(VariantSpec(case.id, policy="enterprise_balanced"), case, run_dir / "workspace",
                      Translator(ScriptedModel(lambda m: ChatResponse(content=m[-1]["content"])), tmp_path / "c"))
    session = Session(v, run_dir, run_dir / "workspace", ScriptedModel(lambda m: ChatResponse(content="C11 is closed this week.")),
                      use_steps=False, started_at=time.time())
    server = build_server(session)

    async def go():
        names = {t.name for t in await server.list_tools()}
        out = await server.call_tool("ask_customer", {"questions": "Should C11 get a delivery?"})
        return names, out

    names, out = asyncio.run(go())
    assert names == {"ask_customer", "request_exception", "check_inbox"}
    assert "C11 is closed" in json.dumps(out, ensure_ascii=False, default=str)
    assert [r["kind"] for r in read_transcript(run_dir) if r["kind"] == "ask"] == ["ask"]
