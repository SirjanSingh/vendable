"""Payment terms as a price lever, and the MSMED Act as a hard limit on them.

Two separate things are tested here and they must not be confused.

The first is commercial: in Indian B2B the rate and the credit period are one negotiation,
so `2/10 Net 30` -- two percent off for paying inside ten days -- is a published entitlement
like a volume break, not something a buyer has to haggle for.

The second is statutory, and it is the reason this file exists. Under s.15 of the MSMED Act
a buyer owes a Udyam-registered micro or small supplier inside 45 days where there is a
written agreement, or 15 days where there is not. Section 16 charges compound interest at
three times the RBI bank rate on a breach, and since 1 April 2024 s.43B(h) disallows the
*buyer's* own deduction until it is actually paid. A buyer agent that negotiates Net 90 with
such a supplier therefore wins a discount that costs its principal more than it saves.

The exclusions carry as much weight as the rule. Medium enterprises are outside it, and Udyam
*traders* are outside 43B(h) -- it reaches manufacturers and service providers. A guard that
fired on every Indian merchant would be wrong, and wrong in the direction that loses sales.
"""

from __future__ import annotations

import pytest

from vendable.core.money import margin_bp, rupees
from vendable.policy.engine import (
    EnterpriseClass,
    LadderRung,
    LineRequest,
    MerchantPolicy,
    PolicyEngine,
    TermsRung,
    UdyamActivity,
    ViolationCode,
)

MERCHANT = "acme-fasteners"


def ask(qty: int, days: int | None = None, price: str | None = None) -> LineRequest:
    return LineRequest(
        sku="BOLT-M8",
        qty=qty,
        payment_terms_days=days,
        offered_unit_price_paise=rupees(price) if price is not None else None,
    )


# --- fixtures ----------------------------------------------------------------------
#
# Deliberately local rather than in conftest: the shared `policy` fixture has no terms
# ladder, which keeps every pre-existing test evaluating at exactly the numbers it was
# written against.


LADDER_2_10_NET_30 = [
    TermsRung(within_days=0, grants_bp=300, label="cash with order -> 3%"),
    TermsRung(within_days=10, grants_bp=200, label="pay within 10 days -> 2%"),
    TermsRung(within_days=30, grants_bp=0, label="net 30 -> list"),
]


@pytest.fixture
def terms_policy() -> MerchantPolicy:
    """A distributor. Trades on 2/10 Net 30, will stretch to 60 days, no MSMED exposure."""
    return MerchantPolicy(
        merchant_id=MERCHANT,
        margin_floor_bp=1500,
        max_total_discount_bp=2000,
        volume_ladder=[
            LadderRung(threshold=100, grants_bp=500, label="100+ units -> 5%"),
            LadderRung(threshold=500, grants_bp=1000, label="500+ units -> 10%"),
        ],
        payment_terms_ladder=LADDER_2_10_NET_30,
        default_payment_terms_days=30,
        max_credit_days=60,
        udyam_registered=False,
    )


@pytest.fixture
def msme_policy() -> MerchantPolicy:
    """A Udyam-registered small manufacturer. s.15 caps its credit at 45 days."""
    return MerchantPolicy(
        merchant_id="shakti-forgings",
        margin_floor_bp=1500,
        max_total_discount_bp=2000,
        payment_terms_ladder=LADDER_2_10_NET_30,
        default_payment_terms_days=30,
        max_credit_days=90,  # commercially willing; the statute is what stops it
        udyam_registered=True,
        enterprise_class=EnterpriseClass.SMALL,
        udyam_activity=UdyamActivity.MANUFACTURER,
        written_agreement=True,
    )


# --- terms are a price lever -------------------------------------------------------


