"""Razorpay webhook verification and handling.

A webhook endpoint is an unauthenticated hole in the server that anyone on the internet can
POST to, and this one is told when money moved. So verification is not a formality here --
it is the only thing distinguishing Razorpay from someone who read the docs and wants a free
order marked paid.

Three properties, each of which fails differently if you get it wrong:

1. **HMAC-SHA256 over the RAW body**, keyed with the dashboard webhook secret -- which is a
   *different secret* from the API key secret. Re-serialising the parsed JSON before hashing
   produces a mismatch that looks like an attack and is actually a bug, so the raw bytes are
   carried all the way to the comparison.
2. **Constant-time comparison.** A `==` on a hex digest leaks the correct signature one byte
   at a time to anyone willing to make enough requests.
3. **Replay defence** on `X-Razorpay-Event-Id`. A valid signature stays valid forever; the
   same signed delivery can be replayed until the event id is remembered.

Verified against the live dashboard configuration on 2026-08-30: five events subscribed --
`payment.authorized`, `payment.captured`, `payment.failed`, `payment_link.paid`, `order.paid`.
Anything else is acknowledged and ignored rather than mishandled.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vendable.core.db import close as db_close
from vendable.core.db import connect

SIGNATURE_HEADER = "X-Razorpay-Signature"
EVENT_ID_HEADER = "X-Razorpay-Event-Id"

HANDLED_EVENTS = frozenset(
    {
        "payment.authorized",
        "payment.captured",
        "payment.failed",
        "payment_link.paid",
        "order.paid",
    }
)


class WebhookError(Exception):
    """The delivery is not trustworthy. Never leaks which check failed to the caller."""


@dataclass(slots=True)
class WebhookEvent:
    event_id: str
    event: str
    payload: dict[str, Any]
    received_at_ms: int

    @property
    def is_handled(self) -> bool:
        return self.event in HANDLED_EVENTS

    def payment_entity(self) -> dict[str, Any] | None:
        return self.payload.get("payload", {}).get("payment", {}).get("entity")

    def payment_link_entity(self) -> dict[str, Any] | None:
        return self.payload.get("payload", {}).get("payment_link", {}).get("entity")

    def order_entity(self) -> dict[str, Any] | None:
        return self.payload.get("payload", {}).get("order", {}).get("entity")


def compute_signature(raw_body: bytes, secret: str) -> str:
    """HMAC-SHA256 hex digest over the exact bytes Razorpay sent."""
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def verify_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    """Constant-time check. Returns a bool rather than raising, so callers cannot forget."""
    if not signature or not secret:
        return False
    return hmac.compare_digest(compute_signature(raw_body, secret), signature)


_SEEN_SCHEMA = """
CREATE TABLE IF NOT EXISTS webhook_seen (
    event_id  TEXT PRIMARY KEY,
    event     TEXT NOT NULL,
    ts_ms     INTEGER NOT NULL
);
"""


class SeenEvents:
    """Remembers delivered event ids so a replayed delivery is not processed twice.

    Razorpay retries on non-2xx, so duplicate deliveries are normal traffic, not just an
    attack. Without this, an honest retry after a slow response double-processes a capture.
    """

    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn = connect(self.db_path)
        self._conn.executescript(_SEEN_SCHEMA)
        self._conn.commit()

    def remember(self, event_id: str, event: str) -> bool:
        """Record an event id. False means it was already seen -- do not process again."""
        try:
            self._conn.execute(
                "INSERT INTO webhook_seen (event_id, event, ts_ms) VALUES (?,?,?)",
                (event_id, event, int(time.time() * 1000)),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def has_seen(self, event_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM webhook_seen WHERE event_id = ?", (event_id,)
        ).fetchone()
        return row is not None

    def close(self) -> None:
        """Release this store's handle.

        A shared connection is only really closed when the pool drops it, because sibling
        stores on the same file are still using it.
        """
        db_close(self.db_path)


def parse_delivery(
    raw_body: bytes,
    headers: dict[str, str],
    secret: str,
    *,
    seen: SeenEvents | None = None,
) -> WebhookEvent:
    """Verify and parse one delivery. Raises `WebhookError` on anything untrustworthy.

    Header lookup is case-insensitive: HTTP headers are case-insensitive by spec, and
    proxies do normalise them. Matching `X-Razorpay-Signature` exactly would work today and
    break behind a gateway that lowercases.
    """
    lower = {k.lower(): v for k, v in headers.items()}
    signature = lower.get(SIGNATURE_HEADER.lower(), "")

    if not verify_signature(raw_body, signature, secret):
        # Deliberately vague. A caller who learns *which* check failed learns something
        # about the secret; a caller who is really Razorpay never sees this at all.
        raise WebhookError("Webhook signature verification failed.")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise WebhookError(f"Webhook body is not valid JSON: {exc}") from exc

    event = payload.get("event", "")
    if not event:
        raise WebhookError("Webhook payload carries no 'event' field.")

    # Razorpay sends an event id header; fall back to a content hash so replay defence still
    # works if a delivery arrives without one.
    event_id = lower.get(EVENT_ID_HEADER.lower()) or hashlib.sha256(raw_body).hexdigest()

    if seen is not None and not seen.remember(event_id, event):
        raise WebhookError(f"Duplicate delivery of event {event_id}; already processed.")

    return WebhookEvent(
        event_id=event_id,
        event=event,
        payload=payload,
        received_at_ms=int(time.time() * 1000),
    )


__all__ = [
    "EVENT_ID_HEADER",
    "HANDLED_EVENTS",
    "SIGNATURE_HEADER",
    "SeenEvents",
    "WebhookError",
    "WebhookEvent",
    "compute_signature",
    "parse_delivery",
    "verify_signature",
]
