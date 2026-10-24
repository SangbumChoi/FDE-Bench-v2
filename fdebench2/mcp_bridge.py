"""MCP server that gives CLI harnesses the same client channel as the reference agent.

    python -m fdebench2.mcp_bridge --run-dir RUN_DIR                      # stdio (dev)
    python -m fdebench2.mcp_bridge --run-dir RUN_DIR --http 127.0.0.1:8765  # isolated agents

In stdio mode the bridge runs as a child of the CLI agent, so the agent's user
can read the run directory (including hidden requirements). For real runs put
the agent in a container that mounts only the workspace and point it at the
bridge over streamable HTTP on the host.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .llm import ModelRegistry
from .session import Session
from .transforms.variant import Variant


def build_session(run_dir: Path) -> Session:
    meta = json.loads((run_dir / "session.json").read_text(encoding="utf-8"))
    variant = Variant.load(run_dir / "variant")
    registry = ModelRegistry.load(meta["models_config"])
    customer = registry.role("customer") if variant.can_ask or variant.policy.agent_visible else None
    return Session(variant, run_dir, Path(meta["workspace"]), customer, use_steps=False,
                   started_at=meta["started_at"])


def build_server(session: Session):
    try:
        from mcp.server.mcpserver import MCPServer as Server  # mcp >= 2
    except ImportError:
        from mcp.server.fastmcp import FastMCP as Server       # mcp 1.x

    server = Server(name="fde-client", instructions="Channel to the client of this engagement.")

    def _with_inbox(text: str) -> str:
        return text + session.inbox_note(session.poll_events())

    if session.variant.can_ask:
        @server.tool(description="Send questions to the client and wait for the answer. "
                                 "Put several questions in one message, one per line.")
        def ask_customer(questions: str) -> str:
            session.tick("ask_customer")
            return _with_inbox(session.ask(questions))

    if session.variant.policy.agent_visible:
        @server.tool(description="Ask the client for permission to break one of their business rules, "
                                 "or record that you are breaking one, as the engagement policy requires.")
        def request_exception(rule: str, justification: str) -> str:
            session.tick("request_exception")
            return _with_inbox(session.request_exception(rule, justification))

    @server.tool(description="Check for new messages from the client.")
    def check_inbox() -> str:
        session.tick("check_inbox")
        return _with_inbox("") or "(no new messages)"

    return server


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--http", help="host:port to serve streamable HTTP instead of stdio")
    args = ap.parse_args()
    server = build_server(build_session(args.run_dir))
    if args.http:
        host, port = args.http.rsplit(":", 1)
        server.run("streamable-http", host=host, port=int(port))
    else:
        server.run("stdio")


if __name__ == "__main__":
    main()
