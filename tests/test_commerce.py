"""Quote -> reserve -> capture, and the window between them.

The cart-hash check at capture is the reason this state machine exists at all, so it gets
the most attention here.
"""

from __future__ import annotations

import pytest

from vendable.commerce.machine import (
    CommerceError,
    CommerceMachine,
    CommerceStore,
    QuoteState,
)
from vendable.core.money import rupees
from vendable.mandate.gate import Cart, CartLine

MERCHANT = "acme-fasteners"


class FakeClock:
    """Time as a variable, so expiry is tested by advancing it rather than sleeping."""

    def __init__(self, t: int = 1_000_000) -> None:
        self.t = t

    def __call__(self) -> int:
        return self.t

    def advance(self, seconds: int) -> None:
        self.t += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def machine(clock: FakeClock) -> CommerceMachine:
    return CommerceMachine(
        CommerceStore(":memory:"),
        merchant_id=MERCHANT,
        quote_ttl_s=900,
        reservation_ttl_s=600,
        clock=clock,
    )


def lines(qty: int = 10, price: str = "100") -> list[CartLine]:
    return [CartLine(sku="BOLT-M8", qty=qty, unit_price_paise=rupees(price))]


STOCK = {"BOLT-M8": 100}


# --- the happy path ----------------------------------------------------------------


def test_quote_reserve_capture(machine):
    q = machine.quote(lines())
    assert q.state is QuoteState.OPEN
    assert q.total_paise == rupees("1000")

    r = machine.reserve(q.quote_id, available=STOCK)
    assert r.state is QuoteState.RESERVED
    assert r.reserved_until_s is not None

    machine.begin_capture(q.quote_id, q.cart_hash)
    done = machine.complete_capture(q.quote_id, payment_id="pay_abc")
    assert done.state is QuoteState.CAPTURED
    assert done.payment_id == "pay_abc"


def test_capturing_releases_the_hold(machine):
    q = machine.quote(lines(qty=60))
    machine.reserve(q.quote_id, available=STOCK)
    assert machine.store.held_qty("BOLT-M8", machine.clock()) == 60
    machine.begin_capture(q.quote_id, q.cart_hash)
    machine.complete_capture(q.quote_id, payment_id="pay_1")
    assert machine.store.held_qty("BOLT-M8", machine.clock()) == 0


# --- the check the whole machine exists for ----------------------------------------


def test_capture_is_refused_when_the_cart_changed_since_authorisation(machine):
    """Cart tampering between quote and capture. Nothing may be charged."""
    q = machine.quote(lines())
    machine.reserve(q.quote_id, available=STOCK)

    other = Cart(merchant_id=MERCHANT, lines=lines(qty=10, price="1")).cart_hash()
    with pytest.raises(CommerceError, match="cart changed between authorisation and capture"):
        machine.begin_capture(q.quote_id, other)

    assert machine.store.get(q.quote_id).state is QuoteState.RESERVED  # untouched


def test_the_refusal_says_nothing_was_charged(machine):
    q = machine.quote(lines())
    machine.reserve(q.quote_id, available=STOCK)
    with pytest.raises(CommerceError, match="Nothing has been charged"):
        machine.begin_capture(q.quote_id, "0" * 64)


# --- expiry ------------------------------------------------------------------------


def test_a_quote_expires(machine, clock):
    q = machine.quote(lines())
    clock.advance(901)
    with pytest.raises(CommerceError, match="expired"):
        machine.reserve(q.quote_id, available=STOCK)
    assert machine.store.get(q.quote_id).state is QuoteState.EXPIRED


def test_a_reservation_expires_and_releases_its_stock(machine, clock):
    q = machine.quote(lines(qty=100))
    machine.reserve(q.quote_id, available=STOCK)
    assert machine.store.held_qty("BOLT-M8", clock()) == 100

    clock.advance(601)
    assert machine.store.held_qty("BOLT-M8", clock()) == 0, "expired holds must not count"
    with pytest.raises(CommerceError, match="reservation on .* expired"):
        machine.begin_capture(q.quote_id, q.cart_hash)


