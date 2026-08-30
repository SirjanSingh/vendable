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

from pydantic import BaseModel, ConfigDict, Field

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
    LIST_BELOW_FLOOR = "list_below_floor"
    """The SKU's own list price does not clear the margin floor. Nothing sells it."""
    CREDIT_TERMS_EXCEEDED = "credit_terms_exceeded"
    """The merchant's own commercial ceiling on how long it will wait to be paid."""
    MSMED_LIMIT_EXCEEDED = "msmed_limit_exceeded"
    """Statutory. See `MerchantPolicy.statutory_max_credit_days`."""


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


class TermsRung(BaseModel):
    """A payment window and what paying inside it earns.

    `2/10 Net 30` -- two percent off for paying inside ten days -- is written as two rungs:
    `within_days=10, grants_bp=200` and `within_days=30, grants_bp=0`.

    Note this reads in the opposite direction to `LadderRung`. A volume rung is earned by
    *clearing* a threshold; a terms rung is earned by falling *inside* a window. Paying
    sooner can therefore never be worth less than paying later, which is the invariant a
    buyer's agent will assume and the one it would be embarrassing to get wrong.
    """

    within_days: int
    grants_bp: BasisPoints
    label: str = ""


class EnterpriseClass(str, enum.Enum):
    """Udyam classification. Only micro and small carry the s.15 payment protection."""

    MICRO = "micro"
    SMALL = "small"
    MEDIUM = "medium"
    UNREGISTERED = "unregistered"


class UdyamActivity(str, enum.Enum):
    """What the enterprise is registered as doing.

    Traders are registered under Udyam for lending purposes but sit outside s.43B(h), which
    reaches manufacturers and service providers. The exclusion matters as much as the rule:
    a guard that fired on every Indian merchant would refuse business the law permits.
    """

    MANUFACTURER = "manufacturer"
    SERVICE = "service"
    TRADER = "trader"


class MerchantPolicy(BaseModel):
    """Everything the merchant is willing to trade away, declared up front.

    Produced in Phase 4 by compiling the merchant's own plain-language rules -- but the
    merchant confirms the compiled result before it goes live. An LLM writes this structure;
    it never gets to *be* this structure at negotiation time.
    """

    model_config = ConfigDict(extra="forbid")
    """Unknown fields are an error, not noise. `margin_floor_bps` is not `margin_floor_bp`,
    and a policy that silently ignored the typo would run on a default floor nobody chose."""

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

    # --- payment terms ---
    #
    # In Indian B2B the rate and the credit period are one negotiation, not two. A policy
    # that models only the rate is modelling half the deal.

    payment_terms_ladder: list[TermsRung] = Field(default_factory=list)
    """Payment windows -> discount authority. Empty means terms move no price."""

    default_payment_terms_days: int = 30
    """Assumed when a buyer states no terms, so a quote is never silently unpriced."""

    max_credit_days: int = 60
    """The merchant's own commercial ceiling. Inclusive."""

    # --- MSMED Act exposure ---

    udyam_registered: bool = False
    enterprise_class: EnterpriseClass = EnterpriseClass.UNREGISTERED
    udyam_activity: UdyamActivity = UdyamActivity.TRADER
    written_agreement: bool = True
    """Whether a written supply agreement exists, which is what separates s.15's 45-day
    outer limit from the 15-day default."""

    def floor_for(self, product: Product) -> BasisPoints:
        return self.category_margin_floor_bp.get(product.category, self.margin_floor_bp)

    def statutory_max_credit_days(self) -> int | None:
        """The MSMED Act s.15 limit on this merchant's credit terms, or None if unbound.

        The whole statute, as a pure function, in the order the exclusions apply:

        - protection follows Udyam registration, not size alone
        - it covers micro and small enterprises; medium is excluded
        - s.43B(h) reaches manufacturers and service providers; traders are excluded
        - with a written agreement the outer limit is 45 days, without one it is 15

        Returning None rather than a large number is deliberate. "Unconstrained" and
        "constrained at some high figure" are different facts, and a buyer's agent reading
        `statutory_max_credit_days` off a decision should be able to tell them apart.
        """
        if not self.udyam_registered:
            return None
        if self.enterprise_class not in (EnterpriseClass.MICRO, EnterpriseClass.SMALL):
            return None
        if self.udyam_activity is UdyamActivity.TRADER:
            return None
        return 45 if self.written_agreement else 15


