"""Razorpay client.

A thin, deliberate wrapper rather than the vendor SDK, for three reasons: retries and their
jitter need to be ours, every call needs to land in the audit chain, and the wrapper must
**refuse to run against a live key**. That last one is not paranoia -- this repo goes public
at submission, and a wrapper that would happily move real money if someone pasted the wrong
key into `.env` is a liability, not a feature.

What the live probe (`scripts/spike_payment.py`) established, and what this is built on:

- `POST /v1/payments/create/json` is **404 on a default test account**. There is no
  server-side payment path. Orders and Payment Links are what exist.
- **`receipt` is not an idempotency key.** Posting the same payload twice with the same
  receipt produced two distinct orders. Idempotency is entirely ours to enforce.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any

import httpx

from vendable.core.money import Paise
from vendable.core.settings import Settings, settings as default_settings

API_BASE = "https://api.razorpay.com/v1"

# No numeric rate limit is published; the docs say 429 with BAD_REQUEST_ERROR /
# "Too many requests" and recommend exponential backoff. These are our own choices.
MAX_ATTEMPTS = 5
BASE_BACKOFF_S = 0.5
MAX_BACKOFF_S = 8.0


class RazorpayError(Exception):
    """A Razorpay call failed in a way the caller must handle."""

    def __init__(self, message: str, *, status: int = 0, code: str = "", retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.code = code
        self.retryable = retryable


class LiveKeyRefused(RazorpayError):
    """Raised when the configured key is not a test key. Never caught internally."""


@dataclass(slots=True)
class Order:
    id: str
    amount_paise: Paise
    currency: str
    receipt: str
    status: str
    raw: dict[str, Any]


@dataclass(slots=True)
class PaymentLink:
    id: str
    short_url: str
    amount_paise: Paise
    status: str
    reference_id: str
    raw: dict[str, Any]


@dataclass(slots=True)
class Payment:
    id: str
    amount_paise: Paise
    status: str
    method: str
    order_id: str
    raw: dict[str, Any]

    @property
    def is_captured(self) -> bool:
        return self.status == "captured"


class RazorpayClient:
    def __init__(self, cfg: Settings | None = None, *, client: httpx.Client | None = None) -> None:
        self.cfg = cfg or default_settings
        if not self.cfg.razorpay_configured:
            raise RazorpayError("No Razorpay credentials configured. See .env.example.")
        if not self.cfg.is_test_mode:
            raise LiveKeyRefused(
                f"key_id '{self.cfg.razorpay_key_id[:12]}...' is not an rzp_test_ key. "
                "Vendable refuses to run against a live account: everything here creates "
                "real orders and payment links."
            )
        self._client = client or httpx.Client(
            base_url=API_BASE,
            auth=(self.cfg.razorpay_key_id, self.cfg.razorpay_key_secret),
            timeout=30.0,
            headers={"Content-Type": "application/json"},
        )

    # -- transport -----------------------------------------------------------------

    def _request(self, method: str, path: str, **kw: Any) -> dict[str, Any]:
        """One call, with bounded retries on the failures that are actually transient.

        429 and 5xx are retried with exponential backoff plus full jitter. A 4xx that is not
        429 is a bug in our request and retrying it just wastes the buyer's time -- it is
        raised immediately with Razorpay's own description attached, so the error the buyer
        agent eventually sees says what was actually wrong.
        """
        last: RazorpayError | None = None

        for attempt in range(MAX_ATTEMPTS):
            try:
                resp = self._client.request(method, path, **kw)
            except httpx.TimeoutException as exc:
                last = RazorpayError(f"Razorpay timed out: {exc}", retryable=True)
            except httpx.HTTPError as exc:
                last = RazorpayError(f"Could not reach Razorpay: {exc}", retryable=True)
            else:
                if resp.is_success:
                    return resp.json()

                try:
                    err = resp.json().get("error", {})
                except Exception:
                    err = {}
                desc = err.get("description") or resp.text[:200]
                code = err.get("code", "")

                retryable = resp.status_code == 429 or resp.status_code >= 500
                last = RazorpayError(
                    f"Razorpay {method} {path} failed: {desc}",
                    status=resp.status_code,
                    code=code,
                    retryable=retryable,
                )
                if not retryable:
                    raise last

            if attempt < MAX_ATTEMPTS - 1:
                # Full jitter: sleep uniformly in [0, backoff]. Without the jitter, every
                # retrying caller wakes at the same instant and re-creates the burst that
                # caused the 429.
                backoff = min(BASE_BACKOFF_S * (2**attempt), MAX_BACKOFF_S)
                time.sleep(random.uniform(0, backoff))

        assert last is not None
        raise last

    # -- orders --------------------------------------------------------------------

    def create_order(
        self, amount_paise: Paise, *, receipt: str, notes: dict[str, str] | None = None
    ) -> Order:
        """Create an order.

        `receipt` carries our `(mandate_jti, cart_hash)` digest so a human can reconcile in
        the dashboard. It provides **no** idempotency -- proven live, see the module docstring.
        Never rely on it to prevent a double charge; that is `SpendLedger`'s job.
        """
        body = self._request(
            "POST",
            "/orders",
            json={
                "amount": amount_paise,
                "currency": "INR",
                "receipt": receipt[:40],  # Razorpay caps receipt length
                "notes": notes or {},
            },
        )
        return Order(
            id=body["id"],
            amount_paise=body["amount"],
            currency=body["currency"],
            receipt=body.get("receipt", ""),
            status=body.get("status", ""),
            raw=body,
        )

    def fetch_order_payments(self, order_id: str) -> list[Payment]:
        body = self._request("GET", f"/orders/{order_id}/payments")
        return [_payment(item) for item in body.get("items", [])]

    # -- payment links -------------------------------------------------------------

    def create_payment_link(
        self,
        amount_paise: Paise,
        *,
        description: str,
        reference_id: str,
        expire_by_epoch: int | None = None,
        notes: dict[str, str] | None = None,
    ) -> PaymentLink:
        """Create a hosted payment link -- the only path to a completed test payment.

        `reference_id` is set to our idempotency digest. Razorpay *does* reject a duplicate
        `reference_id` on payment links, which is a genuine server-side guard, unlike the
        Orders `receipt`.
        """
        payload: dict[str, Any] = {
            "amount": amount_paise,
            "currency": "INR",
            "accept_partial": False,
            "description": description[:255],
            "reference_id": reference_id[:40],
            "notify": {"sms": False, "email": False},
            "reminder_enable": False,
            "notes": notes or {},
        }
        if expire_by_epoch:
            payload["expire_by"] = expire_by_epoch

        body = self._request("POST", "/payment_links", json=payload)
        return PaymentLink(
            id=body["id"],
            short_url=body["short_url"],
            amount_paise=body["amount"],
            status=body.get("status", ""),
            reference_id=body.get("reference_id", ""),
            raw=body,
        )

    def fetch_payment_link(self, link_id: str) -> PaymentLink:
        body = self._request("GET", f"/payment_links/{link_id}")
        return PaymentLink(
            id=body["id"],
            short_url=body["short_url"],
            amount_paise=body["amount"],
            status=body.get("status", ""),
            reference_id=body.get("reference_id", ""),
            raw=body,
        )

    # -- payments ------------------------------------------------------------------

    def fetch_payment(self, payment_id: str) -> Payment:
        return _payment(self._request("GET", f"/payments/{payment_id}"))

    def close(self) -> None:
        self._client.close()


def _payment(body: dict[str, Any]) -> Payment:
    return Payment(
        id=body["id"],
        amount_paise=body.get("amount", 0),
        status=body.get("status", ""),
        method=body.get("method", ""),
        order_id=body.get("order_id", "") or "",
        raw=body,
    )


__all__ = [
    "LiveKeyRefused",
    "Order",
    "Payment",
    "PaymentLink",
    "RazorpayClient",
    "RazorpayError",
]
