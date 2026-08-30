"""The discovery surfaces an agent reads before it calls anything.

This file exists because of a near miss. A syntax error was introduced into
`vendable/publish/surfaces.py` and the whole suite -- 179 tests at the time -- stayed green,
because nothing imported the module. The published surfaces are the first thing a buyer's
agent sees and the last thing anyone thinks to test, so at minimum they must be exercised.
"""

from __future__ import annotations

import json

import pytest

from vendable.policy.engine import EnterpriseClass, MerchantPolicy, TermsRung, UdyamActivity
from vendable.publish.surfaces import (
    llms_txt,
    product_jsonld,
    storefront_jsonld,
    well_known,
)

BASE = "https://acme.test"


@pytest.fixture
def public_policy() -> dict:
    """Shaped like `Storefront.public_policy()`, which is what the builders consume."""
    return {
        "merchant_id": "acme-fasteners",
        "currency": "INR",
        "prices_include_gst": True,
        "max_discount_pct": 20.0,
        "volume_breaks": [{"min_qty": 100, "discount_pct": 5.0}],
        "clearance_policy": [{"stock_age_days_min": 90, "extra_discount_pct": 3.0}],
        "payment_terms": {
            "default": "net 30",
            "max_credit_days": 60,
            "early_payment_discounts": [
                {"pay_within_days": 0, "discount_pct": 3.0, "label": "cash"},
                {"pay_within_days": 10, "discount_pct": 2.0, "label": "2/10"},
                {"pay_within_days": 30, "discount_pct": 0.0, "label": "net 30"},
            ],
        },
        "territories": ["IN-KA"],
        "note": "rules, not persuasion",
    }


def test_every_surface_builds(bolt, public_policy):
    """The smoke test that would have caught the syntax error."""
    assert product_jsonld(bolt, base_url=BASE, merchant_id="acme-fasteners")["@type"]
    assert storefront_jsonld([bolt], base_url=BASE, merchant_id="acme-fasteners")
    assert well_known(base_url=BASE, merchant_id="acme-fasteners", product_count=1)
    assert llms_txt([bolt], public_policy, base_url=BASE, merchant_id="acme-fasteners")


def test_llms_txt_publishes_the_terms_ladder(bolt, public_policy):
    txt = llms_txt([bolt], public_policy, base_url=BASE, merchant_id="acme-fasteners")
    assert "## Payment terms" in txt
    assert "cash with order for 3.0%" in txt  # not "within 0 days"
    assert "pay within 10 days for 2.0%" in txt
    # A zero-value rung is the baseline, not an offer, so it must not be advertised.
    assert "for 0.0%" not in txt


def test_llms_txt_says_terms_are_bound_to_the_quote(bolt, public_policy):
    """A buyer that does not know terms are hashed will try to change them and waste a turn."""
    txt = llms_txt([bolt], public_policy, base_url=BASE, merchant_id="acme-fasteners")
    assert "cart hash" in txt


def test_a_merchant_outside_the_act_publishes_only_its_own_ceiling(bolt, public_policy):
    txt = llms_txt([bolt], public_policy, base_url=BASE, merchant_id="acme-fasteners")
    assert "Credit beyond 60 days is refused." in txt
    assert "MSMED" not in txt


def test_an_msme_supplier_publishes_the_statutory_limit(bolt, public_policy):
    """Publishing it is the point: it is a rule, not a secret like the margin floor."""
    public_policy["payment_terms"]["statutory_max_credit_days"] = 45
    public_policy["payment_terms"]["statutory_basis"] = "Under s.15 of the MSMED Act ..."
    txt = llms_txt([bolt], public_policy, base_url=BASE, merchant_id="shakti-forgings")
    assert "cannot grant more than 45 days" in txt
    assert "not the" in txt and "merchant's to waive" in txt


def test_the_margin_floor_is_never_published(bolt, public_policy):
    """The one number that must not appear on any surface."""
    surfaces = json.dumps(
        [
            product_jsonld(bolt, base_url=BASE, merchant_id="acme-fasteners"),
            storefront_jsonld([bolt], base_url=BASE, merchant_id="acme"),
            well_known(base_url=BASE, merchant_id="acme", product_count=1),
        ]
    ) + llms_txt([bolt], public_policy, base_url=BASE, merchant_id="acme")

    assert str(bolt.cost_price_paise) not in surfaces
    assert "margin_floor" not in surfaces
    assert "cost_price" not in surfaces


def test_public_policy_never_leaks_the_floor_or_the_cost(bolt):
    """Same guarantee, checked at the source rather than on the rendered surface."""
    from vendable.audit.chain import AuditChain
    from vendable.commerce.machine import CommerceMachine, CommerceStore
    from vendable.core.catalog import Catalog
    from vendable.core.storefront import Storefront
    from vendable.mandate.ap2 import generate_keypair
    from vendable.mandate.gate import MandateGate, SpendLedger

    _, pub = generate_keypair()
    policy = MerchantPolicy(
        merchant_id="shakti-forgings",
        margin_floor_bp=1800,
        payment_terms_ladder=[TermsRung(within_days=10, grants_bp=200)],
        udyam_registered=True,
        enterprise_class=EnterpriseClass.SMALL,
        udyam_activity=UdyamActivity.MANUFACTURER,
    )
    catalog = Catalog(":memory:", merchant_id="shakti-forgings")
    catalog.put_many([bolt])
    sf = Storefront(
        merchant_id="shakti-forgings",
        catalog=catalog,
        policy=policy,
        audit=AuditChain(":memory:"),
        commerce=CommerceMachine(CommerceStore(":memory:"), merchant_id="shakti-forgings"),
        gate=MandateGate(pub, merchant_id="shakti-forgings", ledger=SpendLedger(":memory:")),
    )

    published = json.dumps(sf.public_policy())
    assert "1800" not in published
    assert "margin_floor" not in published
    # But the statutory limit *is* published, because it is a rule a buyer should plan around.
    assert sf.public_policy()["payment_terms"]["statutory_max_credit_days"] == 45
