"""Webhook verification.

This endpoint is an unauthenticated hole in the server that gets told when money moved.
These tests are what stop it being a hole anyone can use.
"""

from __future__ import annotations

import json

import pytest

from vendable.razorpay.webhooks import (
    HANDLED_EVENTS,
    SeenEvents,
    WebhookError,
    compute_signature,
    parse_delivery,
    verify_signature,
)

SECRET = "a-webhook-secret-from-the-dashboard"


def delivery(event: str = "payment.captured", *, amount: int = 49_900) -> bytes:
    """A body shaped like a real Razorpay delivery."""
    return json.dumps(
        {
            "entity": "event",
            "account_id": "acc_test",
            "event": event,
            "contains": ["payment"],
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_TViZDQ7bEp50yR",
                        "amount": amount,
                        "currency": "INR",
                        "status": "captured",
                        "method": "netbanking",
                        "order_id": "order_abc",
                    }
                }
            },
            "created_at": 1788034000,
        },
        separators=(",", ":"),
    ).encode()


def headers(body: bytes, secret: str = SECRET, event_id: str = "evt_1") -> dict[str, str]:
    return {
        "X-Razorpay-Signature": compute_signature(body, secret),
        "X-Razorpay-Event-Id": event_id,
        "Content-Type": "application/json",
    }


# --- signature ---------------------------------------------------------------------


def test_a_correctly_signed_delivery_is_accepted():
    body = delivery()
    evt = parse_delivery(body, headers(body), SECRET)
    assert evt.event == "payment.captured"
    assert evt.payment_entity()["id"] == "pay_TViZDQ7bEp50yR"


def test_a_forged_signature_is_rejected():
    body = delivery()
    bad = {"X-Razorpay-Signature": "0" * 64, "X-Razorpay-Event-Id": "evt_x"}
    with pytest.raises(WebhookError, match="signature verification failed"):
        parse_delivery(body, bad, SECRET)


def test_an_unsigned_delivery_is_rejected():
    body = delivery()
    with pytest.raises(WebhookError):
        parse_delivery(body, {"X-Razorpay-Event-Id": "evt_x"}, SECRET)


def test_a_delivery_signed_with_the_wrong_secret_is_rejected():
    """Specifically: signing with the API key secret instead of the webhook secret."""
    body = delivery()
    with pytest.raises(WebhookError):
        parse_delivery(body, headers(body, secret="the-api-key-secret"), SECRET)


def test_a_tampered_body_is_rejected():
    """Sign a ₹499 capture, then swap in ₹49,900. The signature must no longer match."""
    original = delivery(amount=49_900)
    h = headers(original)
    inflated = delivery(amount=4_990_000)
    with pytest.raises(WebhookError):
        parse_delivery(inflated, h, SECRET)


def test_signature_check_is_over_raw_bytes_not_reserialised_json():
    """Re-serialising before hashing is the classic bug -- key order and spacing change."""
    body = json.dumps({"event": "payment.captured", "payload": {}}, indent=4).encode()
    sig = compute_signature(body, SECRET)
    assert verify_signature(body, sig, SECRET)

    reserialised = json.dumps(json.loads(body), separators=(",", ":")).encode()
    assert reserialised != body
    assert not verify_signature(reserialised, sig, SECRET)


def test_header_lookup_is_case_insensitive():
    """Proxies normalise header case. Matching exactly would break behind a gateway."""
    body = delivery()
    lowered = {"x-razorpay-signature": compute_signature(body, SECRET), "x-razorpay-event-id": "e1"}
    assert parse_delivery(body, lowered, SECRET).event_id == "e1"


def test_verification_failure_does_not_say_which_check_failed():
    """A caller who learns why it failed learns something about the secret."""
    body = delivery()
    with pytest.raises(WebhookError) as exc:
        parse_delivery(body, {"X-Razorpay-Signature": "abc"}, SECRET)
    assert str(exc.value) == "Webhook signature verification failed."


# --- replay ------------------------------------------------------------------------


def test_the_same_event_id_is_not_processed_twice():
    seen = SeenEvents(":memory:")
    body = delivery()
    h = headers(body, event_id="evt_dup")
    assert parse_delivery(body, h, SECRET, seen=seen).event_id == "evt_dup"
    with pytest.raises(WebhookError, match="Duplicate delivery"):
        parse_delivery(body, h, SECRET, seen=seen)


def test_distinct_events_both_get_through():
    seen = SeenEvents(":memory:")
    body = delivery()
    assert parse_delivery(body, headers(body, event_id="e1"), SECRET, seen=seen)
    assert parse_delivery(body, headers(body, event_id="e2"), SECRET, seen=seen)


def test_a_delivery_with_no_event_id_still_gets_replay_protection():
    """Falls back to hashing the body, so the guarantee does not depend on a header."""
    seen = SeenEvents(":memory:")
    body = delivery()
    h = {"X-Razorpay-Signature": compute_signature(body, SECRET)}
    parse_delivery(body, h, SECRET, seen=seen)
    with pytest.raises(WebhookError, match="Duplicate delivery"):
        parse_delivery(body, h, SECRET, seen=seen)


# --- payload -----------------------------------------------------------------------


def test_malformed_json_is_rejected_after_the_signature_passes():
    body = b"{not json"
    with pytest.raises(WebhookError, match="not valid JSON"):
        parse_delivery(body, headers(body), SECRET)


def test_a_body_with_no_event_field_is_rejected():
    body = json.dumps({"payload": {}}).encode()
    with pytest.raises(WebhookError, match="no 'event' field"):
        parse_delivery(body, headers(body), SECRET)


def test_events_we_do_not_subscribe_to_are_marked_unhandled_not_rejected():
    """Razorpay can send more than we asked for. Acknowledge, then ignore deliberately."""
    body = delivery(event="payment.dispute.created")
    evt = parse_delivery(body, headers(body), SECRET)
    assert not evt.is_handled


def test_the_five_subscribed_events_are_all_handled():
    """Mirrors the dashboard configuration made on 2026-08-30."""
    assert HANDLED_EVENTS == {
        "payment.authorized",
        "payment.captured",
        "payment.failed",
        "payment_link.paid",
        "order.paid",
    }
    for name in HANDLED_EVENTS:
        body = delivery(event=name)
        assert parse_delivery(body, headers(body), SECRET).is_handled
