"""The policy engine.

This is the component that makes the negotiation agent safe to run, and it contains **no
model call anywhere**. The sales agent may say whatever it likes; nothing it proposes reaches
a buyer until this engine has approved the number.

The engine answers exactly one question -- *what is the lowest price this merchant is willing
to accept for this line, right now?* -- and it answers it the same way every time. Ladders are
declared data, not prompt text. Given the same policy and the same line, the floor is a pure
function, which is what makes it possible to put 60 runs in a confusion matrix and defend the
result.

Design note worth stating: the engine returns a **counter-offer, not just a refusal**. A gate
that only says no forces the LLM to guess again and burns turns; one that says "no, and ₹92.40
is the best I can do" lets the agent close on the first retry. Deterministic components should
hand back the answer they already computed.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, Field

from vendable.core.models import Product
from vendable.core.money import (
    BP_SCALE,
    BasisPoints,
    Paise,
    discount_bp,
    format_inr,
    margin_bp,
    price_at_margin,
)


class ViolationCode(str, enum.Enum):
    BELOW_MARGIN_FLOOR = "below_margin_floor"
    DISCOUNT_EXCEEDS_LADDER = "discount_exceeds_ladder"
    DISCOUNT_EXCEEDS_CAP = "discount_exceeds_cap"
    BELOW_MOQ = "below_moq"
    INSUFFICIENT_STOCK = "insufficient_stock"
    TERRITORY_NOT_ALLOWED = "territory_not_allowed"
    NOT_SELLABLE = "not_sellable"
    NO_COST_BASIS = "no_cost_basis"


class Violation(BaseModel):
    code: ViolationCode
    message: str
    """Written for the buyer's agent to act on, not for a log file."""

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"


class LadderRung(BaseModel):
    """A threshold and the extra discount authority it unlocks."""

    threshold: int
    grants_bp: BasisPoints
    label: str = ""


class MerchantPolicy(BaseModel):
    """Everything the merchant is willing to trade away, declared up front.

    Produced in Phase 4 by compiling the merchant's own plain-language rules -- but the
    merchant confirms the compiled result before it goes live. An LLM writes this structure;
    it never gets to *be* this structure at negotiation time.
    """

    merchant_id: str

    margin_floor_bp: BasisPoints = 1500
    """Never sell below this gross margin on the selling price. The hard floor."""

    category_margin_floor_bp: dict[str, BasisPoints] = Field(default_factory=dict)
    """Per-category overrides. A category floor replaces the global one, high or low."""

    max_total_discount_bp: BasisPoints = 2000
    """Absolute ceiling on discount, however many ladders stack up to justify it."""

    volume_ladder: list[LadderRung] = Field(default_factory=list)
    """Quantity thresholds -> discount authority. Sorted by threshold at evaluation."""

    age_ladder: list[LadderRung] = Field(default_factory=list)
    """Stock-age thresholds in days -> extra discount authority for shifting old stock."""

    allowed_territories: list[str] = Field(default_factory=list)
    """Empty means sell anywhere. Otherwise an allowlist."""

    def floor_for(self, product: Product) -> BasisPoints:
        return self.category_margin_floor_bp.get(product.category, self.margin_floor_bp)


class LineRequest(BaseModel):
    """One line a buyer is asking about."""

    sku: str
    qty: int
    offered_unit_price_paise: Paise | None = None
    """What the buyer (or our own sales agent) wants the price to be. None = just asking."""
    territory: str = ""


class PolicyDecision(BaseModel):
    """The engine's ruling on one line. Always explains itself."""

    sku: str
    qty: int
    allowed: bool
    violations: list[Violation] = Field(default_factory=list)

    list_unit_price_paise: Paise = 0
    best_unit_price_paise: Paise = 0
    """The lowest price policy permits for this line. The counter-offer."""
    offered_unit_price_paise: Paise | None = None

    max_discount_bp: BasisPoints = 0
    """Discount authority actually available here, after ladders and the cap."""
    granted_bp: BasisPoints = 0
    """Authority the ladders granted, before the cap was applied."""
    rungs_applied: list[str] = Field(default_factory=list)
    resulting_margin_bp: BasisPoints = 0

    explanation: str = ""

    @property
    def best_line_total_paise(self) -> Paise:
        return self.best_unit_price_paise * self.qty


