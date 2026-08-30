"""The gate is the last thing between a persuaded model and someone's money.

These tests are the ones to read first, and the boundary cases are deliberate rather than
incidental -- see DECISIONS.md D-007.
"""

from __future__ import annotations

import base64
import json
import time

import jwt
import pytest

from vendable.core.money import rupees
from vendable.mandate.ap2 import (
    AllowedPayees,
    AmountRange,
    Budget,
    MandateError,
    generate_keypair,
    mint,
    verify,
)
from vendable.mandate.gate import Cart, CartLine, RefusalCode, SpendLedger

from .conftest import MERCHANT

CAP = rupees("5000")


def cart(total: int, merchant: str = MERCHANT, currency: str = "INR") -> Cart:
    return Cart(
        merchant_id=merchant,
        currency=currency,
        lines=[CartLine(sku="BOLT-M8", qty=1, unit_price_paise=total)],
    )


def mandate(priv: str, *, cap: int = CAP, **kw) -> str:
    constraints = kw.pop("constraints", [AmountRange(currency="INR", max=cap)])
    return mint(
        priv,
        issuer="https://wallet.test/mandates",
        subject=kw.pop("subject", "buyer-agent-7"),
        audience=kw.pop("audience", MERCHANT),
        constraints=constraints,
        **kw,
    )


# --- the cap boundary. D-007 says max is inclusive; these pin it. ------------------


def test_gate_allows_amount_equal_to_cap(keypair, gate):
    priv, _ = keypair
    d = gate.evaluate(mandate(priv), cart(CAP))
    assert d.allowed, d.explanation
    assert "inclusive" in d.explanation


def test_gate_refuses_one_minor_unit_over_cap(keypair, gate):
    """One paisa over. The whole point of integer money."""
    priv, _ = keypair
    d = gate.evaluate(mandate(priv), cart(CAP + 1))
    assert not d.allowed
    assert d.first_refusal.code is RefusalCode.AMOUNT_OVER_CAP
    assert "₹0.01" in d.first_refusal.message  # names the exact overage


def test_gate_allows_one_minor_unit_under_cap(keypair, gate):
    priv, _ = keypair
    assert gate.evaluate(mandate(priv), cart(CAP - 1)).allowed


def test_refusal_tells_the_agent_what_would_work(keypair, gate):
    """An error an agent cannot recover from unaided is a failed error message."""
    priv, _ = keypair
    msg = gate.evaluate(mandate(priv), cart(rupees("6000"))).first_refusal.message
    assert "₹5,000.00" in msg  # the cap
    assert "₹1,000.00" in msg  # the overage
    assert "higher cap" in msg  # the remedy


# --- forgery and tampering ---------------------------------------------------------


def test_gate_refuses_mandate_signed_by_another_key(gate):
    other_priv, _ = generate_keypair()
    d = gate.evaluate(mandate(other_priv), cart(rupees("100")))
    assert not d.allowed
    assert d.first_refusal.code is RefusalCode.MANDATE_INVALID


def test_gate_refuses_tampered_cap(keypair, gate):
    """The realistic attack: swap the cap in the payload, keep the original signature.

    An attacker holding a valid ₹5,000 mandate cannot re-sign, so all they can do is edit the
    payload segment in place and hope nobody checks. The signature covers header.payload, so
    this must fail -- and it must fail on the signature, before any cap arithmetic runs.
    """
    priv, _ = keypair
    header_b64, payload_b64, sig_b64 = mandate(priv).split(".")

    claims = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
    assert claims["constraints"][0]["max"] == CAP
    claims["constraints"][0]["max"] = rupees("1000000")
    tampered_payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()

    d = gate.evaluate(f"{header_b64}.{tampered_payload}.{sig_b64}", cart(rupees("900000")))
    assert not d.allowed
    assert d.first_refusal.code is RefusalCode.MANDATE_INVALID
    assert "altered after signing" in d.first_refusal.message


def test_alg_none_is_not_accepted(gate):
    """Algorithm confusion: an unsigned token must be refused, not parsed."""
    unsigned = jwt.encode(
        {
            "iss": "x",
            "sub": "y",
            "aud": MERCHANT,
            "iat": int(time.time()),
            "exp": int(time.time()) + 60,
            "jti": "deadbeef",
            "typ": "vendable.open_payment_mandate+jwt",
            "constraints": [{"type": "payment.amount_range", "currency": "INR", "max": 10**9}],
        },
        key="",
        algorithm="none",
    )
    assert not gate.evaluate(unsigned, cart(rupees("50000"))).allowed


