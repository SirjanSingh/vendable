"""Quote -> reserve -> capture, with a TTL on the reservation.

Why this exists rather than a single `buy()` call: between an agent deciding to buy and the
money actually moving, seconds to minutes pass while a browser crosses a checkout page. In
that window the price can change, the stock can sell out, and the cart the buyer agreed to
can drift from the cart being charged. A one-shot purchase either ignores that or discovers
it after taking the money.

So the flow is explicit, and each transition is a decision that gets audited:

    quote     the merchant states a price. Binding for a fixed window, and no stock is held.
    reserve   stock is held against a specific quote. Expires. Releases itself.
    capture   the reservation is turned into money. The cart is re-hashed first, and if it
              differs from the quoted cart by so much as a paisa, the capture is refused.

That last check is the whole reason for the ceremony. It closes the window where a compromised
or confused buyer could agree to one cart and pay for another, and it is what a red-team
"cart tampering between quote and capture" test actually attacks.

Time is injected rather than read from the clock, so expiry is testable without sleeping.
"""

from __future__ import annotations

import enum
import sqlite3
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, Field

from vendable.core.money import Paise, format_inr
from vendable.mandate.gate import Cart, CartLine

DEFAULT_QUOTE_TTL_S = 900
"""15 minutes. Long enough for a slow checkout, short enough that prices stay honest."""

DEFAULT_RESERVATION_TTL_S = 600
"""10 minutes of held stock. Every second here is stock nobody else can buy."""


class QuoteState(str, enum.Enum):
    OPEN = "open"
    RESERVED = "reserved"
    CAPTURED = "captured"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class CommerceError(Exception):
    """A transition was refused. The message is written for the buyer's agent."""


class Quote(BaseModel):
    quote_id: str
    merchant_id: str
    cart: Cart
    cart_hash: str
    state: QuoteState = QuoteState.OPEN
    created_at_s: int
    expires_at_s: int
    reserved_until_s: int | None = None
    payment_link_id: str = ""
    payment_link_url: str = ""
    payment_id: str = ""
    notes: dict[str, str] = Field(default_factory=dict)

    @property
    def total_paise(self) -> Paise:
        return self.cart.total_paise

    def is_expired_at(self, now_s: int) -> bool:
        if self.state is QuoteState.RESERVED and self.reserved_until_s is not None:
            return now_s > self.reserved_until_s
        return now_s > self.expires_at_s


_SCHEMA = """
CREATE TABLE IF NOT EXISTS quotes (
    quote_id   TEXT PRIMARY KEY,
    merchant_id TEXT NOT NULL,
    body       TEXT NOT NULL,
    state      TEXT NOT NULL,
    expires_at_s INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS quotes_state ON quotes(state);

CREATE TABLE IF NOT EXISTS stock_holds (
    quote_id   TEXT NOT NULL,
    sku        TEXT NOT NULL,
    qty        INTEGER NOT NULL,
    until_s    INTEGER NOT NULL,
    PRIMARY KEY (quote_id, sku)
);
CREATE INDEX IF NOT EXISTS holds_sku ON stock_holds(sku);
"""