class PolicyEngine:
    """Evaluates lines against a declared policy. Deterministic and side-effect free."""

    def __init__(self, policy: MerchantPolicy) -> None:
        self.policy = policy

    # -- ladders -------------------------------------------------------------------

    def _grant(self, ladder: list[LadderRung], value: int) -> tuple[BasisPoints, list[str]]:
        """Highest rung whose threshold `value` clears. Rungs do not stack within a ladder.

        Deliberately *not* additive: a merchant who writes "10+ units gets 5%, 50+ gets 10%"
        means the 50-unit buyer gets 10%, not 15%. Summing rungs within one ladder is a
        classic way to accidentally authorise a discount nobody agreed to.
        """
        best, labels = 0, []
        for rung in sorted(ladder, key=lambda r: r.threshold):
            if value >= rung.threshold and rung.grants_bp > best:
                best = rung.grants_bp
                labels = [rung.label or f"threshold {rung.threshold} -> {rung.grants_bp}bp"]
        return best, labels

    # -- the ruling ----------------------------------------------------------------

    def evaluate(self, product: Product, req: LineRequest) -> PolicyDecision:
        violations: list[Violation] = []
        p = self.policy

        # --- hard gates: things no discount authority can rescue ---

        if not product.is_sellable:
            violations.append(
                Violation(
                    code=ViolationCode.NOT_SELLABLE,
                    message=(
                        f"{product.sku} is not currently sellable "
                        f"(availability={product.availability.value}, stock={product.stock_qty})."
                    ),
                )
            )

        if product.cost_price_paise <= 0:
            violations.append(
                Violation(
                    code=ViolationCode.NO_COST_BASIS,
                    message=(
                        f"{product.sku} has no cost price on file, so no margin floor can be "
                        "enforced. Negotiation is refused rather than risk selling below cost. "
                        "List price is still available."
                    ),
                )
            )

        if req.qty < product.moq:
            violations.append(
                Violation(
                    code=ViolationCode.BELOW_MOQ,
                    message=(
                        f"Minimum order quantity for {product.sku} is {product.moq}; "
                        f"{req.qty} was requested. Order at least {product.moq}."
                    ),
                )
            )

        if req.qty > product.stock_qty:
            violations.append(
                Violation(
                    code=ViolationCode.INSUFFICIENT_STOCK,
                    message=(
                        f"Only {product.stock_qty} of {product.sku} in stock; {req.qty} requested."
                    ),
                )
            )

        allowed_terr = p.allowed_territories or product.territories
        if allowed_terr and req.territory and req.territory not in allowed_terr:
            violations.append(
                Violation(
                    code=ViolationCode.TERRITORY_NOT_ALLOWED,
                    message=(
                        f"{product.sku} cannot be sold into '{req.territory}'. "
                        f"Permitted: {', '.join(allowed_terr)}."
                    ),
                )
            )

        # --- discount authority ---

        vol_bp, vol_labels = self._grant(p.volume_ladder, req.qty)
        age_bp, age_labels = self._grant(p.age_ladder, product.stock_age_days)

        # Ladders from *different* dimensions do stack -- volume and ageing are independent
        # reasons to concede -- but `max_total_discount_bp` is the backstop that stops any
        # combination from running away.
        granted_bp = vol_bp + age_bp
        max_discount_bp = min(granted_bp, p.max_total_discount_bp)
        rungs = vol_labels + age_labels
        if granted_bp > p.max_total_discount_bp:
            rungs.append(
                f"capped at {p.max_total_discount_bp}bp by max_total_discount "
                f"(ladders granted {granted_bp}bp)"
            )

        floor_bp = p.floor_for(product)
        list_price = product.list_price_paise

        # Two independent constraints on the price, and the floor is the higher of the two:
        # the margin floor (never sell below cost + margin) and the discount ceiling
        # (never concede more than authorised, whatever the margin allows).
        if product.cost_price_paise > 0:
            margin_floor_price = price_at_margin(product.cost_price_paise, floor_bp)
        else:
            margin_floor_price = list_price

        ladder_floor_price = list_price - (list_price * max_discount_bp) // BP_SCALE
        best_price = max(margin_floor_price, ladder_floor_price)
        # Never quote above list -- if the floor computes higher than list, the SKU is
        # mispriced and the gap validator has already flagged it.
        best_price = min(best_price, list_price) if list_price > 0 else best_price

        # --- judge the offer, if one was made ---

        offered = req.offered_unit_price_paise
        if offered is not None and list_price > 0:
            asked_bp = discount_bp(list_price, offered)

            if offered < margin_floor_price:
                resulting = margin_bp(offered, product.cost_price_paise)
                violations.append(
                    Violation(
                        code=ViolationCode.BELOW_MARGIN_FLOOR,
                        message=(
                            f"{format_inr(offered)} leaves {resulting / 100:.2f}% margin on "
                            f"{product.sku}; the floor for this category is "
                            f"{floor_bp / 100:.2f}%. The lowest price that clears it is "
                            f"{format_inr(margin_floor_price)}."
                        ),
                    )
                )

            if asked_bp > max_discount_bp:
                code = (
                    ViolationCode.DISCOUNT_EXCEEDS_CAP
                    if granted_bp > p.max_total_discount_bp
                    else ViolationCode.DISCOUNT_EXCEEDS_LADDER
                )
                violations.append(
                    Violation(
                        code=code,
                        message=(
                            f"A {asked_bp / 100:.2f}% discount was asked for; "
                            f"{max_discount_bp / 100:.2f}% is authorised at quantity "
                            f"{req.qty}. Order {self._next_threshold_hint(req.qty)} "
                            f"or accept {format_inr(best_price)}."
                        ),
                    )
                )

        allowed = not violations
        decision = PolicyDecision(
            sku=product.sku,
            qty=req.qty,
            allowed=allowed,
            violations=violations,
            list_unit_price_paise=list_price,
            best_unit_price_paise=best_price,
            offered_unit_price_paise=offered,
            max_discount_bp=max_discount_bp,
            granted_bp=granted_bp,
            rungs_applied=rungs,
            resulting_margin_bp=margin_bp(
                offered if offered is not None else best_price, product.cost_price_paise
            ),
        )
        decision.explanation = self._explain(decision)
        return decision

    def _next_threshold_hint(self, qty: int) -> str:
        """Name the next volume rung, so a refusal points at a way forward."""
        higher = [r for r in self.policy.volume_ladder if r.threshold > qty]
        if not higher:
            return "a larger quantity"
        nxt = min(higher, key=lambda r: r.threshold)
        return f"{nxt.threshold}+ units for {nxt.grants_bp / 100:.2f}%"

    def _explain(self, d: PolicyDecision) -> str:
        if d.allowed:
            head = (
                f"Approved: {d.qty} x {d.sku} at {format_inr(d.best_unit_price_paise)} "
                f"(list {format_inr(d.list_unit_price_paise)}, "
                f"{d.max_discount_bp / 100:.2f}% authorised)."
            )
        else:
            head = f"Refused: {d.qty} x {d.sku}. " + " ".join(v.message for v in d.violations)
        if d.rungs_applied:
            head += " Applied: " + "; ".join(d.rungs_applied) + "."
        return head


__all__ = [
    "LadderRung",
    "LineRequest",
    "MerchantPolicy",
    "PolicyDecision",
    "PolicyEngine",
    "Violation",
    "ViolationCode",
]
