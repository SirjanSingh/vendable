"""The merchant's console: routes and the JSON behind them.

Everything else in this repo is built for the *buyer's* agent. This is the only surface built
for the person whose money it is. That distinction drives every decision here.

The console is read-mostly and it does not make policy. It cannot change a margin floor, grant
an exception, or authorise a purchase — those live in `policy.json` and the mandate gate, where
they are reviewable and testable. What it does is answer the two questions a merchant actually
has when they hand a sales agent the keys:

    "What is it allowed to do?"      -> the compiled policy, in the merchant's own numbers
    "What has it been doing?"        -> the audit chain, refusals first, verified on demand

Plus one thing a log cannot answer: *what would it say to this buyer?* `rehearse` runs the real
`negotiate` path against the real engine and shows the merchant the answer before a buyer ever
asks — the same call the buyer would make, on a throwaway subject, so it is a rehearsal and not
a quote anyone can hold them to.

Not mounted outside `VENDABLE_ENV=local` unless `VENDABLE_CONSOLE=on`. See
`Settings.console_enabled` for why: this page shows cost prices and the discretionary authority
the agent may spend, which SECURITY.md H1/H2 already identify as the thing a buyer most wants.
"""

from __future__ import annotations

import json
from pathlib import Path

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route

from vendable.core.settings import settings
from vendable.core.storefront import Storefront, StorefrontError

INDEX = Path(__file__).resolve().parent / "index.html"

# A rehearsal is a real model call on the merchant's own key. Capping the message length keeps
# a stuck loop in the page from becoming a bill, and the buyer-facing tool has no such cap
# because there the cost is bounded by the buyer's own patience, not by a text box.
MAX_REHEARSAL_CHARS = 600


def _record_json(rec) -> dict:
    return {
        "seq": rec.seq,
        "ts_ms": rec.ts_ms,
        "actor": rec.actor,
        "action": rec.action.value,
        "subject": rec.subject,
        "payload": rec.payload,
        "this_hash": rec.this_hash,
        "prev_hash": rec.prev_hash,
    }


def routes(storefront: Storefront) -> list[Route]:
    """Console routes, or an empty list when the console is switched off."""
    if not settings.console_enabled:
        return []

    # The server's own chain, not a new one. `vendable.core.db` keeps a single connection
    # per file, and `AuditChain.close()` closes it for every store sharing it -- so a
    # console that opened and closed its own chain per request would tear the database out
    # from under the MCP tools. It did, on the first page load: the catalog came back with
    # "Cannot operate on a closed database".
    chain = storefront.audit

    async def page(_request: Request) -> Response:
        # Read per request rather than cached at import, so editing the page and refreshing
        # the browser is the whole edit loop. There is no build step to forget to run.
        return HTMLResponse(INDEX.read_text(encoding="utf-8"))

    async def state(_request: Request) -> Response:
        policy = storefront.policy
        products = storefront.catalog.all()
        head = chain.head
        records = len(chain)
        return JSONResponse(
            {
                "merchant_id": storefront.merchant_id,
                "env": settings.vendable_env,
                "product_count": len(products),
                "records": records,
                "head": head,
                "razorpay": "test mode" if storefront.razorpay else "not configured",
                "llm": settings.openai_model if settings.llm_configured else "not configured",
                "policy": storefront.public_policy(),
                # The merchant's own numbers, which the buyer-facing surfaces never emit.
                "floor": {
                    "margin_floor_pct": policy.margin_floor_bp / 100,
                    "max_total_discount_pct": policy.max_total_discount_bp / 100,
                },
                "products": [
                    {
                        "sku": p.sku,
                        "title": p.title,
                        "list_price_paise": p.list_price_paise,
                        "cost_price_paise": p.cost_price_paise,
                        "stock_qty": p.stock_qty,
                        "stock_age_days": p.stock_age_days,
                        "sellable": p.is_sellable,
                    }
                    for p in products
                ],
            }
        )

    async def ledger(request: Request) -> Response:
        try:
            limit = min(int(request.query_params.get("limit", "60")), 500)
        except ValueError:
            limit = 60
        records = [_record_json(r) for r in chain]
        return JSONResponse({"records": records[-limit:][::-1], "total": len(records)})

    async def verify(_request: Request) -> Response:
        breaks = chain.verify()
        total = len(chain)
        head = chain.head
        return JSONResponse(
            {
                "intact": not breaks,
                "records": total,
                "head": head,
                "breaks": [
                    {"seq": b.seq, "record_id": b.record_id, "reason": b.reason} for b in breaks
                ],
            }
        )

    async def rehearse(request: Request) -> Response:
        """Run the buyer's own negotiate path, so the merchant sees it before a buyer does."""
        try:
            body = json.loads(await request.body() or b"{}")
        except json.JSONDecodeError:
            return JSONResponse({"error": "body must be JSON"}, status_code=400)

        sku = str(body.get("sku", "")).strip()
        message = str(body.get("message", "")).strip()
        try:
            qty = int(body.get("qty", 0))
        except (TypeError, ValueError):
            return JSONResponse({"error": "qty must be a whole number"}, status_code=400)
        terms = body.get("payment_terms_days")
        terms = None if terms in (None, "") else int(terms)

        if not sku or qty <= 0 or not message:
            return JSONResponse({"error": "sku, a positive qty and a message"}, status_code=400)
        if len(message) > MAX_REHEARSAL_CHARS:
            return JSONResponse(
                {"error": f"message is capped at {MAX_REHEARSAL_CHARS} characters here"},
                status_code=400,
            )

        product = storefront.catalog.get(sku)
        if product is None:
            return JSONResponse({"error": f"no SKU '{sku}' in this catalog"}, status_code=404)

        try:
            result = storefront.negotiate(product, qty, message, payment_terms_days=terms)
        except StorefrontError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

        # The two numbers the merchant is really asking about: what the engine already owed
        # this buyer, and how much of the discretionary allowance the agent chose to spend.
        _prod, baseline = storefront.price_line(sku, qty, payment_terms_days=terms)
        return JSONResponse(
            {
                "sku": result.sku,
                "qty": result.qty,
                "list_price_paise": result.list_price_paise,
                "unit_price_paise": result.final_unit_price_paise,
                "conceded_bp": result.conceded_bp,
                "entitled_bp": baseline.entitled_bp,
                "discretionary_bp": baseline.discretionary_bp,
                "spent_bp": result.conceded_bp - baseline.entitled_bp,
                "floor_unit_price_paise": baseline.best_unit_price_paise,
                "message": result.message,
                "rounds": len(result.turns),
                "used_fallback": result.used_fallback,
                "payment_terms_days": result.payment_terms_days,
                "injection": {
                    "risk": result.injection.risk.value if result.injection else "clean",
                    "summary": result.injection.summary() if result.injection else "",
                },
                "blocked_reason": result.blocked_reason,
            }
        )

    return [
        Route("/console", page),
        Route("/api/console/state", state),
        Route("/api/console/ledger", ledger),
        Route("/api/console/verify", verify),
        Route("/api/console/rehearse", rehearse, methods=["POST"]),
    ]


__all__ = ["routes"]