class CommerceStore:
    """Persistence for quotes and stock holds. SQLite, WAL, one file."""

    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        if self.db_path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def put(self, q: Quote) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO quotes (quote_id, merchant_id, body, state, expires_at_s)"
            " VALUES (?,?,?,?,?)",
            (q.quote_id, q.merchant_id, q.model_dump_json(), q.state.value, q.expires_at_s),
        )
        self._conn.commit()

    def get(self, quote_id: str) -> Quote | None:
        row = self._conn.execute(
            "SELECT body FROM quotes WHERE quote_id = ?", (quote_id,)
        ).fetchone()
        return Quote.model_validate_json(row["body"]) if row else None

    def hold(self, quote_id: str, sku: str, qty: int, until_s: int) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO stock_holds (quote_id, sku, qty, until_s) VALUES (?,?,?,?)",
            (quote_id, sku, qty, until_s),
        )
        self._conn.commit()

    def release(self, quote_id: str) -> None:
        self._conn.execute("DELETE FROM stock_holds WHERE quote_id = ?", (quote_id,))
        self._conn.commit()

    def held_qty(self, sku: str, now_s: int) -> int:
        """Live holds only. An expired hold is not stock -- it is a row nobody cleaned up.

        Reads filter on expiry rather than relying on a sweeper having run, so a crashed
        process cannot leave stock permanently unsellable.
        """
        row = self._conn.execute(
            "SELECT COALESCE(SUM(qty), 0) AS q FROM stock_holds WHERE sku = ? AND until_s >= ?",
            (sku, now_s),
        ).fetchone()
        return int(row["q"])

    def expired_reservations(self, now_s: int) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT quote_id FROM stock_holds WHERE until_s < ?", (now_s,)
        ).fetchall()
        return [r["quote_id"] for r in rows]

    def close(self) -> None:
        self._conn.close()


