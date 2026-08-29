"""The mandate gate.

The one place a payment can be authorised, and the last thing standing between a persuaded
language model and someone's money. It contains **no model call**, reads nothing from the
prompt, and fails closed on every ambiguity.

The gate's contract with the rest of the system: it is handed a token supplied by the buyer
and a cart computed by the merchant, and it trusts *neither* until it has checked both. It
returns a decision that explains itself well enough for the buyer's agent to fix the problem
unaided -- an over-cap refusal names the cap and the overage, not merely "denied".
"""

from __future__ import annotations

import enum
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from vendable.core.db import close as db_close
from vendable.core.db import connect
from vendable.core.money import Paise, format_inr
from vendable.mandate.ap2 import MandateClaims, MandateError, verify


class RefusalCode(str, enum.Enum):
    MANDATE_INVALID = "mandate_invalid"
    UNSUPPORTED_CURRENCY = "unsupported_currency"
    NO_AMOUNT_CONSTRAINT = "no_amount_constraint"
    CURRENCY_MISMATCH = "currency_mismatch"
    AMOUNT_OVER_CAP = "amount_over_cap"
    AMOUNT_UNDER_MIN = "amount_under_min"
    PAYEE_NOT_ALLOWED = "payee_not_allowed"
    BUDGET_EXHAUSTED = "budget_exhausted"
    REPLAY = "replay"
    EMPTY_CART = "empty_cart"


class Refusal(BaseModel):
    code: RefusalCode
    message: str

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"


class CartLine(BaseModel):
    sku: str
    qty: int
    unit_price_paise: Paise

    @property
    def line_total_paise(self) -> Paise:
        return self.unit_price_paise * self.qty