def test_expired_mandate_is_refused(keypair, gate):
    priv, _ = keypair
    token = mandate(priv, ttl_seconds=1, now=int(time.time()) - 3600)
    d = gate.evaluate(token, cart(rupees("100")))
    assert not d.allowed
    assert "expired" in d.first_refusal.message.lower()


def test_mandate_for_another_merchant_is_refused(keypair, gate):
    priv, _ = keypair
    d = gate.evaluate(mandate(priv, audience="a-different-shop"), cart(rupees("100")))
    assert not d.allowed
    assert d.first_refusal.code is RefusalCode.MANDATE_INVALID


# --- fail closed -------------------------------------------------------------------


def test_mandate_without_a_cap_is_refused_not_treated_as_unlimited(keypair, gate):
    priv, _ = keypair
    token = mandate(priv, constraints=[AllowedPayees(payees=[MERCHANT])])
    d = gate.evaluate(token, cart(rupees("1")))
    assert not d.allowed
    assert d.first_refusal.code is RefusalCode.NO_AMOUNT_CONSTRAINT


def test_currency_mismatch_is_refused_without_conversion(keypair, gate):
    priv, _ = keypair
    token = mandate(priv, constraints=[AmountRange(currency="USD", max=CAP)])
    d = gate.evaluate(token, cart(rupees("100")))
    assert not d.allowed
    assert d.first_refusal.code is RefusalCode.CURRENCY_MISMATCH


def test_empty_cart_is_refused(keypair, gate):
    priv, _ = keypair
    d = gate.evaluate(mandate(priv), Cart(merchant_id=MERCHANT, lines=[]))
    assert not d.allowed
    assert RefusalCode.EMPTY_CART in {r.code for r in d.refusals}


# --- payee allowlist and budget ----------------------------------------------------


def test_payee_not_on_allowlist_is_refused(keypair, gate):
    priv, _ = keypair
    token = mandate(
        priv,
        constraints=[AmountRange(max=CAP), AllowedPayees(payees=["some-other-shop"])],
    )
    d = gate.evaluate(token, cart(rupees("100")))
    assert not d.allowed
    assert d.first_refusal.code is RefusalCode.PAYEE_NOT_ALLOWED


def test_budget_accumulates_across_carts(keypair, gate):
    """A per-transaction cap alone authorises unlimited transactions. Budget is the fix."""
    priv, _ = keypair
    token = mandate(
        priv,
        constraints=[AmountRange(max=rupees("1000")), Budget(max_total=rupees("1500"))],
    )
    first = gate.evaluate(token, cart(rupees("1000")))
    assert first.allowed
    gate.ledger.record(first.mandate_jti, first.cart_hash, first.amount_paise, 0, "pay_1")

    second = gate.evaluate(token, cart(rupees("900")))
    assert not second.allowed
    assert second.first_refusal.code is RefusalCode.BUDGET_EXHAUSTED
    assert "₹500.00" in second.first_refusal.message  # what remains


# --- replay ------------------------------------------------------------------------


def test_identical_cart_under_same_mandate_is_refused_as_replay(keypair, gate):
    priv, _ = keypair
    token = mandate(priv)
    c = cart(rupees("500"))
    first = gate.evaluate(token, c)
    assert first.allowed
    gate.ledger.record(first.mandate_jti, first.cart_hash, first.amount_paise, 0, "pay_abc")

    again = gate.evaluate(token, c)
    assert not again.allowed
    assert again.first_refusal.code is RefusalCode.REPLAY
    assert "pay_abc" in again.first_refusal.message


def test_a_different_cart_under_the_same_mandate_still_works(keypair, gate):
    """Replay protection must not become a one-purchase-per-mandate rule."""
    priv, _ = keypair
    token = mandate(priv)
    first = gate.evaluate(token, cart(rupees("500")))
    gate.ledger.record(first.mandate_jti, first.cart_hash, first.amount_paise, 0, "pay_1")
    assert gate.evaluate(token, cart(rupees("600"))).allowed


