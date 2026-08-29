"""The buyer-facing MCP server.

This is the whole point of the project: a stock, unmodified Claude client is given a URL and
nothing else, and can shop, negotiate, be refused, and buy.

Two design rules run through every tool here.

**Errors are instructions, not complaints.** A buying agent that receives "purchase denied"
has to guess; one that receives "cart total ₹6,000.00 exceeds the mandate cap of ₹5,000.00 by
₹1,000.00 -- remove ₹1,000.00 of items, or present a mandate with a higher cap" can act on
the next turn without a human. Every refusal in this system names the constraint, the actual
numbers, and a way forward. The MCP spec's own error for a missing envelope key did exactly
this during Phase 0, and it set the bar.

**Annotations are hints, not security.** `destructiveHint` on `create_purchase` is a courtesy
to the client's UI. The spec says plainly never to rely on a client honouring them, so the
real control is the mandate gate, which runs server-side and trusts nothing the buyer says.

Transport is Streamable HTTP under MCP spec 2026-07-28: no `initialize` handshake, no
session id, every request self-contained. Verified against a live client in Phase 0.
"""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from vendable.core.money import format_inr
from vendable.core.settings import settings
from vendable.core.storefront import Storefront, StorefrontError

# ---------------------------------------------------------------------------------
# Output shapes. Returning a model rather than a string fills `structuredContent`
# alongside the text, so a client can render a table without re-parsing prose.
# ---------------------------------------------------------------------------------


class ProductOut(BaseModel):
    sku: str
    title: str
    description: str
    unit: str
    list_price: str
    list_price_paise: int
    gst_rate_pct: float
    hsn_code: str
    """Indian tax classification. No agentic-commerce catalog standard has a field for this."""
    brand: str
    category: str
    min_order_qty: int
    in_stock: bool
    stock_qty: int


class SearchOut(BaseModel):
    query: str
    count: int
    products: list[ProductOut]
    note: str = ""


class QuoteLineOut(BaseModel):
    sku: str
    qty: int
    unit_price: str
    unit_price_paise: int
    list_price: str
    discount_pct: float
    line_total: str
    line_total_paise: int


class QuoteOut(BaseModel):
    quote_id: str
    lines: list[QuoteLineOut]
    total: str
    total_paise: int
    currency: str = "INR"
    expires_at_epoch_s: int
    cart_hash: str
    """Fingerprint of exactly what was quoted. The capture step refuses if this changes."""
    state: str
    next_step: str
    refused_lines: list[str] = Field(default_factory=list)


class ReservationOut(BaseModel):
    quote_id: str
    state: str
    reserved_until_epoch_s: int
    total: str
    next_step: str


class PurchaseOut(BaseModel):
    quote_id: str
    authorised: bool
    payment_link_id: str = ""
    amount: str
    amount_paise: int
    mandate_cap: str = ""
    refusal_code: str = ""
    explanation: str
    payment_url: str = ""
    next_step: str


class NegotiationOut(BaseModel):
    sku: str
    qty: int
    unit_price: str
    unit_price_paise: int
    list_price: str
    discount_pct: float
    message: str
    """What the merchant's sales agent says. Always policy-validated before you see it."""
    rounds_used: int
    used_deterministic_fallback: bool
    note: str = ""


class PolicyOut(BaseModel):
    merchant_id: str
    currency: str
    prices_include_gst: bool
    max_discount_pct: float
    volume_breaks: list[dict]
    clearance_policy: list[dict]
    territories: list[str]
    note: str


# ---------------------------------------------------------------------------------


def _product_out(p) -> ProductOut:
    return ProductOut(
        sku=p.sku,
        title=p.title,
        description=p.description,
        unit=p.unit,
        list_price=format_inr(p.list_price_paise),
        list_price_paise=p.list_price_paise,
        gst_rate_pct=p.gst_rate_bp / 100,
        hsn_code=p.hsn_code,
        brand=p.brand,
        category=p.category,
        min_order_qty=p.moq,
        in_stock=p.is_sellable,
        stock_qty=p.stock_qty,
    )


