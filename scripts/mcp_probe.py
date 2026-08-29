"""A minimal MCP client, used to drive the storefront the way a stock agent would.

Deliberately hand-rolled against the wire format rather than using the SDK client: the claim
being tested is that *any* spec-compliant 2026-07-28 client can transact here, and borrowing
the same SDK the server uses would quietly prove something weaker.

    .venv/Scripts/python.exe scripts/mcp_probe.py [url]
"""

from __future__ import annotations

import json
import sys
from typing import Any

import httpx

PROTOCOL = "2026-07-28"
ENVELOPE = {
    "io.modelcontextprotocol/protocolVersion": PROTOCOL,
    "io.modelcontextprotocol/clientCapabilities": {},
}


class McpClient:
    def __init__(self, url: str = "http://localhost:8080/mcp", timeout: float = 120.0) -> None:
        self.url = url
        self._http = httpx.Client(timeout=timeout)

    def rpc(self, method: str, params: dict[str, Any] | None = None, name: str = "") -> Any:
        body_params = dict(params or {})
        body_params["_meta"] = ENVELOPE
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL,
            "Mcp-Method": method,
        }
        if name:
            headers["Mcp-Name"] = name
        resp = self._http.post(
            self.url,
            headers=headers,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": body_params},
        )
        payload = _decode(resp)
        if "error" in payload:
            raise RuntimeError(f"{method} -> {payload['error']}")
        return payload["result"]

    def discover(self) -> Any:
        return self.rpc("server/discover")

    def list_tools(self) -> list[dict]:
        return self.rpc("tools/list")["tools"]

    def call(self, tool: str, **arguments: Any) -> dict:
        """Call a tool. Returns structuredContent, or raises with the server's own message."""
        result = self.rpc("tools/call", {"name": tool, "arguments": arguments}, name=tool)
        if result.get("isError"):
            text = " ".join(
                block.get("text", "")
                for block in result.get("content", [])
                if isinstance(block, dict)
            )
            raise ToolRefused(text.strip() or "tool returned an error with no message")
        return result.get("structuredContent", {})

    def close(self) -> None:
        self._http.close()


def _decode(resp: httpx.Response) -> dict[str, Any]:
    """Accept either a JSON body or an SSE stream.

    A server may answer a slow tool call with `text/event-stream` rather than
    `application/json` -- both are valid under the spec, and a client that only handles the
    first fails on exactly the tools that take long enough to matter. Found the hard way when
    `negotiate` started making a real model call.
    """
    content_type = resp.headers.get("content-type", "")
    if "text/event-stream" not in content_type:
        return resp.json()
    for line in resp.text.splitlines():
        if line.startswith("data:"):
            body = line[5:].strip()
            if body:
                return json.loads(body)
    raise RuntimeError(f"SSE response carried no data frame: {resp.text[:200]}")


class ToolRefused(RuntimeError):
    """The server refused. The message is meant to be actionable -- read it."""


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080/mcp"
    c = McpClient(url)

    info = c.discover()
    server = info.get("_meta", {}).get("io.modelcontextprotocol/serverInfo", {})
    print(f"connected: {server.get('title')} v{server.get('version')}")
    print(f"protocol:  {', '.join(info.get('supportedVersions', []))}\n")

    tools = c.list_tools()
    print(f"{len(tools)} tools:")
    for t in tools:
        ann = t.get("annotations", {})
        flags = "read-only" if ann.get("readOnlyHint") else "writes"
        if ann.get("destructiveHint"):
            flags += ", destructive"
        print(f"  {t['name']:<18} ({flags})")
        print(f"      {t['description'].splitlines()[0]}")
    print()

    print(json.dumps(c.call("get_policies"), indent=2)[:900])
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