def test_paying_sooner_is_never_worth_less(terms_policy, bolt):
    """Cash >= Net 10 >= Net 30. A buyer must never be punished for paying earlier."""
    engine = PolicyEngine(terms_policy)
    cash = engine.evaluate(bolt, ask(50, days=0))
    ten = engine.evaluate(bolt, ask(50, days=10))
    thirty = engine.evaluate(bolt, ask(50, days=30))

    assert cash.payment_terms_bp == 300
    assert ten.payment_terms_bp == 200
    assert thirty.payment_terms_bp == 0
    assert cash.best_unit_price_paise <= ten.best_unit_price_paise
    assert ten.best_unit_price_paise <= thirty.best_unit_price_paise


def test_a_window_is_earned_by_falling_inside_it_not_by_clearing_it(terms_policy, bolt):
    """The inverse of the volume ladder. Paying in 5 days earns the 10-day rung."""
    engine = PolicyEngine(terms_policy)
    assert engine.evaluate(bolt, ask(50, days=5)).payment_terms_bp == 200
    # 20 days is inside Net 30 but outside the 10-day window, so it earns nothing.
    assert engine.evaluate(bolt, ask(50, days=20)).payment_terms_bp == 0


def test_terms_discount_is_entitled_not_discretionary(terms_policy, bolt):
    """2/10 Net 30 is published, so it is owed without anyone having to haggle for it."""
    d = PolicyEngine(terms_policy).evaluate(bolt, ask(500, days=10))
    # 10% volume + 2% terms, both published.
    assert d.entitled_bp == 1200
    assert d.entitled_unit_price_paise == d.best_unit_price_paise


def test_terms_and_volume_stack_but_respect_the_cap(terms_policy, bolt):
    """Independent reasons to concede stack; max_total_discount_bp is still the backstop."""
    bolt.stock_age_days = 200  # + 5% ageing
    terms_policy.age_ladder = [LadderRung(threshold=180, grants_bp=500, label="180d -> 5%")]
    d = PolicyEngine(terms_policy).evaluate(bolt, ask(500, days=0))
    assert d.granted_bp == 1800  # 10% volume + 5% ageing + 3% cash
    assert d.max_discount_bp == 1800  # under the 20% cap
    assert d.entitled_bp <= d.max_discount_bp


def test_a_terms_discount_cannot_breach_the_margin_floor(terms_policy, bolt):
    """The floor outranks every ladder, including this one."""
    terms_policy.margin_floor_bp = 2500
    d = PolicyEngine(terms_policy).evaluate(bolt, ask(500, days=0))
    assert margin_bp(d.best_unit_price_paise, bolt.cost_price_paise) >= 2500


def test_no_ladder_means_terms_move_nothing(policy, bolt):
    """The shared fixture has no terms ladder. Asking for cash must change no number."""
    engine = PolicyEngine(policy)
    assert engine.evaluate(bolt, ask(500, days=0)).payment_terms_bp == 0
    assert (
        engine.evaluate(bolt, ask(500, days=0)).best_unit_price_paise
        == engine.evaluate(bolt, ask(500)).best_unit_price_paise
    )


def test_terms_default_to_the_merchants_own_when_unstated(terms_policy, bolt):
    d = PolicyEngine(terms_policy).evaluate(bolt, ask(50))
    assert d.payment_terms_days == 30


# --- the merchant's own commercial ceiling -----------------------------------------


def test_credit_beyond_the_merchants_ceiling_is_refused(terms_policy, bolt):
    d = PolicyEngine(terms_policy).evaluate(bolt, ask(50, days=90))
    assert not d.allowed
    v = next(v for v in d.violations if v.code is ViolationCode.CREDIT_TERMS_EXCEEDED)
    assert "60" in v.message


def test_credit_exactly_at_the_ceiling_is_allowed(terms_policy, bolt):
    """Inclusive, like the mandate cap. An off-by-one here refuses good business."""
    assert PolicyEngine(terms_policy).evaluate(bolt, ask(50, days=60)).allowed


# --- MSMED s.15: the statutory limit -----------------------------------------------


