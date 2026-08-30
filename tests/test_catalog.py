"""Catalog validation and money arithmetic.

Deciding what is broken about a SKU is arithmetic, not judgement -- which is why there is no
model call anywhere near it. These tests are what make that claim checkable.
"""

from __future__ import annotations

import pytest

from vendable.core.catalog import Catalog
from vendable.core.models import (
    Availability,
    Product,
    Severity,
    catalog_health,
    score_gaps,
    validate_product,
)
from vendable.core.money import (
    apply_bp,
    discount_bp,
    format_inr,
    gst_split,
    margin_bp,
    price_at_margin,
    rupees,
)


def fields(gaps) -> set[str]:
    return {g.field for g in gaps}


# --- gap detection -----------------------------------------------------------------


def test_a_healthy_sku_has_no_blocking_gaps(bolt):
    assert not [g for g in validate_product(bolt) if g.severity is Severity.BLOCKING]


def test_missing_price_blocks(bolt):
    bolt.list_price_paise = 0
    gaps = [g for g in validate_product(bolt) if g.severity is Severity.BLOCKING]
    assert "list_price_paise" in fields(gaps)


def test_selling_below_cost_blocks(bolt):
    bolt.cost_price_paise = rupees("150")
    gap = next(g for g in validate_product(bolt) if g.field == "cost_price_paise")
    assert gap.severity is Severity.BLOCKING
    assert "₹100.00" in gap.why and "₹150.00" in gap.why


def test_missing_cost_blocks_because_no_floor_can_be_enforced(bolt):
    bolt.cost_price_paise = 0
    gap = next(g for g in validate_product(bolt) if g.field == "cost_price_paise")
    assert gap.severity is Severity.BLOCKING
    assert "below cost" in gap.why


def test_in_stock_with_zero_quantity_blocks(bolt):
    """The nastiest one: it fails at checkout, after the buyer has committed."""
    bolt.stock_qty = 0
    bolt.availability = Availability.IN_STOCK
    gap = next(g for g in validate_product(bolt) if g.field == "stock_qty")
    assert gap.severity is Severity.BLOCKING


@pytest.mark.parametrize("hsn", ["", "12x4", "123", "123456789"])
def test_bad_hsn_is_flagged(bolt, hsn):
    bolt.hsn_code = hsn
    assert "hsn_code" in fields(validate_product(bolt))


@pytest.mark.parametrize("hsn", ["7318", "731815", "73181500"])
def test_valid_hsn_lengths_pass(bolt, hsn):
    bolt.hsn_code = hsn
    assert "hsn_code" not in fields(validate_product(bolt))


def test_a_gst_rate_that_is_not_a_real_slab_is_flagged(bolt):
    bolt.gst_rate_bp = 1700
    assert "gst_rate_bp" in fields(validate_product(bolt))


def test_every_gap_says_what_to_do_about_it(bolt):
    """A finding with no remedy is a complaint."""
    bolt.hsn_code = ""
    bolt.unit = ""
    bolt.brand = ""
    for gap in validate_product(bolt):
        assert gap.how_to_fix.strip()
        assert gap.why.strip()


# --- ranking -----------------------------------------------------------------------


def test_gaps_are_ranked_by_revenue_at_risk():
    """A merchant with forty broken SKUs needs to know which three to fix first."""
    cheap = Product(sku="CHEAP", title="Washer", list_price_paise=rupees("2"), stock_qty=10)
    dear = Product(sku="DEAR", title="Lathe", list_price_paise=rupees("400000"), stock_qty=10)
    ranked = score_gaps([cheap, dear])
    assert ranked[0].sku == "DEAR"


def test_ranking_is_stable_across_runs():
    """These numbers go into evidence, so they have to reproduce exactly."""
    products = [
        Product(sku=f"S{i}", title="", list_price_paise=rupees(str(100 + i)), stock_qty=5)
        for i in range(20)
    ]
    first = [(g.sku, g.field) for g in score_gaps(products)]
    for _ in range(5):
        assert [(g.sku, g.field) for g in score_gaps(products)] == first


def test_catalog_health_counts_blocked_skus_not_blocked_gaps(bolt):
    """Two blocking gaps on one SKU is still one untransactable SKU."""
    broken = Product(sku="B", title="", list_price_paise=0, stock_qty=0)
    health, _ = catalog_health([bolt, broken])
    assert health.total_skus == 2
    assert health.transactable_skus == 1
    assert health.transactable_pct == 50.0
    assert health.blocking_gaps >= 2


