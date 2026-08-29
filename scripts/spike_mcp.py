"""Spike B -- the MCP killer.

Question: can a stock, unmodified Claude client connect to this server given only a URL,
and actually call a tool?

Everything downstream depends on yes. Answered before any domain code exists.

    ../.venv/Scripts/python.exe scripts/spike_mcp.py
    claude mcp add --transport http --scope local vendable-spike http://localhost:8080/mcp

Findings land in docs/research/PHASE-0.md and what-broke.md.
"""

from __future__ import annotations

import os

import uvicorn
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import BaseModel

mcp = MCPServer(
    name="vendable-spike",
    title="Vendable (transport spike)",
    version="0.0.1",
    instructions=(
        "A throwaway server that exists only to prove a stock client can reach it by URL. "
        "It sells nothing."
    ),
)


class Echo(BaseModel):
    """Structured output, to confirm structuredContent rides along with the text content."""

    heard: str
    server: str
    protocol_note: str


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
def ping(message: str) -> Echo:
    """Echo a message back. Proves the transport, nothing more."""
    return Echo(
        heard=message,
        server="vendable-spike",
        protocol_note="MCP 2026-07-28 streamable http, stateless",
    )


def build_app():
    # Empty allowlist -> SDK default, which is localhost-only. Correct for local work.
    # Behind a real hostname this MUST be populated or every request gets 421.
    allowed = [h for h in os.environ.get("VENDABLE_ALLOWED_HOSTS", "").split(",") if h.strip()]
    security = None
    if allowed:
        security = TransportSecuritySettings(
            allowed_hosts=allowed + [f"{h}:*" for h in allowed],
            allowed_origins=[f"https://{h}" for h in allowed],
        )
    return mcp.streamable_http_app(transport_security=security)


app = build_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"spike server on http://localhost:{port}/mcp")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