class CommerceMachine:
    """The state machine. Every refusal explains what the buyer should do instead."""

    def __init__(
        self,
        store: CommerceStore,
        *,
        merchant_id: str,
        quote_ttl_s: int = DEFAULT_QUOTE_TTL_S,
        reservation_ttl_s: int = DEFAULT_RESERVATION_TTL_S,
        clock: Callable[[], int] = lambda: int(time.time()),
    ) -> None:
        self.store = store
        self.merchant_id = merchant_id
        self.quote_ttl_s = quote_ttl_s
        self.reservation_ttl_s = reservation_ttl_s
        self.clock = clock

    # -- quote ---------------------------------------------------------------------

    def quote(self, lines: list[CartLine], *, notes: dict[str, str] | None = None) -> Quote:
        if not lines:
            raise CommerceError("Cannot quote an empty cart.")
        now = self.clock()
        cart = Cart(merchant_id=self.merchant_id, currency="INR", lines=lines)
        q = Quote(
            quote_id=f"q_{uuid.uuid4().hex[:16]}",
            merchant_id=self.merchant_id,
            cart=cart,
            cart_hash=cart.cart_hash(),
            created_at_s=now,
            expires_at_s=now + self.quote_ttl_s,
            notes=notes or {},
        )
        self.store.put(q)
        return q

    # -- reserve -------------------------------------------------------------------

    def reserve(self, quote_id: str, *, available: dict[str, int]) -> Quote:
        """Hold stock against a quote.

        `available` is the merchant's on-hand count per SKU, passed in rather than read from
        a catalog, so this module stays free of catalog coupling and remains testable.
        """
        q = self._load(quote_id)
        now = self.clock()

        if q.state is QuoteState.RESERVED:
            # Idempotent: re-reserving a live reservation returns it rather than
            # double-holding. Agents retry, and a retry must not consume stock twice.
            if not q.is_expired_at(now):
                return q
        elif q.state is not QuoteState.OPEN:
            raise CommerceError(
                f"Quote {quote_id} is {q.state.value} and cannot be reserved. Request a new quote."
            )

        if q.is_expired_at(now):
            self._expire(q)
            raise CommerceError(
                f"Quote {quote_id} expired at {q.expires_at_s} (now {now}). "
                "Prices may have changed; request a new quote."
            )

        for line in q.cart.lines:
            on_hand = available.get(line.sku, 0)
            held_elsewhere = self.store.held_qty(line.sku, now)
            free = on_hand - held_elsewhere
            if line.qty > free:
                raise CommerceError(
                    f"Cannot reserve {line.qty} x {line.sku}: {on_hand} on hand, "
                    f"{held_elsewhere} already held by other reservations, {free} free. "
                    "Reduce the quantity or retry once a reservation expires."
                )

        until = now + self.reservation_ttl_s
        for line in q.cart.lines:
            self.store.hold(q.quote_id, line.sku, line.qty, until)

        q.state = QuoteState.RESERVED
        q.reserved_until_s = until
        self.store.put(q)
        return q

    # -- capture -------------------------------------------------------------------

    def begin_capture(self, quote_id: str, cart_hash_at_authorisation: str) -> Quote:
        """Final check before money moves.

        The hash comparison is the point of the whole state machine. `cart_hash_at_
        authorisation` is what the mandate gate signed off on; `q.cart_hash` is what is
        about to be charged. If they differ, something changed in between, and the only safe
        response is to stop.
        """
        q = self._load(quote_id)
        now = self.clock()

        if q.state is QuoteState.CAPTURED:
            raise CommerceError(
                f"Quote {quote_id} has already been captured (payment {q.payment_id}). "
                "It has not been charged again."
            )
        if q.state is not QuoteState.RESERVED:
            raise CommerceError(
                f"Quote {quote_id} is {q.state.value}; only a reserved quote can be captured. "
                "Reserve it first."
            )
        if q.is_expired_at(now):
            self._expire(q)
            raise CommerceError(
                f"The reservation on {quote_id} expired at {q.reserved_until_s} (now {now}). "
                "Stock has been released. Request a new quote."
            )
        if q.cart_hash != cart_hash_at_authorisation:
            raise CommerceError(
                "The cart changed between authorisation and capture. "
                f"Authorised {cart_hash_at_authorisation[:12]}..., "
                f"about to charge {q.cart_hash[:12]}.... "
                f"Nothing has been charged. Re-quote and present a fresh mandate."
            )
        return q

    def complete_capture(self, quote_id: str, *, payment_id: str) -> Quote:
        q = self._load(quote_id)
        q.state = QuoteState.CAPTURED
        q.payment_id = payment_id
        self.store.put(q)
        self.store.release(q.quote_id)  # the stock is sold, not held
        return q

    def attach_payment_link(self, quote_id: str, *, link_id: str, link_url: str) -> Quote:
        q = self._load(quote_id)
        q.payment_link_id = link_id
        q.payment_link_url = link_url
        self.store.put(q)
        return q

    # -- housekeeping --------------------------------------------------------------

    def cancel(self, quote_id: str) -> Quote:
        q = self._load(quote_id)
        if q.state is QuoteState.CAPTURED:
            raise CommerceError(f"Quote {quote_id} is captured and cannot be cancelled.")
        q.state = QuoteState.CANCELLED
        self.store.put(q)
        self.store.release(q.quote_id)
        return q

    def sweep_expired(self) -> list[str]:
        """Release stock from lapsed reservations. Returns the quote ids released.

        Reads already ignore expired holds, so this is tidying rather than correctness --
        which is exactly why it is safe to run on a timer and safe to never run at all.
        """
        now = self.clock()
        released: list[str] = []
        for quote_id in self.store.expired_reservations(now):
            q = self.store.get(quote_id)
            if q is None:
                self.store.release(quote_id)
                continue
            if q.state is QuoteState.CAPTURED:
                self.store.release(quote_id)
                continue
            self._expire(q)
            released.append(quote_id)
        return released

    # -- internals -----------------------------------------------------------------

    def _load(self, quote_id: str) -> Quote:
        q = self.store.get(quote_id)
        if q is None:
            raise CommerceError(f"No such quote: {quote_id}.")
        return q

    def _expire(self, q: Quote) -> None:
        q.state = QuoteState.EXPIRED
        self.store.put(q)
        self.store.release(q.quote_id)


def describe(q: Quote) -> str:
    """One line a human or an agent can read."""
    items = ", ".join(
        f"{ln.qty} x {ln.sku} @ {format_inr(ln.unit_price_paise)}" for ln in q.cart.lines
    )
    return f"{q.quote_id} [{q.state.value}] {items} = {format_inr(q.total_paise)}"


__all__ = [
    "DEFAULT_QUOTE_TTL_S",
    "DEFAULT_RESERVATION_TTL_S",
    "CommerceError",
    "CommerceMachine",
    "CommerceStore",
    "Quote",
    "QuoteState",
    "describe",
]