class LineRequest(BaseModel):
    """One line a buyer is asking about."""

    sku: str
    qty: int
    offered_unit_price_paise: Paise | None = None
    """What the buyer (or our own sales agent) wants the price to be. None = just asking."""
    territory: str = ""
    payment_terms_days: int | None = None
    """How long the buyer wants to take to pay. None = the merchant's declared default."""


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
    """Total authority available here, after ladders and the cap."""
    granted_bp: BasisPoints = 0
    """Authority the ladders granted, before the cap was applied."""

    entitled_bp: BasisPoints = 0
    """The PUBLISHED entitlement -- the volume break this quantity earns.

    Given automatically, without being asked for. `get_policies` publishes these thresholds,
    so withholding one until a buyer haggles would make the published policy a lie.
    """
    entitled_unit_price_paise: Paise = 0
    """List price minus the published entitlement, floored by margin. What a quote is issued at."""

    discretionary_bp: BasisPoints = 0
    """Authority a negotiation may concede ON TOP of the entitlement.

    Currently the stock-ageing ladder: a genuine reason to move old stock, but one the
    merchant would rather not hand out unprompted. This is what there is to negotiate for --
    and it is why an agent that trips the injection detector gets the entitlement and nothing
    more, rather than being rewarded with the maximum.
    """
    payment_terms_days: int = 0
    """The terms this decision was priced on -- the buyer's, or the merchant's default."""
    payment_terms_bp: BasisPoints = 0
    """Authority the payment-terms ladder granted. Entitled, not discretionary: the ladder
    is published, so paying early earns it without anyone having to ask."""
    statutory_max_credit_days: int | None = None
    """The MSMED s.15 limit in force, or None where the merchant is outside the Act.
    Reported on every decision so a buyer can read it off an approval, not only a refusal."""

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

    def _grant_terms(self, ladder: list[TermsRung], days: int) -> tuple[BasisPoints, list[str]]:
        """Best rung whose window `days` falls *inside*. The inverse of `_grant`.

        Written as a max over every qualifying window rather than the narrowest one so that
        paying sooner is never worth less than paying later, whatever order a merchant
        happens to declare the rungs in.
        """
        best, labels = 0, []
        for rung in sorted(ladder, key=lambda r: r.within_days):
            if days <= rung.within_days and rung.grants_bp > best:
                best = rung.grants_bp
                labels = [rung.label or f"within {rung.within_days}d -> {rung.grants_bp}bp"]
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

        # --- payment terms ---
        #
        # Both of these are gates rather than price adjustments: no order size and no
        # offered price rescues them. The statutory one is checked first because it is not
        # the merchant's to waive.

        terms_days = (
            req.payment_terms_days
            if req.payment_terms_days is not None
            else p.default_payment_terms_days
        )
        statutory_days = p.statutory_max_credit_days()

        if statutory_days is not None and terms_days > statutory_days:
            basis = (
                f"a written agreement caps the period at {statutory_days} days"
                if p.written_agreement
                else f"with no written supply agreement the period is {statutory_days} days"
            )
            violations.append(
                Violation(
                    code=ViolationCode.MSMED_LIMIT_EXCEEDED,
                    message=(
                        f"Net {terms_days} cannot be agreed. This supplier is a Udyam-"
                        f"registered {p.enterprise_class.value} "
                        f"{p.udyam_activity.value}, so under s.15 of the MSMED Act "
                        f"{basis}. Paying later obliges the buyer to compound interest at "
                        "three times the RBI bank rate under s.16, and defers the buyer's "
                        "own deduction on the expense under s.43B(h) until it is actually "
                        f"paid. Ask for Net {statutory_days} or shorter."
                    ),
                )
            )
        # Not an `elif`: a merchant may be more conservative than the statute, and a buyer
        # that fixes only the reason it was told about would just be refused again.
        if terms_days > p.max_credit_days:
            violations.append(
                Violation(
                    code=ViolationCode.CREDIT_TERMS_EXCEEDED,
                    message=(
                        f"Net {terms_days} is beyond this merchant's ceiling of "
                        f"Net {p.max_credit_days}. Ask for Net {p.max_credit_days} or "
                        "shorter, or pay sooner for a better rate."
                    ),
                )
            )

        # --- discount authority ---

        vol_bp, vol_labels = self._grant(p.volume_ladder, req.qty)
        age_bp, age_labels = self._grant(p.age_ladder, product.stock_age_days)
        terms_bp, terms_labels = self._grant_terms(p.payment_terms_ladder, terms_days)

        # Ladders from *different* dimensions do stack -- volume and ageing are independent
        # reasons to concede -- but `max_total_discount_bp` is the backstop that stops any
        # combination from running away.
        granted_bp = vol_bp + age_bp + terms_bp
        max_discount_bp = min(granted_bp, p.max_total_discount_bp)
        # The volume break and the terms rung are both published, so both are owed without
        # being asked for. Ageing authority is the only thing a negotiation can unlock.
        entitled_bp = min(vol_bp + terms_bp, p.max_total_discount_bp)
        discretionary_bp = max_discount_bp - entitled_bp
        rungs = vol_labels + age_labels + terms_labels
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
        entitled_price = max(
            margin_floor_price, list_price - (list_price * entitled_bp) // BP_SCALE
        )
        # When the margin floor computes ABOVE list price, the SKU cannot be sold within
        # this policy at any quantity, on any terms, at any discount -- list price is the
        # most anyone will ever pay, and even that loses money.
        #
        # This used to clamp silently to list and carry on, with a comment claiming the gap
        # validator "has already flagged it". It had: `validate_product` returns a blocking
        # gap for exactly this. But a gap is a line in a report, and nothing connected that
        # report to the sales path -- so the engine approved PIPE-GI-40 at -11.79% against a
        # 15% floor, ~Rs 230 lost per unit, with `violations` empty. Found by the property
        # sweep in scripts/negotiation_invariants.py rather than by any hand-written attack,
        # which is the second time counting has beaten attacking in this repo.
        if list_price > 0 and product.cost_price_paise > 0 and margin_floor_price > list_price:
            violations.append(
                Violation(
                    code=ViolationCode.LIST_BELOW_FLOOR,
                    message=(
                        f"{product.sku} cannot be sold. Its list price of "
                        f"{format_inr(list_price)} does not clear the "
                        f"{floor_bp / 100:.2f}% margin floor on a cost of "
                        f"{format_inr(product.cost_price_paise)} -- every sale loses "
                        f"{format_inr(product.cost_price_paise - list_price)} per unit "
                        "before any discount. No quantity or payment term changes this. "
                        f"The merchant must reprice it to at least "
                        f"{format_inr(margin_floor_price)}."
                    ),
                )
            )

        best_price = min(best_price, list_price) if list_price > 0 else best_price
        entitled_price = min(entitled_price, list_price) if list_price > 0 else entitled_price

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
            entitled_bp=entitled_bp,
            entitled_unit_price_paise=entitled_price,
            discretionary_bp=discretionary_bp,
            payment_terms_days=terms_days,
            payment_terms_bp=terms_bp,
            statutory_max_credit_days=statutory_days,
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
                f"{d.max_discount_bp / 100:.2f}% authorised) on Net {d.payment_terms_days}."
            )
        else:
            head = f"Refused: {d.qty} x {d.sku}. " + " ".join(v.message for v in d.violations)
        if d.rungs_applied:
            head += " Applied: " + "; ".join(d.rungs_applied) + "."
        return head


__all__ = [
    "EnterpriseClass",
    "LadderRung",
    "LineRequest",
    "MerchantPolicy",
    "PolicyDecision",
    "PolicyEngine",
    "TermsRung",
    "UdyamActivity",
    "Violation",
    "ViolationCode",
]
