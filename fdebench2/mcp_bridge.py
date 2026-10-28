"""MCP server that gives CLI harnesses the same client channel as the reference agent.

    python -m fdebench2.mcp_bridge --run-dir RUN_DIR                       # stdio (dev)
    FDEB2_BRIDGE_TOKEN=... python -m fdebench2.mcp_bridge --run-dir RUN_DIR --http 172.17.0.1:8765

In stdio mode the bridge runs as a child of the CLI agent, so the agent's user
can read the run directory (including hidden requirements). For real runs put
the agent in a container that mounts only the workspace and point it at the
bridge over streamable HTTP on the host. Over HTTP every request must carry
`Authorization: Bearer <token>` with the run's random token, so other
containers on the network (other runs) cannot use this run's client.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
from pathlib import Path

from .llm import ModelRegistry
from .session import Session
from .transforms.variant import Variant

TOKEN_ENV = "FDEB2_BRIDGE_TOKEN"
CLIENT_USAGE = "client_usage.json"      # the client model's usage so far, read by the runner for cost columns


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

    def _reply(text: str) -> str:
        if session.customer is not None:
            (session.run_dir / CLIENT_USAGE).write_text(json.dumps(session.customer.usage.to_dict()),
                                                       encoding="utf-8")
        return text + session.inbox_note(session.poll_events())

    if session.variant.can_ask:
        @server.tool(description="Send questions to the client and wait for the answer. "
                                 "Put several questions in one message, one per line.")
        def ask_customer(questions: str) -> str:
            session.tick("ask_customer")
            return _reply(session.ask(questions))

    if session.variant.policy.agent_visible:
        @server.tool(description="Ask the client for permission to break one of their business rules, "
                                 "or record that you are breaking one, as the engagement policy requires.")
        def request_exception(rule: str, justification: str) -> str:
            session.tick("request_exception")
            return _reply(session.request_exception(rule, justification))

    @server.tool(description="Check for new messages from the client.")
    def check_inbox() -> str:
        session.tick("check_inbox")
        return _reply("") or "(no new messages)"

    return server


def http_app(server, token: str, host: str = "127.0.0.1"):
    """The server's streamable HTTP app (at /mcp) behind a bearer-token check."""
    try:
        app = server.streamable_http_app(host=host)           # mcp >= 2
    except TypeError:
        app = server.streamable_http_app()                    # mcp 1.x
    expected = f"Bearer {token}".encode()

    async def guarded(scope, receive, send):
        if scope["type"] == "http" and not hmac.compare_digest(dict(scope["headers"]).get(b"authorization", b""),
                                                                expected):
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"content-type", b"text/plain")]})
            await send({"type": "http.response.body", "body": b"unauthorized"})
            return
        await app(scope, receive, send)
    return guarded


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--http", help=f"host:port to serve streamable HTTP instead of stdio (token in ${TOKEN_ENV})")
    args = ap.parse_args()
    token = os.environ.get(TOKEN_ENV, "")
    if args.http and not token:
        ap.error(f"--http needs a bearer token in ${TOKEN_ENV}")
    server = build_server(build_session(args.run_dir))
    if args.http:
        import uvicorn
        host, port = args.http.rsplit(":", 1)
        uvicorn.run(http_app(server, token, host), host=host, port=int(port), log_level="warning")
    else:
        server.run("stdio")


if __name__ == "__main__":
    main()