def test_small_manufacturer_refuses_net_60(msme_policy, bolt):
    """The scene this whole change exists for."""
    d = PolicyEngine(msme_policy).evaluate(bolt, ask(50, days=60))
    assert not d.allowed
    assert ViolationCode.MSMED_LIMIT_EXCEEDED in {v.code for v in d.violations}


def test_the_msmed_refusal_explains_itself_and_points_somewhere(msme_policy, bolt):
    """A refusal a buyer agent cannot act on costs a round trip. Name the statute, the
    consequence, and the terms that would work."""
    d = PolicyEngine(msme_policy).evaluate(bolt, ask(50, days=60))
    msg = next(v for v in d.violations if v.code is ViolationCode.MSMED_LIMIT_EXCEEDED).message
    assert "45" in msg
    assert "43B(h)" in msg  # the consequence that lands on the buyer
    assert "three times" in msg.lower() or "3x" in msg.lower()


def test_forty_five_days_exactly_is_allowed(msme_policy, bolt):
    """s.15 says the period 'shall not exceed' 45 days. 45 itself is compliant."""
    assert PolicyEngine(msme_policy).evaluate(bolt, ask(50, days=45)).allowed


def test_without_a_written_agreement_the_limit_is_fifteen_days(msme_policy, bolt):
    msme_policy.written_agreement = False
    engine = PolicyEngine(msme_policy)
    assert engine.evaluate(bolt, ask(50, days=15)).allowed
    d = engine.evaluate(bolt, ask(50, days=30))
    assert not d.allowed
    msg = next(v for v in d.violations if v.code is ViolationCode.MSMED_LIMIT_EXCEEDED).message
    assert "15" in msg


# --- MSMED: who it does NOT reach --------------------------------------------------


def test_a_udyam_trader_is_not_constrained(msme_policy, bolt):
    """43B(h) reaches manufacturers and service providers. Traders are excluded, and a
    guard that fired on them would refuse business the law permits."""
    msme_policy.udyam_activity = UdyamActivity.TRADER
    assert msme_policy.statutory_max_credit_days() is None
    assert PolicyEngine(msme_policy).evaluate(bolt, ask(50, days=60)).allowed


def test_a_medium_enterprise_is_not_constrained(msme_policy, bolt):
    """The Act's payment protection covers micro and small only."""
    msme_policy.enterprise_class = EnterpriseClass.MEDIUM
    assert msme_policy.statutory_max_credit_days() is None
    assert PolicyEngine(msme_policy).evaluate(bolt, ask(50, days=60)).allowed


def test_an_unregistered_merchant_is_not_constrained(msme_policy, bolt):
    """Protection follows Udyam registration, not size alone."""
    msme_policy.udyam_registered = False
    assert msme_policy.statutory_max_credit_days() is None
    assert PolicyEngine(msme_policy).evaluate(bolt, ask(50, days=60)).allowed


def test_a_service_provider_is_constrained(msme_policy, bolt):
    msme_policy.udyam_activity = UdyamActivity.SERVICE
    assert msme_policy.statutory_max_credit_days() == 45


# --- the gate is hard --------------------------------------------------------------


def test_no_discount_authority_rescues_a_statutory_breach(msme_policy, bolt):
    """Ordering 5,000 units and offering full list price must still be refused. This is a
    gate, not a price adjustment."""
    d = PolicyEngine(msme_policy).evaluate(bolt, ask(5_000, days=90, price="100"))
    assert not d.allowed
    assert ViolationCode.MSMED_LIMIT_EXCEEDED in {v.code for v in d.violations}


def test_the_statutory_limit_is_reported_on_every_decision(msme_policy, terms_policy, bolt):
    """A buyer agent should be able to read the constraint off an allowed quote, not only
    discover it by being refused."""
    allowed = PolicyEngine(msme_policy).evaluate(bolt, ask(50, days=30))
    assert allowed.allowed
    assert allowed.statutory_max_credit_days == 45
    assert PolicyEngine(terms_policy).evaluate(bolt, ask(50)).statutory_max_credit_days is None
