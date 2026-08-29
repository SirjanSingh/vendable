"""The catalog domain.

A `Product` is what a merchant sells. A `Gap` is a specific, named reason an AI buyer will
skip past it -- and the whole point of the validator is that gaps are found *deterministically*
and ranked by the revenue they cost, so a merchant with forty broken SKUs knows which three
to fix first.
"""

from __future__ import annotations

import enum
import re

from pydantic import BaseModel, Field, field_validator

from vendable.core.money import BasisPoints, Paise, apply_bp, format_inr, margin_bp

# HSN codes are 4, 6 or 8 digits in Indian GST filings. Anything else is a typo.
HSN_RE = re.compile(r"^\d{4}(\d{2})?(\d{2})?$")

# The GST slabs that actually exist. A rate outside this set is an extraction error,
# not an unusual business decision.
VALID_GST_BP: frozenset[int] = frozenset({0, 50, 300, 500, 1200, 1800, 2800})


class Severity(str, enum.Enum):
    BLOCKING = "blocking"
    """An AI buyer cannot transact this SKU at all."""
    DEGRADING = "degrading"
    """It is transactable, but will lose to a better-described competitor."""
    ADVISORY = "advisory"
    """Worth fixing, costs nothing today."""


class Availability(str, enum.Enum):
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    BACKORDER = "backorder"


class Product(BaseModel):
    """A single sellable SKU.

    Field names follow schema.org `Product` / `Offer` where an equivalent exists, so the
    JSON-LD published in Phase 3 is a rename rather than a translation.

    `hsn_code` and `gst_rate_bp` have **no equivalent** in schema.org, in OpenAI's product
    feed spec, or in UCP. Every agentic-commerce catalog standard published so far assumes a
    tax model that India does not use. They are carried here under a `vendable:` namespace
    when serialised -- see `vendable.publish`.
    """

    sku: str
    title: str = ""
    description: str = ""

    # money
    list_price_paise: Paise = 0
    """GST-inclusive list price, the number an Indian merchant actually writes down."""
    cost_price_paise: Paise = 0
    """Landed cost. Never published; used only by the policy engine to enforce floors."""

    # india
    hsn_code: str = ""
    gst_rate_bp: BasisPoints = 0

    # trade terms
    unit: str = ""
    moq: int = 1
    """Minimum order quantity."""
    stock_qty: int = 0
    stock_age_days: int = 0
    """How long this stock has been sitting. Drives the ageing discount ladder."""
    availability: Availability = Availability.IN_STOCK

    # merchandising
    brand: str = ""
    category: str = ""
    territories: list[str] = Field(default_factory=list)
    """Where this may be sold. Empty means unrestricted."""

    # provenance
    source_ref: str = ""
    """Where this came from -- 'pricelist-a.pdf p3 row 12'. Makes extraction auditable."""

    @field_validator("sku")
    @classmethod
    def _sku_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("sku cannot be blank")
        return v.strip()

    @property
    def margin_bp(self) -> BasisPoints:
        return margin_bp(self.list_price_paise, self.cost_price_paise)

    @property
    def is_sellable(self) -> bool:
        return (
            self.availability is Availability.IN_STOCK
            and self.stock_qty > 0
            and self.list_price_paise > 0
        )


class Gap(BaseModel):
    """One specific, fixable reason a SKU underperforms with an AI buyer."""

    sku: str
    field: str
    severity: Severity
    why: str
    """What an AI buyer does about it. Concrete, not 'improves quality'."""
    how_to_fix: str
    revenue_impact_paise: Paise = 0
    """Estimated annual revenue at risk. See `score_gaps` for how this is derived."""

    def __str__(self) -> str:
        return (
            f"[{self.severity.value}] {self.sku}.{self.field} "
            f"({format_inr(self.revenue_impact_paise)}/yr): {self.why}"
        )


# How much of a SKU's annual revenue each severity puts at risk. These are stated
# assumptions, not measurements, and the README says so -- a blocking gap forfeits the
# line entirely, a degrading one costs roughly a third to a better-described rival.
_SEVERITY_WEIGHT_BP: dict[Severity, BasisPoints] = {
    Severity.BLOCKING: 10_000,
    Severity.DEGRADING: 3_300,
    Severity.ADVISORY: 500,
}

# Annual volume assumed when a SKU has no sales history, expressed as turns of current
# stock. Deliberately conservative: overstating impact would make the ranking dishonest.
_ASSUMED_ANNUAL_TURNS = 4


def annual_revenue_estimate(p: Product) -> Paise:
    """A crude but stated-out-loud estimate of what a SKU is worth in a year.

    There is no sales history in a price-list PDF, so this cannot be measured. It is
    modelled as `list price x stock on hand x assumed turns`, which at least ranks a
    ₹40,000 machine above a ₹40 washer -- and ranking is all it is used for.
    """
    units = max(p.stock_qty, p.moq, 1)
    return p.list_price_paise * units * _ASSUMED_ANNUAL_TURNS


