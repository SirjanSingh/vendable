"""The whole server: MCP tools, discovery surfaces, and the webhook receiver, on one port.

One process and one port because that is what a merchant can actually run, and because the
webhook has to reach the same database the MCP tools write to. Splitting them would be
tidier architecture and a worse product.

Routes:

    /mcp                          MCP Streamable HTTP (spec 2026-07-28)
    /.well-known/vendable.json    machine-readable pointer to everything else
    /storefront.jsonld            schema.org catalog, with namespaced GST/HSN
    /products/{sku}.jsonld        one SKU
    /llms.txt                     the summary an agent reads before deciding to bother
    /healthz                      liveness, plus an audit-chain integrity check
    /webhooks/razorpay            Razorpay deliveries (also accepted at /)
    /console                      the merchant's own view (local only, see Settings)
    /api/console/*                the JSON behind it
    /theatre                      a captured buyer-side run, replayed (local only)
    /theatre/run.json             the capture behind it
"""

from __future__ import annotations

import json

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Mount, Route

from vendable.audit.chain import Action
from vendable.console import routes as console_routes
from vendable.theatre import routes as theatre_routes
from vendable.core.settings import settings
from vendable.core.storefront import Storefront
from vendable.mcp.server import build_app as build_mcp_app
from vendable.publish.surfaces import llms_txt, product_jsonld, storefront_jsonld, well_known
from vendable.razorpay.webhooks import SeenEvents, WebhookError, parse_delivery


def build(storefront: Storefront) -> Starlette:
    base = settings.vendable_public_base_url.rstrip("/")
    mcp_app = build_mcp_app(storefront)
    seen = SeenEvents(settings.vendable_db_path)

    def _jsonld(payload: dict) -> Response:
        # A distinct media type, so a crawler that only wants linked data can ask for it.
        return Response(
            json.dumps(payload, indent=2, ensure_ascii=False),
            media_type="application/ld+json",
        )

    async def well_known_route(_request: Request) -> Response:
        return JSONResponse(
            well_known(
                base_url=base,
                merchant_id=storefront.merchant_id,
                product_count=len(storefront.catalog),
            )
        )

    async def storefront_route(_request: Request) -> Response:
        return _jsonld(
            storefront_jsonld(
                storefront.catalog.all(), base_url=base, merchant_id=storefront.merchant_id
            )
        )

    async def product_route(request: Request) -> Response:
        sku = request.path_params["sku"].removesuffix(".jsonld")
        product = storefront.catalog.get(sku)
        if product is None:
            return JSONResponse({"error": f"No SKU '{sku}' in this catalog."}, status_code=404)
        return _jsonld(product_jsonld(product, base_url=base, merchant_id=storefront.merchant_id))

    async def llms_route(_request: Request) -> Response:
        return PlainTextResponse(
            llms_txt(
                storefront.catalog.all(),
                storefront.public_policy(),
                base_url=base,
                merchant_id=storefront.merchant_id,
            )
        )

    async def health_route(_request: Request) -> Response:
        breaks = storefront.audit.verify()
        return JSONResponse(
            {
                "status": "ok" if not breaks else "audit_chain_broken",
                "merchant": storefront.merchant_id,
                "products": len(storefront.catalog),
                "audit_records": len(storefront.audit),
                "audit_chain_intact": not breaks,
                "razorpay": "test mode" if storefront.razorpay else "not configured",
                "negotiation_model": settings.openai_model if storefront.completer else "none",
            },
            status_code=200 if not breaks else 500,
        )

    async def webhook_route(request: Request) -> Response:
        """Verify, then act. In that order, with nothing done before verification.

        Razorpay retries on any non-2xx, so a duplicate delivery is ordinary traffic rather
        than an attack. Both are handled the same way: acknowledge, and do the work once.
        """
        raw = await request.body()
        secret = settings.razorpay_webhook_secret
        if not secret:
            # Fail closed. An unconfigured secret means every delivery is unverifiable, and
            # accepting unverified money events is worse than dropping them.
            return JSONResponse({"error": "webhook secret not configured"}, status_code=503)

        try:
            event = parse_delivery(raw, dict(request.headers), secret, seen=seen)
        except WebhookError as exc:
            message = str(exc)
            if "Duplicate" in message:
                # 200, deliberately: a retry is not a failure, and a non-2xx here would make
                # Razorpay retry the retry.
                return JSONResponse({"status": "duplicate, already processed"})
            storefront.audit.append("razorpay", Action.WEBHOOK_RECEIVED, "-", {"rejected": message})
            return JSONResponse({"error": message}, status_code=400)

        storefront.audit.append(
            "razorpay",
            Action.WEBHOOK_RECEIVED,
            event.event_id,
            {"event": event.event, "handled": event.is_handled},
        )

        if not event.is_handled:
            return JSONResponse({"status": f"acknowledged, not subscribed to {event.event}"})

        payment = event.payment_entity() or {}
        link = event.payment_link_entity() or {}
        quote_id = (payment.get("notes") or {}).get("quote_id") or (link.get("notes") or {}).get(
            "quote_id", ""
        )

        if event.event in ("payment.captured", "payment_link.paid") and quote_id:
            try:
                storefront.settle(
                    quote_id,
                    payment_id=payment.get("id", link.get("id", "")),
                    captured_amount=payment.get("amount", link.get("amount_paid", 0)),
                )
            except Exception as exc:  # noqa: BLE001 -- a webhook must always return 200-ish
                storefront.audit.append(
                    "razorpay", Action.PAYMENT_FAILED, quote_id, {"settle_error": str(exc)}
                )
                return JSONResponse({"status": "received", "settle_error": str(exc)})
            return JSONResponse({"status": "settled", "quote_id": quote_id})

        if event.event == "payment.failed":
            storefront.audit.append(
                "razorpay",
                Action.PAYMENT_FAILED,
                quote_id or payment.get("id", "-"),
                {
                    "reason": payment.get("error_description", ""),
                    "code": payment.get("error_code", ""),
                },
            )

        return JSONResponse({"status": "received", "event": event.event})

    routes = [
        Route("/.well-known/vendable.json", well_known_route),
        Route("/storefront.jsonld", storefront_route),
        Route("/products/{sku}", product_route),
        Route("/llms.txt", llms_route),
        Route("/healthz", health_route),
        Route("/webhooks/razorpay", webhook_route, methods=["POST"]),
        # The dashboard webhook was configured against the bare domain, so accept there too.
        Route("/", webhook_route, methods=["POST"]),
        # The merchant's own view. Empty unless the console is enabled -- it shows cost
        # prices and the agent's spending authority, so it is local-only by default.
        # It goes BEFORE the mount: `Mount("", ...)` matches every path, so anything
        # after it is unreachable.
        *console_routes(storefront),
        # A captured buyer-side run, replayed. Same switch as the console, and for the same
        # reason: it shows real payment identifiers and what the agent was allowed to spend.
        # Also before the mount, for the reason above.
        *theatre_routes(),
        Mount("", app=mcp_app),
    ]
    # The MCP app owns a task group that is created in its lifespan. Mounting an ASGI app
    # does NOT run its lifespan -- the inner app simply never starts, and every request dies
    # with "Task group is not initialized". The outer app has to adopt it explicitly.
    return Starlette(routes=routes, lifespan=lambda _app: mcp_app.router.lifespan_context(mcp_app))


__all__ = ["build"]