def test_ledger_insert_is_atomic_against_double_charge(keypair):
    """Two concurrent captures of the same cart: exactly one may win."""
    ledger = SpendLedger(":memory:")
    assert ledger.record("jti-1", "hash-1", 100, 0, "a") is True
    assert ledger.record("jti-1", "hash-1", 100, 0, "b") is False
    assert ledger.spent("jti-1") == 100


# --- cart hashing ------------------------------------------------------------------


def test_cart_hash_is_order_independent_but_price_sensitive():
    a = Cart(
        merchant_id=MERCHANT,
        lines=[
            CartLine(sku="A", qty=1, unit_price_paise=100),
            CartLine(sku="B", qty=2, unit_price_paise=200),
        ],
    )
    b = Cart(
        merchant_id=MERCHANT,
        lines=[
            CartLine(sku="B", qty=2, unit_price_paise=200),
            CartLine(sku="A", qty=1, unit_price_paise=100),
        ],
    )
    assert a.cart_hash() == b.cart_hash()

    tampered = Cart(
        merchant_id=MERCHANT,
        lines=[
            CartLine(sku="A", qty=1, unit_price_paise=100),
            CartLine(sku="B", qty=2, unit_price_paise=199),
        ],
    )
    assert tampered.cart_hash() != a.cart_hash()


def test_cart_hash_is_sensitive_to_payment_terms():
    """An early-payment discount is granted on a *promise* to pay early, and a promise that
    binds nothing is not a control. Terms are in the hash, so taking 2/10 pricing and then
    switching to Net 60 before capture breaks the authorisation exactly like a price edit.
    """
    lines = [CartLine(sku="A", qty=100, unit_price_paise=980)]
    early = Cart(merchant_id=MERCHANT, lines=lines, payment_terms_days=10)
    late = Cart(merchant_id=MERCHANT, lines=lines, payment_terms_days=60)
    assert early.cart_hash() != late.cart_hash()


def test_cart_hash_is_stable_for_identical_terms():
    """The flip side: nothing about the hash may be incidental, or every capture breaks."""
    lines = [CartLine(sku="A", qty=100, unit_price_paise=980)]
    a = Cart(merchant_id=MERCHANT, lines=lines, payment_terms_days=10)
    b = Cart(merchant_id=MERCHANT, lines=list(lines), payment_terms_days=10)
    assert a.cart_hash() == b.cart_hash()


# --- verify() directly -------------------------------------------------------------


def test_verify_rejects_a_token_of_the_wrong_type(keypair):
    priv, pub = keypair
    token = jwt.encode(
        {
            "iss": "x",
            "sub": "y",
            "aud": MERCHANT,
            "iat": int(time.time()),
            "exp": int(time.time()) + 60,
            "jti": "j",
            "typ": "some.other.credential+jwt",
            "constraints": [],
        },
        priv,
        algorithm="EdDSA",
    )
    with pytest.raises(MandateError, match="cannot authorise a payment"):
        verify(token, pub, audience=MERCHANT)


# --- settlement currency, found by the confusion matrix ----------------------------


def test_a_cart_in_a_currency_the_merchant_cannot_settle_is_refused(keypair, gate):
    """Found as a false accept by scripts/gate_matrix.py.

    The gate compared the mandate's currency to the cart's currency. Both are supplied by
    the buyer, so an attacker who controls both can make them agree: a EUR mandate against a
    EUR cart passed, and the amounts were then compared as bare integers against a cap that
    means paise. Agreement between two attacker-supplied values is not validation, so the
    cart's currency is now checked against the merchant's settlement currency instead.
    """
    priv, _ = keypair
    token = mandate(priv, constraints=[AmountRange(currency="EUR", max=CAP)])
    d = gate.evaluate(token, cart(rupees("100"), currency="EUR"))
    assert not d.allowed
    assert RefusalCode.UNSUPPORTED_CURRENCY in {r.code for r in d.refusals}
    assert "settles only in INR" in d.first_refusal.message


def test_the_settlement_check_is_independent_of_the_mandate(keypair, gate):
    """Even a perfectly self-consistent mandate cannot introduce a new currency."""
    priv, _ = keypair
    for ccy in ("USD", "GBP", "AED"):
        token = mandate(priv, constraints=[AmountRange(currency=ccy, max=CAP)])
        assert not gate.evaluate(token, cart(rupees("100"), currency=ccy)).allowed
