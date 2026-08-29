"""The storefront: everything wired together, with the audit chain woven through.

This is the only place that knows about all the pieces at once, and it exists so that the
MCP server and the CLI drive *identical* logic. A demo where the CLI takes a different code
path from the agent-facing surface is a demo that proves nothing about the agent-facing
surface.

The ordering inside `purchase()` is the part worth reading closely. It is deliberately
paranoid, and each step is placed where it is for a reason:

1. the quote must exist and still be reserved
2. the **mandate gate** runs before anything irreversible -- signature, expiry, audience,
   cap, budget, replay
3. only then is the cart re-hashed and compared to what was authorised
4. the spend is recorded *before* the payment link is created, so a crash between the two
   leaves a phantom spend rather than an unrecorded charge

Point 4 is a real trade-off and it is chosen knowingly: over-recording costs a buyer a
retry, under-recording costs them money twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vendable.audit.chain import Action, AuditChain
from vendable.commerce.machine import (
    CommerceError,
    CommerceMachine,
    CommerceStore,
    Quote,
)
from vendable.core.catalog import Catalog
from vendable.core.models import Product
from vendable.core.money import Paise, format_inr
from vendable.mandate.gate import Cart, CartLine, GateDecision, MandateGate, SpendLedger
from vendable.policy.engine import LineRequest, MerchantPolicy, PolicyDecision, PolicyEngine


class StorefrontError(Exception):
    """A request was refused. The message is written for the buyer's agent to act on."""


@dataclass(slots=True)
class QuoteLine:
    sku: str
    qty: int
    unit_price_paise: Paise
    list_price_paise: Paise
    discount_bp: int
    explanation: str


@dataclass(slots=True)
class PurchaseResult:
    quote_id: str
    authorised: bool
    gate: GateDecision
    payment_link_url: str = ""
    payment_link_id: str = ""
    message: str = ""


