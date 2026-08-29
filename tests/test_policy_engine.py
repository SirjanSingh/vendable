"""The policy engine bounds the negotiation agent.

If these tests are wrong, a language model can be talked into selling below cost. They are
the reason the sales agent is safe to let speak.
"""

from __future__ import annotations

from vendable.core.models import Availability, Product
from vendable.core.money import margin_bp, rupees
from vendable.policy.engine import LineRequest, PolicyEngine, ViolationCode


def ask(qty: int, price: str | None = None, territory: str = "") -> LineRequest:
    return LineRequest(
        sku="BOLT-M8",
        qty=qty,
        offered_unit_price_paise=rupees(price) if price is not None else None,
        territory=territory,
    )


# --- the floor holds ---------------------------------------------------------------


def test_below_margin_floor_is_refused(engine, bolt):
    """₹70 cost, 15% floor -> nothing below ₹82.36 is sellable at any volume."""
    d = engine.evaluate(bolt, ask(1000, "80"))
    assert not d.allowed
    assert ViolationCode.BELOW_MARGIN_FLOOR in {v.code for v in d.violations}


def test_the_counter_offer_actually_clears_the_floor(engine, bolt):
    """The engine's own best price must satisfy its own rule. Rounding included."""
    d = engine.evaluate(bolt, ask(1000, "10"))
    assert margin_bp(d.best_unit_price_paise, bolt.cost_price_paise) >= 1500


def test_refusal_names_the_lowest_workable_price(engine, bolt):
    """A refusal that does not say what would work costs the agent another round trip."""
    d = engine.evaluate(bolt, ask(1000, "50"))
    floor_msg = next(v for v in d.violations if v.code is ViolationCode.BELOW_MARGIN_FLOOR)
    assert "lowest price that clears it is" in floor_msg.message
    assert "15.00%" in floor_msg.message


def test_stacked_ladders_cannot_breach_the_floor(engine, bolt):
    """Volume 10% + ageing 5% = 15%, which on a ₹100/₹70 line is still above the floor --
    but the margin floor, not the ladder, must be what decides the final number."""
    bolt.stock_age_days = 200  # unlocks the 5% ageing rung
    d = engine.evaluate(bolt, ask(500))
    assert d.granted_bp == 1500
    assert margin_bp(d.best_unit_price_paise, bolt.cost_price_paise) >= 1500


def test_margin_floor_beats_a_generous_ladder(engine, bolt, policy):
    """When the ladders authorise more than the margin allows, margin wins."""
    policy.margin_floor_bp = 2500
    bolt.stock_age_days = 200
    d = PolicyEngine(policy).evaluate(bolt, ask(500))
    # 15% ladder would give ₹85; a 25% floor on ₹70 cost needs ₹93.34.
    assert d.best_unit_price_paise == rupees("93.34")
    assert margin_bp(d.best_unit_price_paise, bolt.cost_price_paise) >= 2500


# --- discount authority ------------------------------------------------------------


def test_rungs_within_one_ladder_do_not_stack(engine, bolt):
    """'100+ gets 5%, 500+ gets 10%' means the 500-unit buyer gets 10%, not 15%."""
    assert engine.evaluate(bolt, ask(500)).granted_bp == 1000  # the 10% rung, not 5% + 10%
    assert engine.evaluate(bolt, ask(100)).granted_bp == 500  # only the 5% rung clears


def test_ladders_from_different_dimensions_do_stack(engine, bolt):
    bolt.stock_age_days = 100  # 3% ageing rung
    assert engine.evaluate(bolt, ask(500)).granted_bp == 1300  # 10% volume + 3% age


def test_max_total_discount_caps_the_stack(engine, bolt, policy):
    policy.max_total_discount_bp = 1200
    bolt.stock_age_days = 200
    d = PolicyEngine(policy).evaluate(bolt, ask(500))
    assert d.granted_bp == 1500
    assert d.max_discount_bp == 1200
    assert any("capped at 1200bp" in r for r in d.rungs_applied)


def test_discount_beyond_authority_is_refused_with_a_route_forward(engine, bolt):
    d = engine.evaluate(bolt, ask(100, "88"))  # asks 12%, only 5% authorised at qty 100
    assert not d.allowed
    v = next(v for v in d.violations if v.code is ViolationCode.DISCOUNT_EXCEEDS_LADDER)
    assert "500+ units for 10.00%" in v.message  # names the next rung


def test_list_price_is_always_acceptable(engine, bolt):
    assert engine.evaluate(bolt, ask(10, "100")).allowed


def test_paying_above_list_is_not_a_discount(engine, bolt):
    assert engine.evaluate(bolt, ask(10, "120")).allowed


# --- hard gates --------------------------------------------------------------------


def test_below_moq_is_refused(engine, bolt):
    d = engine.evaluate(bolt, ask(5))
    assert not d.allowed
    v = next(v for v in d.violations if v.code is ViolationCode.BELOW_MOQ)
    assert "at least 10" in v.message


def test_more_than_stock_is_refused(engine, bolt):
    d = engine.evaluate(bolt, ask(9_999))
    assert ViolationCode.INSUFFICIENT_STOCK in {v.code for v in d.violations}


def test_out_of_stock_is_refused(engine, bolt):
    bolt.availability = Availability.OUT_OF_STOCK
    assert not engine.evaluate(bolt, ask(100)).allowed


def test_territory_outside_the_allowlist_is_refused(engine, bolt):
    d = engine.evaluate(bolt, ask(100, territory="IN-TN"))
    assert ViolationCode.TERRITORY_NOT_ALLOWED in {v.code for v in d.violations}
    assert engine.evaluate(bolt, ask(100, territory="IN-KA")).allowed


def test_no_cost_price_refuses_negotiation_rather_than_guessing(engine):
    """Without a cost basis there is no floor, so the safe answer is 'list price only'."""
    p = Product(
        sku="X",
        title="Mystery item",
        description="An item with no cost price recorded anywhere.",
        list_price_paise=rupees("100"),
        stock_qty=10,
    )
    d = engine.evaluate(p, LineRequest(sku="X", qty=1))
    assert not d.allowed
    assert ViolationCode.NO_COST_BASIS in {v.code for v in d.violations}


# --- determinism -------------------------------------------------------------------


def test_the_same_line_always_gets_the_same_answer(engine, bolt):
    """Evidence numbers have to reproduce. This is what makes 60 batch runs meaningful."""
    results = {engine.evaluate(bolt, ask(500, "90")).best_unit_price_paise for _ in range(50)}
    assert len(results) == 1


def test_category_floor_overrides_the_global_one(engine, bolt, policy):
    policy.category_margin_floor_bp = {"fasteners": 2800}
    d = PolicyEngine(policy).evaluate(bolt, ask(500))
    assert margin_bp(d.best_unit_price_paise, bolt.cost_price_paise) >= 2800