def validate_product(p: Product) -> list[Gap]:
    """Find every gap in one SKU. Pure, deterministic, no model call.

    This is the first of the places where an LLM was deliberately not used. Whether a price
    is missing is a fact, not a judgement, and a model asked to decide it would sometimes
    hallucinate one. The LLM's job is upstream -- reading the PDF. Deciding what is broken
    is arithmetic.
    """
    gaps: list[Gap] = []
    rev = annual_revenue_estimate(p)

    def add(field: str, sev: Severity, why: str, fix: str) -> None:
        gaps.append(
            Gap(
                sku=p.sku,
                field=field,
                severity=sev,
                why=why,
                how_to_fix=fix,
                revenue_impact_paise=apply_bp(rev, _SEVERITY_WEIGHT_BP[sev]),
            )
        )

    if p.list_price_paise <= 0:
        add(
            "list_price_paise",
            Severity.BLOCKING,
            "No price. A buying agent cannot compare or quote this, so it is skipped silently.",
            "Set a GST-inclusive list price in paise.",
        )

    if not p.title.strip():
        add(
            "title",
            Severity.BLOCKING,
            "No title. The SKU cannot be matched to any search intent.",
            "Give it the name a customer would type.",
        )

    if p.cost_price_paise <= 0:
        add(
            "cost_price_paise",
            Severity.BLOCKING,
            "No cost price, so no margin floor can be enforced. Negotiation is refused "
            "outright on this SKU rather than risk selling below cost.",
            "Set landed cost. It is never published -- only the floor is derived from it.",
        )
    elif p.list_price_paise > 0 and p.margin_bp < 0:
        add(
            "cost_price_paise",
            Severity.BLOCKING,
            f"List price is below cost ({format_inr(p.list_price_paise)} < "
            f"{format_inr(p.cost_price_paise)}). Every sale loses money.",
            "Correct whichever of the two is wrong. Usually the cost was entered per-case "
            "and the price per-unit.",
        )

    if not p.hsn_code:
        add(
            "hsn_code",
            Severity.DEGRADING,
            "No HSN code. A B2B buyer cannot raise a compliant purchase order or claim "
            "input tax credit, so procurement agents filter the SKU out.",
            "Add the 4, 6 or 8 digit HSN for this category.",
        )
    elif not HSN_RE.match(p.hsn_code):
        add(
            "hsn_code",
            Severity.DEGRADING,
            f"HSN '{p.hsn_code}' is not 4, 6 or 8 digits, so it will fail GST validation "
            "downstream.",
            "Correct it -- this is usually an OCR slip, a stray space or a dropped digit.",
        )

    if p.gst_rate_bp not in VALID_GST_BP:
        add(
            "gst_rate_bp",
            Severity.DEGRADING,
            f"GST rate {p.gst_rate_bp / 100:g}% is not a real slab, so any invoice total "
            "computed from it is wrong.",
            "Use one of 0, 0.5, 3, 5, 12, 18 or 28 percent.",
        )

    if not p.unit.strip():
        add(
            "unit",
            Severity.DEGRADING,
            "No unit of measure. 'Price 450' is ambiguous between per-piece, per-kg and "
            "per-box, and an agent will not guess -- it asks, or it leaves.",
            "State the selling unit: piece, kg, box of 50.",
        )

    if len(p.description.strip()) < 20:
        add(
            "description",
            Severity.DEGRADING,
            "Description too thin to answer a specification question, so the SKU loses to a "
            "competitor whose listing does.",
            "One or two sentences covering material, size and fit.",
        )

    if p.stock_qty <= 0 and p.availability is Availability.IN_STOCK:
        add(
            "stock_qty",
            Severity.BLOCKING,
            "Marked in stock with zero quantity. A reservation against it will fail at "
            "checkout, after the buyer has committed.",
            "Set the real quantity, or mark it out of stock or backorder.",
        )

    if not p.brand.strip():
        add(
            "brand",
            Severity.ADVISORY,
            "No brand, so the SKU never surfaces for brand-qualified searches.",
            "Add the brand, or the merchant's own name for unbranded goods.",
        )

    if not p.category.strip():
        add(
            "category",
            Severity.ADVISORY,
            "No category, so browse and comparison queries miss it.",
            "Add a category.",
        )

    return gaps


def score_gaps(products: list[Product]) -> list[Gap]:
    """Validate a whole catalog and rank every gap by revenue at risk.

    Ties break on severity, then SKU, so the ordering is stable across runs -- which matters
    because these numbers go into evidence and have to reproduce.
    """
    all_gaps = [g for p in products for g in validate_product(p)]
    order = {Severity.BLOCKING: 0, Severity.DEGRADING: 1, Severity.ADVISORY: 2}
    return sorted(
        all_gaps,
        key=lambda g: (-g.revenue_impact_paise, order[g.severity], g.sku, g.field),
    )


class CatalogHealth(BaseModel):
    """The headline a merchant sees after ingestion."""

    total_skus: int
    transactable_skus: int
    blocking_gaps: int
    degrading_gaps: int
    advisory_gaps: int
    revenue_at_risk_paise: Paise

    @property
    def transactable_pct(self) -> float:
        return 0.0 if not self.total_skus else 100.0 * self.transactable_skus / self.total_skus


def catalog_health(products: list[Product]) -> tuple[CatalogHealth, list[Gap]]:
    gaps = score_gaps(products)
    blocked = {g.sku for g in gaps if g.severity is Severity.BLOCKING}
    by_sev: dict[Severity, int] = {s: 0 for s in Severity}
    for g in gaps:
        by_sev[g.severity] += 1
    return (
        CatalogHealth(
            total_skus=len(products),
            transactable_skus=sum(1 for p in products if p.sku not in blocked),
            blocking_gaps=by_sev[Severity.BLOCKING],
            degrading_gaps=by_sev[Severity.DEGRADING],
            advisory_gaps=by_sev[Severity.ADVISORY],
            revenue_at_risk_paise=sum(g.revenue_impact_paise for g in gaps),
        ),
        gaps,
    )


__all__ = [
    "Availability",
    "CatalogHealth",
    "Gap",
    "Product",
    "Severity",
    "annual_revenue_estimate",
    "catalog_health",
    "score_gaps",
    "validate_product",
]
