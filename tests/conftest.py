"""Shared fixtures.

Nothing here touches the network, the filesystem outside tmp, or any credential. That is a
hard rule for this suite: a test run must be reproducible on a machine that has never seen a
Razorpay key.
"""

from __future__ import annotations

import pytest

from vendable.core.models import Product
from vendable.core.money import rupees
from vendable.mandate.ap2 import generate_keypair
from vendable.mandate.gate import MandateGate, SpendLedger
from vendable.policy.engine import LadderRung, MerchantPolicy, PolicyEngine

MERCHANT = "acme-fasteners"


@pytest.fixture
def keypair() -> tuple[str, str]:
    return generate_keypair()


@pytest.fixture
def gate(keypair: tuple[str, str]) -> MandateGate:
    _, public_pem = keypair
    return MandateGate(public_pem, merchant_id=MERCHANT, ledger=SpendLedger(":memory:"))


@pytest.fixture
def bolt() -> Product:
    """A healthy, fully-specified SKU. ₹100 list, ₹70 cost -> 30% margin."""
    return Product(
        sku="BOLT-M8",
        title="Hex bolt M8 x 40",
        description="Hot dip galvanised mild steel hex bolt, 8mm diameter, 40mm length.",
        list_price_paise=rupees("100"),
        cost_price_paise=rupees("70"),
        hsn_code="73181500",
        gst_rate_bp=1800,
        unit="piece",
        moq=10,
        stock_qty=5_000,
        stock_age_days=30,
        brand="Tata",
        category="fasteners",
        territories=["IN-KA", "IN-MH"],
    )


@pytest.fixture
def policy() -> MerchantPolicy:
    """15% floor, volume ladder to 10%, ageing ladder to 5%, hard cap at 20%."""
    return MerchantPolicy(
        merchant_id=MERCHANT,
        margin_floor_bp=1500,
        max_total_discount_bp=2000,
        volume_ladder=[
            LadderRung(threshold=100, grants_bp=500, label="100+ units -> 5%"),
            LadderRung(threshold=500, grants_bp=1000, label="500+ units -> 10%"),
        ],
        age_ladder=[
            LadderRung(threshold=90, grants_bp=300, label="90+ days old -> 3%"),
            LadderRung(threshold=180, grants_bp=500, label="180+ days old -> 5%"),
        ],
    )


@pytest.fixture
def engine(policy: MerchantPolicy) -> PolicyEngine:
    return PolicyEngine(policy)