class Cart(BaseModel):
    """What is actually being bought, priced by the merchant, not by the buyer."""

    merchant_id: str
    currency: str = "INR"
    lines: list[CartLine] = Field(default_factory=list)

    @property
    def total_paise(self) -> Paise:
        return sum(line.line_total_paise for line in self.lines)

    def cart_hash(self) -> str:
        """A stable fingerprint of exactly what was agreed.

        Used for two things: idempotency, and detecting tampering between the moment a quote
        was issued and the moment payment is captured. Every field that could change the
        amount is in the hash; nothing that could not is.
        """
        body = json.dumps(
            {
                "merchant_id": self.merchant_id,
                "currency": self.currency,
                "lines": sorted(
                    [
                        {"sku": ln.sku, "qty": ln.qty, "unit": ln.unit_price_paise}
                        for ln in self.lines
                    ],
                    key=lambda d: str(d["sku"]),
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(body.encode()).hexdigest()


class GateDecision(BaseModel):
    allowed: bool
    refusals: list[Refusal] = Field(default_factory=list)

    mandate_jti: str = ""
    subject: str = ""
    cart_hash: str = ""
    amount_paise: Paise = 0
    cap_paise: Paise | None = None
    spent_before_paise: Paise = 0

    explanation: str = ""

    @property
    def first_refusal(self) -> Refusal | None:
        return self.refusals[0] if self.refusals else None


_LEDGER_SCHEMA = """
CREATE TABLE IF NOT EXISTS mandate_spend (
    jti          TEXT NOT NULL,
    cart_hash    TEXT NOT NULL,
    amount_paise INTEGER NOT NULL,
    ts_ms        INTEGER NOT NULL,
    ref          TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (jti, cart_hash)
);
"""


class SpendLedger:
    """Tracks what each mandate has already committed.

    Answers two questions the token itself cannot: *has this exact purchase already been
    made* (replay / duplicate) and *how much of the budget is left*. The primary key on
    `(jti, cart_hash)` is what makes double-charging structurally impossible rather than
    merely unlikely -- Razorpay's Orders API has no idempotency header, so this is where
    the guarantee has to live.
    """

    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn = connect(self.db_path)
        self._conn.executescript(_LEDGER_SCHEMA)
        self._conn.commit()

    def spent(self, jti: str) -> Paise:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(amount_paise), 0) AS t FROM mandate_spend WHERE jti = ?",
            (jti,),
        ).fetchone()
        return int(row["t"])

    def prior(self, jti: str, cart_hash: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM mandate_spend WHERE jti = ? AND cart_hash = ?", (jti, cart_hash)
        ).fetchone()
        return dict(row) if row else None

    def record(self, jti: str, cart_hash: str, amount: Paise, ts_ms: int, ref: str = "") -> bool:
        """Commit a spend. Returns False if this exact purchase was already recorded."""
        try:
            self._conn.execute(
                "INSERT INTO mandate_spend (jti, cart_hash, amount_paise, ts_ms, ref)"
                " VALUES (?,?,?,?,?)",
                (jti, cart_hash, amount, ts_ms, ref),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def close(self) -> None:
        """Release this store's handle.

        A shared connection is only really closed when the pool drops it, because sibling
        stores on the same file are still using it.
        """
        db_close(self.db_path)


class MandateGate:
    """Decides whether a cart may be paid for under a mandate.

    Fails closed everywhere. A mandate that does not parse, does not carry a cap, or names a
    currency other than the cart's is refused -- absence of a constraint is never read as
    absence of a limit.
    """

    def __init__(
        self,
        public_pem: str,
        *,
        merchant_id: str,
        ledger: SpendLedger | None = None,
        settlement_currency: str = "INR",
    ) -> None:
        self.public_pem = public_pem
        self.merchant_id = merchant_id
        self.ledger = ledger or SpendLedger()
        self.settlement_currency = settlement_currency
        """The only currency this merchant can actually be paid in.

        Checked independently of the mandate. Found by the confusion matrix: comparing the
        mandate's currency to the cart's currency passes trivially when an attacker controls
        both, so a EUR mandate against a EUR cart was authorised even though the merchant
        settles exclusively in INR -- and the amounts would then have been compared as bare
        integers against an INR cap. Agreement between two attacker-supplied values is not
        validation.
        """

    def evaluate(self, token: str, cart: Cart) -> GateDecision:
        refusals: list[Refusal] = []
        cart_hash = cart.cart_hash()
        amount = cart.total_paise

        # 1. Is the token real, unexpired, and addressed to us?
        try:
            claims: MandateClaims = verify(token, self.public_pem, audience=self.merchant_id)
        except MandateError as exc:
            d = GateDecision(
                allowed=False,
                refusals=[Refusal(code=RefusalCode.MANDATE_INVALID, message=str(exc))],
                cart_hash=cart_hash,
                amount_paise=amount,
            )
            d.explanation = f"Refused before any pricing was considered. {exc}"
            return d

        spent = self.ledger.spent(claims.jti)

        if not cart.lines:
            refusals.append(
                Refusal(
                    code=RefusalCode.EMPTY_CART,
                    message="There is nothing in the cart to pay for.",
                )
            )

        # Checked against the merchant, not against the mandate. Both of those are supplied
        # by the buyer and can agree with each other while being wrong.
        if cart.currency != self.settlement_currency:
            refusals.append(
                Refusal(
                    code=RefusalCode.UNSUPPORTED_CURRENCY,
                    message=(
                        f"This merchant settles only in {self.settlement_currency}; the cart "
                        f"is priced in {cart.currency}. No conversion is performed. Re-price "
                        f"the cart in {self.settlement_currency}."
                    ),
                )
            )

        # 2. Replay: this exact cart, under this exact mandate, already went through.
        prior = self.ledger.prior(claims.jti, cart_hash)
        if prior is not None:
            refusals.append(
                Refusal(
                    code=RefusalCode.REPLAY,
                    message=(
                        f"This exact cart was already paid for under this mandate "
                        f"(reference {prior.get('ref') or 'unknown'}). It has not been "
                        "charged again. Issue a new mandate to buy the same items twice."
                    ),
                )
            )

        # 3. The cap. The one number this whole project claims to get right.
        rng = claims.amount_range()
        cap: Paise | None = None
        if rng is None:
            refusals.append(
                Refusal(
                    code=RefusalCode.NO_AMOUNT_CONSTRAINT,
                    message=(
                        "This mandate carries no payment.amount_range constraint, so it "
                        "authorises no specific amount. A mandate without a cap is refused "
                        "rather than treated as unlimited."
                    ),
                )
            )
        else:
            cap = rng.max
            if rng.currency != cart.currency:
                refusals.append(
                    Refusal(
                        code=RefusalCode.CURRENCY_MISMATCH,
                        message=(
                            f"The mandate authorises {rng.currency}; this cart is priced in "
                            f"{cart.currency}. No conversion is performed."
                        ),
                    )
                )
            # Inclusive bounds -- see DECISIONS.md D-007.
            elif amount > rng.max:
                refusals.append(
                    Refusal(
                        code=RefusalCode.AMOUNT_OVER_CAP,
                        message=(
                            f"Cart total {format_inr(amount)} exceeds the mandate cap of "
                            f"{format_inr(rng.max)} by {format_inr(amount - rng.max)}. "
                            f"Remove {format_inr(amount - rng.max)} of items, or present a "
                            "mandate with a higher cap."
                        ),
                    )
                )
            elif amount < rng.min:
                refusals.append(
                    Refusal(
                        code=RefusalCode.AMOUNT_UNDER_MIN,
                        message=(
                            f"Cart total {format_inr(amount)} is below the mandate minimum "
                            f"of {format_inr(rng.min)}."
                        ),
                    )
                )

        # 4. Is this merchant on the allowlist?
        payees = claims.allowed_payees()
        if payees is not None and cart.merchant_id not in payees.payees:
            refusals.append(
                Refusal(
                    code=RefusalCode.PAYEE_NOT_ALLOWED,
                    message=(
                        f"'{cart.merchant_id}' is not in this mandate's allowed payees "
                        f"({', '.join(payees.payees)})."
                    ),
                )
            )

        # 5. Cumulative budget across every cart under this mandate.
        budget = claims.budget()
        if budget is not None:
            if budget.currency != cart.currency:
                refusals.append(
                    Refusal(
                        code=RefusalCode.CURRENCY_MISMATCH,
                        message=(
                            f"The mandate budget is denominated in {budget.currency}; this "
                            f"cart is priced in {cart.currency}."
                        ),
                    )
                )
            elif spent + amount > budget.max_total:
                remaining = budget.max_total - spent
                refusals.append(
                    Refusal(
                        code=RefusalCode.BUDGET_EXHAUSTED,
                        message=(
                            f"This mandate has a total budget of "
                            f"{format_inr(budget.max_total)}, of which "
                            f"{format_inr(spent)} is already committed. "
                            f"{format_inr(remaining)} remains and this cart needs "
                            f"{format_inr(amount)}."
                        ),
                    )
                )

        decision = GateDecision(
            allowed=not refusals,
            refusals=refusals,
            mandate_jti=claims.jti,
            subject=claims.sub,
            cart_hash=cart_hash,
            amount_paise=amount,
            cap_paise=cap,
            spent_before_paise=spent,
        )
        decision.explanation = self._explain(decision)
        return decision

    def _explain(self, d: GateDecision) -> str:
        if d.allowed:
            head = (
                f"Authorised {format_inr(d.amount_paise)} against mandate {d.mandate_jti[:8]} "
                f"held by {d.subject}"
            )
            if d.cap_paise is not None:
                head += f", within its {format_inr(d.cap_paise)} cap"
                if d.amount_paise == d.cap_paise:
                    head += " (exactly at the cap, which is inclusive)"
            return head + "."
        return (
            f"Refused {format_inr(d.amount_paise)} against mandate {d.mandate_jti[:8] or '?'}. "
            + " ".join(r.message for r in d.refusals)
        )


__all__ = [
    "Cart",
    "CartLine",
    "GateDecision",
    "MandateGate",
    "Refusal",
    "RefusalCode",
    "SpendLedger",
]