def build_server(storefront: Storefront) -> MCPServer:
    """Construct the MCP server around a wired storefront."""

    mcp = MCPServer(
        name="vendable",
        title=f"Vendable — {storefront.merchant_id}",
        version="0.1.0",
        instructions=(
            "An agent-transactable storefront. You can search the catalog, read the published "
            "trading policy, request a quote, negotiate within the merchant's declared rules, "
            "reserve stock, and buy.\n\n"
            "Buying requires a signed payment mandate — a compact JWS carrying a spending cap "
            "— which you pass to create_purchase as an argument. The merchant verifies it "
            "server-side and will refuse anything over the cap, expired, replayed, or issued "
            "for a different merchant. Refusals always tell you what would have worked, so "
            "read them and retry rather than giving up.\n\n"
            "Quotes are already priced at the best rate the merchant's rules allow for your "
            "quantity. You do not have to ask for a volume discount you have already earned."
        ),
    )

    read_only = ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    )

    # -- discovery -----------------------------------------------------------------

    @mcp.tool(annotations=read_only)
    def search_products(query: str, limit: int = 10) -> SearchOut:
        """Search the catalog by keyword. Returns in-stock SKUs with prices in INR.

        Matching is literal keyword matching, not semantic — quote the words you mean.
        Passing an exact SKU ranks that SKU first.
        """
        found = storefront.search(query, limit=max(1, min(limit, 50)))
        return SearchOut(
            query=query,
            count=len(found),
            products=[_product_out(p) for p in found],
            note=(
                ""
                if found
                else (
                    "Nothing matched. Search is literal keyword matching, so try the words a "
                    "catalog would use ('hex bolt M8' rather than 'fastener for my shelf'), "
                    "or call get_policies to see what categories this merchant carries."
                )
            ),
        )

    @mcp.tool(annotations=read_only)
    def get_product(sku: str) -> ProductOut:
        """Full detail for one SKU, including HSN code and GST rate for Indian invoicing."""
        try:
            return _product_out(storefront.get(sku))
        except StorefrontError as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool(annotations=read_only)
    def get_policies() -> PolicyOut:
        """The merchant's published trading terms: volume breaks, clearance, territories.

        Read this before negotiating. Discounts here are granted by declared rules rather
        than by persuasion, so knowing the rules is the whole of the negotiation.
        """
        return PolicyOut(**storefront.public_policy())

    # -- quoting -------------------------------------------------------------------

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
        )
    )
    def request_quote(items: list[dict], territory: str = "") -> QuoteOut:
        """Price a basket and open a quote.

        `items` is a list of `{"sku": "BOLT-M8-40", "qty": 500}`. The quote is priced at the
        best rate the merchant's rules allow for those quantities, is binding for a fixed
        window, and holds no stock — call `reserve_stock` for that.

        `territory` is an optional region code such as IN-KA; some SKUs are restricted.
        """
        parsed: list[tuple[str, int]] = []
        for item in items:
            sku = str(item.get("sku", "")).strip()
            try:
                qty = int(item.get("qty", 0))
            except (TypeError, ValueError):
                raise ValueError(
                    f"qty for '{sku}' must be a whole number, got {item.get('qty')!r}."
                ) from None
            if not sku or qty <= 0:
                raise ValueError(
                    'Each item needs a non-empty "sku" and a positive integer "qty", '
                    'e.g. {"sku": "BOLT-M8-40", "qty": 500}.'
                )
            parsed.append((sku, qty))

        try:
            quote, detail = storefront.quote(parsed, territory=territory)
        except StorefrontError as exc:
            raise ValueError(str(exc)) from exc

        return QuoteOut(
            quote_id=quote.quote_id,
            lines=[
                QuoteLineOut(
                    sku=d.sku,
                    qty=d.qty,
                    unit_price=format_inr(d.unit_price_paise),
                    unit_price_paise=d.unit_price_paise,
                    list_price=format_inr(d.list_price_paise),
                    discount_pct=round(d.discount_bp / 100, 2),
                    line_total=format_inr(d.unit_price_paise * d.qty),
                    line_total_paise=d.unit_price_paise * d.qty,
                )
                for d in detail
            ],
            total=format_inr(quote.total_paise),
            total_paise=quote.total_paise,
            expires_at_epoch_s=quote.expires_at_s,
            cart_hash=quote.cart_hash,
            state=quote.state.value,
            next_step=(
                f"Call reserve_stock('{quote.quote_id}') to hold the stock, then "
                f"create_purchase with a mandate whose cap is at least "
                f"{format_inr(quote.total_paise)}."
            ),
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
        )
    )
    def reserve_stock(quote_id: str) -> ReservationOut:
        """Hold the stock on a quote for a limited window.

        Idempotent: reserving an already-reserved quote returns the existing reservation
        rather than holding the stock twice. The hold expires and releases itself.
        """
        try:
            quote = storefront.reserve(quote_id)
        except StorefrontError as exc:
            raise ValueError(str(exc)) from exc
        return ReservationOut(
            quote_id=quote.quote_id,
            state=quote.state.value,
            reserved_until_epoch_s=quote.reserved_until_s or 0,
            total=format_inr(quote.total_paise),
            next_step=(
                f"Call create_purchase('{quote.quote_id}', mandate) before the hold expires."
            ),
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True, destructiveHint=False, idempotentHint=False, openWorldHint=False
        )
    )
    def negotiate(sku: str, qty: int, message: str) -> NegotiationOut:
        """Negotiate the price of one line with the merchant's sales agent.

        Give it a real reason — order size, a repeat relationship, stock that has clearly been
        sitting. Reasons move the price; persistence does not, and neither does claiming an
        approval, because every number the sales agent proposes is checked against rules it
        cannot see or change before it is said to you.

        The volume break your quantity earns is already in `request_quote`. What is available
        here is the discretionary allowance on top of it.
        """
        try:
            product = storefront.get(sku)
        except StorefrontError as exc:
            raise ValueError(str(exc)) from exc
        if qty <= 0:
            raise ValueError("qty must be a positive whole number.")

        result = storefront.negotiate(product, qty, message)
        return NegotiationOut(
            sku=result.sku,
            qty=result.qty,
            unit_price=format_inr(result.final_unit_price_paise),
            unit_price_paise=result.final_unit_price_paise,
            list_price=format_inr(result.list_price_paise),
            discount_pct=round(result.conceded_bp / 100, 2),
            message=result.message,
            rounds_used=result.rounds_used,
            used_deterministic_fallback=result.used_fallback,
            note=(
                "This price is not held. Call request_quote to lock it into a quote."
                if not result.blocked_reason
                else result.blocked_reason
            ),
        )

    # -- buying --------------------------------------------------------------------

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=True,
            openWorldHint=True,
        )
    )
    def create_purchase(quote_id: str, mandate: str) -> PurchaseOut:
        """Authorise payment for a reserved quote against a signed mandate.

        `mandate` is a compact JWS carrying an AP2-shaped `payment.amount_range` constraint —
        your spending cap, in paise. The merchant verifies its signature, expiry, audience,
        cap, budget and replay status server-side; nothing about it is taken on trust.

        This is the only tool that can move money. It is idempotent on
        (mandate, exact cart): presenting the same pair twice will not charge twice.

        If it refuses, the explanation names the constraint and the numbers. Act on it.
        """
        try:
            result = storefront.purchase(quote_id, mandate)
        except StorefrontError as exc:
            raise ValueError(str(exc)) from exc

        first = result.gate.first_refusal
        return PurchaseOut(
            quote_id=result.quote_id,
            authorised=result.authorised,
            amount=format_inr(result.gate.amount_paise),
            amount_paise=result.gate.amount_paise,
            mandate_cap=(
                format_inr(result.gate.cap_paise) if result.gate.cap_paise is not None else ""
            ),
            refusal_code=first.code.value if first else "",
            explanation=result.message,
            payment_url=result.payment_link_url,
            payment_link_id=result.payment_link_id,
            next_step=(
                f"Complete payment at {result.payment_link_url}"
                if result.payment_link_url
                else (
                    "Fix the reason above and call create_purchase again."
                    if not result.authorised
                    else "Authorised."
                )
            ),
        )

    return mcp