# --- money ------------------------------------------------------------------------


def test_rupees_never_builds_a_float():
    assert rupees("1234.56") == 123456
    assert rupees("0.01") == 1
    assert rupees("0.005") == 1  # half-up, pinned


def test_indian_digit_grouping():
    assert format_inr(rupees("1234567.89")) == "₹12,34,567.89"
    assert format_inr(rupees("100")) == "₹100.00"
    assert format_inr(-1) == "-₹0.01"


def test_price_at_margin_always_clears_its_own_floor():
    """The counter-offer must satisfy the rule it was derived from, at every cost."""
    for cost in range(1, 5000, 37):
        for floor in (500, 1500, 2500, 4000):
            assert margin_bp(price_at_margin(cost, floor), cost) >= floor


def test_a_100_percent_margin_floor_is_rejected_rather_than_silently_wrong():
    with pytest.raises(ValueError, match="unsatisfiable"):
        price_at_margin(1000, 10_000)


def test_discount_bp_rounds_against_the_buyer():
    """A discount between two basis points counts as the deeper one, so no policy floor can
    be crossed by a rounding artefact."""
    assert discount_bp(rupees("3"), rupees("3") - 1) == 34  # 33.3...bp -> 34


def test_gst_split_always_reconstitutes_the_total():
    for gross in range(1, 20_000, 91):
        for rate in (500, 1200, 1800, 2800):
            base, tax = gst_split(gross, rate)
            assert base + tax == gross
            assert base >= 0 and tax >= 0


def test_gst_split_on_a_clean_number():
    assert gst_split(rupees("118"), 1800) == (rupees("100"), rupees("18"))


def test_apply_bp_rounds_half_up():
    assert apply_bp(100_000, 1800) == 18_000
    assert apply_bp(1, 5_000) == 1  # 0.5 paise -> 1
    assert apply_bp(1, 4_999) == 0


# --- merchant scoping --------------------------------------------------------------
#
# The products table has carried a merchant_id column and an index on it from the start,
# but every read ignored it. That was invisible while there was one merchant and became a
# correctness bug the moment there were two: a second storefront sharing the same SQLite
# file would serve the first merchant's SKUs, priced against its own policy.


def _scoped(tmp_path, merchant, products):
    cat = Catalog(tmp_path / "shared.db", merchant_id=merchant)
    cat.put_many(products)
    return cat


def test_two_merchants_on_one_file_do_not_see_each_other(tmp_path, bolt):
    acme = _scoped(tmp_path, "acme-fasteners", [bolt])

    other = bolt.model_copy(update={"sku": "SF-BOLT-M8", "list_price_paise": 9200})
    shakti = _scoped(tmp_path, "shakti-forgings", [other])

    assert len(acme) == 1
    assert len(shakti) == 1
    assert [p.sku for p in acme.all()] == ["BOLT-M8"]
    assert [p.sku for p in shakti.all()] == ["SF-BOLT-M8"]


def test_get_does_not_reach_across_merchants(tmp_path, bolt):
    _scoped(tmp_path, "acme-fasteners", [bolt])
    shakti = Catalog(tmp_path / "shared.db", merchant_id="shakti-forgings")
    assert shakti.get("BOLT-M8") is None


def test_search_does_not_reach_across_merchants(tmp_path, bolt):
    _scoped(tmp_path, "acme-fasteners", [bolt])
    shakti = Catalog(tmp_path / "shared.db", merchant_id="shakti-forgings")
    assert shakti.search("bolt") == []


def test_stock_map_is_scoped(tmp_path, bolt):
    """Reservations are checked against this. An unscoped stock map would let one merchant
    hold stock it does not own."""
    _scoped(tmp_path, "acme-fasteners", [bolt])
    shakti = Catalog(tmp_path / "shared.db", merchant_id="shakti-forgings")
    assert shakti.stock_map() == {}


def test_an_unscoped_catalog_still_sees_everything(tmp_path, bolt):
    """Tests and the CLI build catalogs with no merchant. That must keep meaning 'all'."""
    _scoped(tmp_path, "acme-fasteners", [bolt])
    assert len(Catalog(tmp_path / "shared.db")) == 1
