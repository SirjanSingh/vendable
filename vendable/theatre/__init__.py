"""The theatre: a captured buyer-side run, replayed as a page.

The merchant console next door answers the merchant's two questions -- what is the agent allowed
to do, and what has it been doing. This surface answers a third one, which belongs to whoever is
being shown the system rather than whoever owns it: *what actually happened when a buyer's agent
met this merchant?*

That run already exists. `scripts/demo_buy.py` drives it end to end -- discovery, a volume break
applied unasked, three mandate refusals on three different grounds, the MSMED statutory refusal
that only one of the two merchants can make, a prompt injection that wins nothing, a payment that
settles and a payment that declines. It renders as terminal scrollback, and
`docs/video/PRODUCTION.md` is explicit that terminal scrollback is never what goes on screen: the
real text gets re-typeset, it does not get screenshotted.

So this is that text, re-typeset, in the same LEDGER GLASS the console and the film already use.

Replay rather than live, deliberately. `vendable/razorpay/checkout.py` makes the same argument
about the payment simulator: a failure that only happens sometimes cannot be put in a demo. A
page that re-runs the negotiation live in front of an audience is a page that depends on an LLM's
latency and a network's mood at the exact moment attention is most expensive. The values here
were produced by a real run against two live servers on Razorpay test mode; nothing is
illustrative and nothing is rounded.

`run.json` is currently transcribed by hand from the run committed at
`docs/video/assets/demo_run.txt`, plus the two payment legs in `docs/sessions/2026-08-31.md`.
There is deliberately no `--capture` flag on `demo_buy.py`: that script is what both the film
and the live demo run, and editing it was not worth the risk this close to the deadline. Adding
one is the obvious next step, and it is the only reason this file is not self-updating.

Gated on the same switch as the console. It shows cost-derived pricing, the merchant's own
discretionary authority, and real payment identifiers, which SECURITY.md H1/H2 already identify
as the things a buyer most wants to see.
"""

from __future__ import annotations

from pathlib import Path

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from vendable.core.settings import settings

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
RUN = HERE / "run.json"


def routes() -> list[Route | Mount]:
    """Theatre routes, or an empty list when the surface is switched off."""
    if not settings.console_enabled:
        return []

    # A build that was never run leaves no `static/`. Mounting StaticFiles at a missing directory
    # raises at construction, which would take the whole server down -- including the MCP endpoint
    # and the console, neither of which has anything to do with this page. Fail soft instead and
    # say what to run.
    if not STATIC.is_dir():

        async def missing(_request: Request) -> Response:
            return JSONResponse(
                {
                    "error": "theatre is not built",
                    "run": "cd theatre && npm install && npm run build",
                },
                status_code=503,
            )

        return [Route("/theatre", missing)]

    async def run(_request: Request) -> Response:
        if not RUN.is_file():
            return JSONResponse(
                {
                    "error": "no captured run",
                    "run": "restore vendable/theatre/run.json from git",
                },
                status_code=503,
            )
        return FileResponse(RUN, media_type="application/json")

    return [
        # Ahead of the mount: Starlette matches in order, and StaticFiles would otherwise serve
        # the copy Vite bakes into the bundle rather than the canonical file next to this module.
        # Both exist on purpose -- the baked copy is what makes the built page work when it is
        # opened straight off disk, with no server at all, which is the fallback if something
        # goes wrong live.
        Route("/theatre/run.json", run),
        Mount("/theatre", app=StaticFiles(directory=STATIC, html=True)),
    ]


__all__ = ["routes"]