class Storefront:
    def __init__(
        self,
        *,
        merchant_id: str,
        catalog: Catalog,
        policy: MerchantPolicy,
        audit: AuditChain,
        commerce: CommerceMachine,
        gate: MandateGate,
        razorpay=None,  # RazorpayClient | None -- injected so tests need no credentials
    ) -> None:
        self.merchant_id = merchant_id
        self.catalog = catalog
        self.policy = policy
        self.engine = PolicyEngine(policy)
        self.audit = audit
        self.commerce = commerce
        self.gate = gate
        self.razorpay = razorpay

    # -- discovery -----------------------------------------------------------------

    def search(self, query: str, *, limit: int = 10) -> list[Product]:
        return self.catalog.search(query, limit=limit, in_stock_only=True)

    def get(self, sku: str) -> Product:
        p = self.catalog.get(sku)
        if p is None:
            near = self.catalog.search(sku, limit=3)
            hint = f" Did you mean: {', '.join(x.sku for x in near)}?" if near else ""
            raise StorefrontError(f"No SKU '{sku}' in this catalog.{hint}")
        return p

    def public_policy(self) -> dict:
        """The trading terms a buyer is allowed to see.

        Cost prices and margin floors are **never** published. A buyer who knows the floor
        knows exactly what to demand, and the negotiation becomes theatre. What is published
        is what a human sales rep would tell you: the volume breaks, the ageing policy, the
        territories, and the ceiling on any discount.
        """
        return {
            "merchant_id": self.merchant_id,
            "currency": "INR",
            "prices_include_gst": True,
            "max_discount_pct": round(self.policy.max_total_discount_bp / 100, 2),
            "volume_breaks": [
                {"min_qty": r.threshold, "discount_pct": round(r.grants_bp / 100, 2)}
                for r in sorted(self.policy.volume_ladder, key=lambda r: r.threshold)
            ],
            "clearance_policy": [
                {
                    "stock_age_days_min": r.threshold,
                    "extra_discount_pct": round(r.grants_bp / 100, 2),
                }
                for r in sorted(self.policy.age_ladder, key=lambda r: r.threshold)
            ],
            "territories": self.policy.allowed_territories or ["IN-KA", "IN-MH", "IN-TN"],
            "note": (
                "Discounts are granted by declared rules, not by persuasion. Every counter-"
                "offer is checked against a margin floor that is not published; asking for a "
                "deeper discount than the rules allow will be refused with the best available "
                "price attached."
            ),
        }

    # -- pricing -------------------------------------------------------------------

    def price_line(
        self, sku: str, qty: int, *, territory: str = "", offered_unit_price: Paise | None = None
    ) -> tuple[Product, PolicyDecision]:
        product = self.get(sku)
        decision = self.engine.evaluate(
            product,
            LineRequest(
                sku=sku, qty=qty, territory=territory, offered_unit_price_paise=offered_unit_price
            ),
        )
        return product, decision

    def quote(
        self, items: list[tuple[str, int]], *, territory: str = ""
    ) -> tuple[Quote, list[QuoteLine]]:
        """Price a basket at the best price policy allows, and open a quote.

        A quote is issued at the **best legal price**, not at list. A buyer that qualifies
        for a volume break gets it without having to ask -- making an agent haggle for a
        discount it already earned is how human sales works, not how this should.
        """
        if not items:
            raise StorefrontError("Ask for at least one SKU and quantity.")

        lines: list[CartLine] = []
        detail: list[QuoteLine] = []
        refusals: list[str] = []

        for sku, qty in items:
            try:
                product, decision = self.price_line(sku, qty, territory=territory)
            except StorefrontError as exc:
                refusals.append(str(exc))
                continue
            if not decision.allowed:
                refusals.append(decision.explanation)
                continue
            lines.append(
                CartLine(sku=sku, qty=qty, unit_price_paise=decision.best_unit_price_paise)
            )
            detail.append(
                QuoteLine(
                    sku=sku,
                    qty=qty,
                    unit_price_paise=decision.best_unit_price_paise,
                    list_price_paise=decision.list_unit_price_paise,
                    discount_bp=decision.max_discount_bp,
                    explanation=decision.explanation,
                )
            )

        if not lines:
            self.audit.append(
                "buyer", Action.QUOTE_REFUSED, "-", {"items": items, "refusals": refusals}
            )
            raise StorefrontError("Nothing could be quoted. " + " ".join(refusals))

        q = self.commerce.quote(lines, notes={"territory": territory})
        self.audit.append(
            "merchant",
            Action.QUOTE_ISSUED,
            q.quote_id,
            {
                "total_paise": q.total_paise,
                "cart_hash": q.cart_hash,
                "lines": [
                    {"sku": d.sku, "qty": d.qty, "unit_paise": d.unit_price_paise} for d in detail
                ],
                "refused_lines": refusals,
            },
        )
        return q, detail

    # -- reservation ---------------------------------------------------------------

    def reserve(self, quote_id: str) -> Quote:
        try:
            q = self.commerce.reserve(quote_id, available=self.catalog.stock_map())
        except CommerceError as exc:
            self.audit.append("merchant", Action.QUOTE_REFUSED, quote_id, {"why": str(exc)})
            raise StorefrontError(str(exc)) from exc
        self.audit.append(
            "merchant",
            Action.RESERVATION_HELD,
            quote_id,
            {"until_s": q.reserved_until_s, "total_paise": q.total_paise},
        )
        return q

    # -- purchase ------------------------------------------------------------------

    def purchase(self, quote_id: str, mandate: str) -> PurchaseResult:
        """Authorise and prepare payment. See the module docstring for the ordering."""
        q = self.commerce.store.get(quote_id)
        if q is None:
            raise StorefrontError(f"No such quote: {quote_id}.")

        cart = Cart(merchant_id=self.merchant_id, currency="INR", lines=list(q.cart.lines))

        self.audit.append(
            "buyer", Action.MANDATE_PRESENTED, quote_id, {"cart_hash": cart.cart_hash()}
        )

        # 2. the gate, before anything irreversible
        decision = self.gate.evaluate(mandate, cart)
        if not decision.allowed:
            self.audit.append(
                "merchant",
                Action.MANDATE_REFUSED,
                quote_id,
                {
                    "amount_paise": decision.amount_paise,
                    "cap_paise": decision.cap_paise,
                    "refusals": [r.model_dump() for r in decision.refusals],
                    "explanation": decision.explanation,
                },
            )
            return PurchaseResult(
                quote_id=quote_id,
                authorised=False,
                gate=decision,
                message=decision.explanation,
            )

        self.audit.append(
            "merchant",
            Action.MANDATE_ACCEPTED,
            quote_id,
            {
                "jti": decision.mandate_jti,
                "subject": decision.subject,
                "amount_paise": decision.amount_paise,
                "cap_paise": decision.cap_paise,
            },
        )

        # 3. the cart must not have moved since authorisation
        try:
            self.commerce.begin_capture(quote_id, cart.cart_hash())
        except CommerceError as exc:
            self.audit.append("merchant", Action.PAYMENT_FAILED, quote_id, {"why": str(exc)})
            raise StorefrontError(str(exc)) from exc

        # 4. record the spend before creating the link
        ref = f"{decision.mandate_jti[:16]}-{decision.cart_hash[:12]}"
        fresh = self.gate.ledger.record(
            decision.mandate_jti, decision.cart_hash, decision.amount_paise, 0, ref
        )
        if not fresh:
            return PurchaseResult(
                quote_id=quote_id,
                authorised=False,
                gate=decision,
                message=(
                    "This cart was already charged under this mandate. Nothing was charged again."
                ),
            )

        if self.razorpay is None:
            self.audit.append(
                "merchant",
                Action.PAYMENT_REQUESTED,
                quote_id,
                {"amount_paise": decision.amount_paise, "note": "no payment provider configured"},
            )
            return PurchaseResult(
                quote_id=quote_id,
                authorised=True,
                gate=decision,
                message=(
                    f"Authorised {format_inr(decision.amount_paise)}, but no payment provider "
                    "is configured on this server."
                ),
            )

        link = self.razorpay.create_payment_link(
            decision.amount_paise,
            description=f"Vendable {quote_id}",
            reference_id=ref,
            notes={"quote_id": quote_id, "mandate_jti": decision.mandate_jti[:16]},
        )
        self.commerce.attach_payment_link(quote_id, link_id=link.id, link_url=link.short_url)
        self.audit.append(
            "merchant",
            Action.PAYMENT_REQUESTED,
            quote_id,
            {
                "amount_paise": decision.amount_paise,
                "payment_link_id": link.id,
                "reference_id": ref,
            },
        )
        return PurchaseResult(
            quote_id=quote_id,
            authorised=True,
            gate=decision,
            payment_link_url=link.short_url,
            payment_link_id=link.id,
            message=(
                f"Authorised {format_inr(decision.amount_paise)} against mandate "
                f"{decision.mandate_jti[:8]}. Complete payment at {link.short_url}."
            ),
        )

    def settle(self, quote_id: str, *, payment_id: str, captured_amount: Paise) -> Quote:
        """Record a confirmed capture. Called by the webhook handler."""
        q = self.commerce.complete_capture(quote_id, payment_id=payment_id)
        self.catalog_deduct(q)
        self.audit.append(
            "merchant",
            Action.PAYMENT_CAPTURED,
            quote_id,
            {"payment_id": payment_id, "amount_paise": captured_amount},
        )
        return q

    def catalog_deduct(self, q: Quote) -> None:
        for line in q.cart.lines:
            product = self.catalog.get(line.sku)
            if product is not None:
                self.catalog.set_stock(line.sku, max(0, product.stock_qty - line.qty))


def build_storefront(
    *,
    merchant_id: str,
    db_path: Path | str,
    policy: MerchantPolicy,
    public_pem: str,
    razorpay=None,
) -> Storefront:
    """Wire a storefront against one SQLite file.

    Every store shares the same database so the whole demo is one file that can be copied,
    inspected, or deleted -- and so `audit --verify` sees the same rows the server wrote.
    """
    db_path = str(db_path)
    return Storefront(
        merchant_id=merchant_id,
        catalog=Catalog(db_path, merchant_id=merchant_id),
        policy=policy,
        audit=AuditChain(db_path),
        commerce=CommerceMachine(CommerceStore(db_path), merchant_id=merchant_id),
        gate=MandateGate(public_pem, merchant_id=merchant_id, ledger=SpendLedger(db_path)),
        razorpay=razorpay,
    )


__all__ = [
    "PurchaseResult",
    "QuoteLine",
    "Storefront",
    "StorefrontError",
    "build_storefront",
]