def test_expired_holds_are_ignored_even_if_the_sweeper_never_ran(machine, clock):
    """Correctness must not depend on housekeeping having happened."""
    first = machine.quote(lines(qty=100))
    machine.reserve(first.quote_id, available=STOCK)
    clock.advance(601)

    second = machine.quote(lines(qty=100))
    assert machine.reserve(second.quote_id, available=STOCK).state is QuoteState.RESERVED


def test_sweep_releases_lapsed_reservations(machine, clock):
    q = machine.quote(lines())
    machine.reserve(q.quote_id, available=STOCK)
    assert machine.sweep_expired() == []
    clock.advance(601)
    assert machine.sweep_expired() == [q.quote_id]
    assert machine.store.get(q.quote_id).state is QuoteState.EXPIRED


def test_sweep_does_not_disturb_a_captured_quote(machine, clock):
    q = machine.quote(lines())
    machine.reserve(q.quote_id, available=STOCK)
    machine.begin_capture(q.quote_id, q.cart_hash)
    machine.complete_capture(q.quote_id, payment_id="pay_1")
    clock.advance(10_000)
    assert machine.sweep_expired() == []
    assert machine.store.get(q.quote_id).state is QuoteState.CAPTURED


# --- stock contention --------------------------------------------------------------


def test_a_second_reservation_cannot_take_stock_already_held(machine):
    first = machine.quote(lines(qty=80))
    machine.reserve(first.quote_id, available=STOCK)

    second = machine.quote(lines(qty=40))
    with pytest.raises(CommerceError, match="already held by other reservations"):
        machine.reserve(second.quote_id, available=STOCK)


def test_the_stock_refusal_shows_the_arithmetic(machine):
    """'Out of stock' is useless; 100 on hand, 80 held, 20 free is actionable."""
    first = machine.quote(lines(qty=80))
    machine.reserve(first.quote_id, available=STOCK)
    second = machine.quote(lines(qty=40))
    with pytest.raises(CommerceError) as exc:
        machine.reserve(second.quote_id, available=STOCK)
    msg = str(exc.value)
    assert "100 on hand" in msg and "80 already held" in msg and "20 free" in msg


# --- idempotency and bad transitions -----------------------------------------------


def test_reserving_twice_is_idempotent_not_a_double_hold(machine):
    """Agents retry. A retry must not consume the stock a second time."""
    q = machine.quote(lines(qty=60))
    machine.reserve(q.quote_id, available=STOCK)
    machine.reserve(q.quote_id, available=STOCK)
    assert machine.store.held_qty("BOLT-M8", machine.clock()) == 60


def test_capturing_twice_is_refused(machine):
    q = machine.quote(lines())
    machine.reserve(q.quote_id, available=STOCK)
    machine.begin_capture(q.quote_id, q.cart_hash)
    machine.complete_capture(q.quote_id, payment_id="pay_1")
    with pytest.raises(CommerceError, match="not been charged again"):
        machine.begin_capture(q.quote_id, q.cart_hash)


def test_capturing_without_reserving_is_refused(machine):
    q = machine.quote(lines())
    with pytest.raises(CommerceError, match="only a reserved quote can be captured"):
        machine.begin_capture(q.quote_id, q.cart_hash)


def test_cancelling_frees_the_stock(machine):
    q = machine.quote(lines(qty=50))
    machine.reserve(q.quote_id, available=STOCK)
    machine.cancel(q.quote_id)
    assert machine.store.held_qty("BOLT-M8", machine.clock()) == 0


def test_a_captured_quote_cannot_be_cancelled(machine):
    q = machine.quote(lines())
    machine.reserve(q.quote_id, available=STOCK)
    machine.begin_capture(q.quote_id, q.cart_hash)
    machine.complete_capture(q.quote_id, payment_id="pay_1")
    with pytest.raises(CommerceError, match="captured and cannot be cancelled"):
        machine.cancel(q.quote_id)


def test_an_empty_cart_cannot_be_quoted(machine):
    with pytest.raises(CommerceError, match="empty cart"):
        machine.quote([])


def test_an_unknown_quote_id_is_a_clear_error(machine):
    with pytest.raises(CommerceError, match="No such quote"):
        machine.reserve("q_nope", available=STOCK)
