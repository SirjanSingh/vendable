"""Spike A -- the payment killer, run live.

Research said no headless path exists on a default test account (docs/research/PHASE-0.md #A).
This confirms that against the real API with real test keys, rather than taking the docs'
word for it, and establishes which path Vendable actually builds on.

    .venv/Scripts/python.exe scripts/spike_payment.py

Nothing here is imported by the app. It is a probe, kept in the repo because the answer it
produced shaped D-004 and a reviewer should be able to re-run it.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

import httpx

from vendable.core.money import format_inr, rupees
from vendable.core.settings import settings

API = "https://api.razorpay.com/v1"


def client() -> httpx.Client:
    return httpx.Client(
        auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
        timeout=30.0,
        headers={"Content-Type": "application/json"},
    )


def show(label: str, r: httpx.Response) -> dict[str, Any]:
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:400]}
    ok = "ok " if r.is_success else "FAIL"
    print(f"  [{ok}] {label}: HTTP {r.status_code}")
    if not r.is_success:
        err = body.get("error", body)
        print(f"         code={err.get('code')} desc={err.get('description')}")
    return body


def main() -> int:
    if not settings.razorpay_configured:
        print("No Razorpay keys in .env. Nothing to probe.")
        return 1
    if not settings.is_test_mode:
        print("REFUSING TO RUN: key_id is not an rzp_test_ key. This spike creates real")
        print("orders and must never touch a live account.")
        return 1

    print(f"key: {settings.razorpay_key_id[:11]}... (test mode)\n")
    findings: dict[str, str] = {}

    with client() as c:
        # --- 1. do the credentials work at all? ---
        print("1. Authentication")
        r = c.get(f"{API}/payments", params={"count": 1})
        show("GET /payments", r)
        if r.status_code == 401:
            print("\nKeys are rejected. Check they were copied whole and are test-mode keys.")
            return 1
        findings["auth"] = "working"

        # --- 2. Orders: does `receipt` really behave as an idempotency key? ---
        print("\n2. Orders API, and whether `receipt` de-duplicates")
        receipt = f"vendable-spike-{int(time.time())}"
        payload = {
            "amount": rupees("499"),
            "currency": "INR",
            "receipt": receipt,
            "notes": {"source": "vendable spike A"},
        }
        first = show("POST /orders", c.post(f"{API}/orders", json=payload))
        order_id = first.get("id", "")
        if order_id:
            print(f"         order {order_id} for {format_inr(payload['amount'])}")

        dup = c.post(f"{API}/orders", json=payload)
        show("POST /orders again, same receipt", dup)
        if dup.is_success and dup.json().get("id") != order_id:
            findings["orders_receipt_idempotent"] = (
                "NO -- a second create with the same receipt produced a DIFFERENT order. "
                "Self-dedupe is mandatory."
            )
        elif dup.is_success:
            findings["orders_receipt_idempotent"] = "returns the same order"
        else:
            findings["orders_receipt_idempotent"] = (
                f"rejected the duplicate (HTTP {dup.status_code}) -- acts as an idempotency key"
            )

        # --- 3. Can an order be paid server-side? (S2S) ---
        print("\n3. Server-to-server payment (the only documented headless path)")
        s2s = c.post(
            f"{API}/payments/create/json",
            json={
                "amount": payload["amount"],
                "currency": "INR",
                "order_id": order_id,
                "email": "spike@vendable.test",
                "contact": "+919000000000",
                "method": "upi",
                "upi": {"flow": "collect", "vpa": "success@razorpay"},
            },
        )
        body = show("POST /payments/create/json", s2s)
        if s2s.is_success:
            findings["s2s"] = "ENABLED -- a headless payment path exists after all"
        else:
            findings["s2s"] = (
                f"unavailable: {body.get('error', {}).get('description', s2s.status_code)}"
            )

        # --- 4. Payment Links: created by API, but payable by API? ---
        print("\n4. Payment Links")
        link = c.post(
            f"{API}/payment_links",
            json={
                "amount": rupees("499"),
                "currency": "INR",
                "accept_partial": False,
                "description": "Vendable spike A",
                "notify": {"sms": False, "email": False},
                "reminder_enable": False,
            },
        )
        lbody = show("POST /payment_links", link)
        link_url = lbody.get("short_url", "")
        if link_url:
            print(f"         {link_url}")
            findings["payment_link"] = f"created, hosted page at {link_url}"
        else:
            findings["payment_link"] = "creation failed"

    print("\n" + "=" * 70)
    print("FINDINGS")
    print("=" * 70)
    for k, v in findings.items():
        print(f"  {k}: {v}")
    print(
        "\nIf s2s is unavailable, D-004 stands: the last mile needs a browser, and that is\n"
        "the honest finding to report rather than hide."
    )
    print(json.dumps(findings, indent=2), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
