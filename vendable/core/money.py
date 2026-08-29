"""Money and rates, as integers.

Every amount in this system is an integer count of **paise**. No float ever touches an
amount. A float rupee value is a rounding bug that has not fired yet, and the one place it
would fire is a cap comparison -- which is the single arithmetic this project claims to get
right.

Rates are integer **basis points** (1 bp = 0.01%), so 18% GST is 1800 and a 12.5% margin
floor is 1250. Same reasoning: percentages get multiplied by amounts, and a float percentage
puts a float back into the amount.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

Paise = int
"""An integer count of paise. 100 paise = 1 rupee."""

BasisPoints = int
"""An integer count of basis points. 10_000 bp = 100%."""

BP_SCALE: BasisPoints = 10_000


def rupees(amount: str | int) -> Paise:
    """Parse a rupee amount to paise. Accepts str to avoid a float ever existing.

    >>> rupees("1234.50")
    123450
    >>> rupees(1200)
    120000
    """
    d = Decimal(str(amount))
    return int((d * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def format_inr(paise: Paise) -> str:
    """Render paise for humans and for audit records. Indian digit grouping.

    >>> format_inr(123450)
    '₹1,234.50'
    >>> format_inr(1234567890)
    '₹1,23,45,678.90'
    """
    sign = "-" if paise < 0 else ""
    whole, frac = divmod(abs(paise), 100)
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return f"{sign}₹{s}.{frac:02d}"


def apply_bp(amount: Paise, bp: BasisPoints) -> Paise:
    """Take `bp` basis points of `amount`, rounded half-up to the nearest paisa.

    Rounding is pinned rather than left to chance because it decides cap-boundary cases.

    >>> apply_bp(100_000, 1800)   # 18% of ₹1000
    18000
    >>> apply_bp(333, 1250)       # 12.5% of ₹3.33 -> 0.416... paise
    42
    """
    q, r = divmod(amount * bp, BP_SCALE)
    # round half up on the remainder, without ever building a float
    return q + (1 if r * 2 >= BP_SCALE else 0)


def discount_bp(list_price: Paise, offered_price: Paise) -> BasisPoints:
    """How deep a discount `offered_price` represents against `list_price`, in bp.

    Rounded **up**, deliberately: a discount that lands between two basis points is treated
    as the deeper of the two, so the policy engine can never be talked past a floor by a
    rounding artefact. Errs against the merchant's counterparty, never against the merchant.

    >>> discount_bp(100_000, 90_000)
    1000
    >>> discount_bp(100_000, 100_001)   # a premium is not a discount
    0
    """
    if list_price <= 0:
        return 0
    delta = list_price - offered_price
    if delta <= 0:
        return 0
    q, r = divmod(delta * BP_SCALE, list_price)
    return q + (1 if r else 0)


def margin_bp(price: Paise, cost: Paise) -> BasisPoints:
    """Gross margin on `price`, in bp. Negative when selling below cost.

    Margin is taken **on the selling price**, the retail convention, not as a markup on cost.
    Stated explicitly because a policy that says "15% floor" means very different numbers
    under the two readings, and the merchant means this one.

    >>> margin_bp(100_000, 80_000)
    2000
    >>> margin_bp(100_000, 120_000)
    -2000
    """
    if price <= 0:
        return 0
    delta = price - cost
    # truncate toward zero so a margin is never reported better than it is
    return int(delta * BP_SCALE / price)


def price_at_margin(cost: Paise, floor_bp: BasisPoints) -> Paise:
    """The lowest price that still clears `floor_bp` margin on the selling price.

    Rounded **up**, so the returned price always satisfies the floor rather than landing a
    paisa under it. This is what the policy engine hands back as its counter-offer, so it
    has to be safe by construction.

    >>> price_at_margin(80_000, 2000)   # need 20% margin on ₹800 cost
    100000
    >>> margin_bp(price_at_margin(79_999, 2000), 79_999) >= 2000
    True
    """
    if floor_bp >= BP_SCALE:
        raise ValueError("a margin floor of 100% or more is unsatisfiable at any finite price")
    denom = BP_SCALE - floor_bp
    q, r = divmod(cost * BP_SCALE, denom)
    return q + (1 if r else 0)


def gst_split(gross_paise: Paise, gst_rate_bp: BasisPoints) -> tuple[Paise, Paise]:
    """Split a GST-inclusive amount into (taxable value, tax).

    Indian list prices are quoted inclusive far more often than not, so this is the split
    that actually gets used. The two halves are guaranteed to sum back to `gross_paise`
    exactly -- the tax is derived and the base is the remainder, never the other way round.

    >>> gst_split(118_000, 1800)
    (100000, 18000)
    >>> sum(gst_split(99_999, 1800)) == 99_999
    True
    """
    q, r = divmod(gross_paise * gst_rate_bp, BP_SCALE + gst_rate_bp)
    tax = q + (1 if r * 2 >= (BP_SCALE + gst_rate_bp) else 0)
    return gross_paise - tax, tax