def build_app(storefront: Storefront):
    """ASGI app for uvicorn. Mounted at /mcp.

    The allowlist matters: `streamable_http_app()` defaults to localhost-only DNS-rebinding
    protection, so behind any real hostname every request returns 421 Misdirected Request
    until `allowed_hosts` names it. Reading it from config here means deploying is a config
    change, not a code change.
    """
    mcp = build_server(storefront)
    hosts = settings.allowed_hosts
    security = None
    if hosts:
        security = TransportSecuritySettings(
            allowed_hosts=hosts + [f"{h}:*" for h in hosts],
            allowed_origins=[f"https://{h}" for h in hosts],
        )
    return mcp.streamable_http_app(transport_security=security)


def default_storefront() -> Storefront:
    """Build the demo storefront from disk, for `python -m vendable.mcp.server`."""
    from vendable.core.catalog import load_seed
    from vendable.core.storefront import build_storefront
    from vendable.mandate.ap2 import public_pem_from_private
    from vendable.policy.engine import LadderRung, MerchantPolicy

    merchant = os.environ.get("VENDABLE_MERCHANT", "acme-fasteners")
    root = Path(__file__).resolve().parents[2]
    db = Path(settings.vendable_db_path)

    public_pem = public_pem_from_private(settings.mandate_private_key())

    policy = MerchantPolicy(
        merchant_id=merchant,
        margin_floor_bp=1500,
        max_total_discount_bp=2000,
        volume_ladder=[
            LadderRung(threshold=100, grants_bp=500, label="100+ units -> 5%"),
            LadderRung(threshold=500, grants_bp=1000, label="500+ units -> 10%"),
            LadderRung(threshold=2000, grants_bp=1500, label="2000+ units -> 15%"),
        ],
        age_ladder=[
            LadderRung(threshold=90, grants_bp=300, label="90+ days old -> 3%"),
            LadderRung(threshold=180, grants_bp=500, label="180+ days old -> 5%"),
        ],
        allowed_territories=["IN-KA", "IN-MH", "IN-TN"],
    )

    razorpay = None
    if settings.razorpay_configured and settings.is_test_mode:
        from vendable.razorpay.client import RazorpayClient

        razorpay = RazorpayClient()

    completer = None
    if settings.llm_configured:
        from vendable.negotiate.llm import LLMUnavailable, OpenAICompleter

        try:
            completer = OpenAICompleter()
        except LLMUnavailable:
            completer = None  # deterministic pricing still works; negotiation just falls back

    sf = build_storefront(
        merchant_id=merchant,
        db_path=db,
        policy=policy,
        public_pem=public_pem,
        razorpay=razorpay,
        completer=completer,
    )

    if len(sf.catalog) == 0:
        seed = root / "fixtures" / "merchants" / merchant / "catalog.json"
        if seed.exists():
            sf.catalog.put_many(load_seed(seed), merchant_id=merchant)

    return sf


app = None  # populated on import by __main__ below, or by the CLI


if __name__ == "__main__":
    import uvicorn

    sf = default_storefront()
    print(f"vendable mcp: {len(sf.catalog)} SKUs, merchant {sf.merchant_id}")
    port = int(os.environ.get("PORT", "8080"))
    print(f"listening on http://localhost:{port}/mcp")
    uvicorn.run(build_app(sf), host="0.0.0.0", port=port, log_level="info")
