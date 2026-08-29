"""Hash-chained append-only audit log.

Every money decision lands here -- **refusals included**, which is the point. A log that only
records successes cannot answer "why did it say no", and "why did it say no" is the question
this whole project exists to answer.

Why a hash chain rather than just an append-only table: no store on the shortlist actually
guarantees append-only. SQLite will happily `UPDATE`; Firestore will happily overwrite. The
chain does not *prevent* tampering -- nothing at this layer can -- but it makes tampering
**detectable**, including by someone who does not trust the operator. `verify_chain()` names
the first record that does not add up. That is a much more honest claim than "immutable",
and it is one that can be demonstrated live by editing a row and re-running the check.
"""

from __future__ import annotations

import enum
import hashlib
import json
import sqlite3
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

GENESIS_HASH = "0" * 64


class Action(str, enum.Enum):
    """Every kind of event worth being able to prove later."""

    CATALOG_INGESTED = "catalog.ingested"
    POLICY_COMPILED = "policy.compiled"
    POLICY_CONFIRMED = "policy.confirmed"
    QUOTE_ISSUED = "quote.issued"
    QUOTE_REFUSED = "quote.refused"
    NEGOTIATION_PROPOSED = "negotiation.proposed"
    NEGOTIATION_BLOCKED = "negotiation.blocked"
    NEGOTIATION_SETTLED = "negotiation.settled"
    MANDATE_PRESENTED = "mandate.presented"
    MANDATE_ACCEPTED = "mandate.accepted"
    MANDATE_REFUSED = "mandate.refused"
    RESERVATION_HELD = "reservation.held"
    RESERVATION_RELEASED = "reservation.released"
    PAYMENT_REQUESTED = "payment.requested"
    PAYMENT_CAPTURED = "payment.captured"
    PAYMENT_FAILED = "payment.failed"
    WEBHOOK_RECEIVED = "webhook.received"
    INJECTION_BLOCKED = "injection.blocked"


class AuditRecord(BaseModel):
    """One immutable link in the chain."""

    seq: int
    record_id: str
    ts_ms: int
    actor: str
    """Who acted -- 'buyer:agent-7', 'merchant:acme', 'system'."""
    action: Action
    subject: str
    """What was acted on -- an sku, a quote id, a mandate jti."""
    payload: dict[str, Any] = Field(default_factory=dict)
    prev_hash: str
    this_hash: str = ""

    def digest(self) -> str:
        """Recompute this record's hash from its own content.

        `sort_keys` + `separators` pin the serialisation: the same record must hash the same
        way on every machine and every Python version, or verification is worthless.
        """
        body = json.dumps(
            {
                "seq": self.seq,
                "record_id": self.record_id,
                "ts_ms": self.ts_ms,
                "actor": self.actor,
                "action": self.action.value,
                "subject": self.subject,
                "payload": self.payload,
                "prev_hash": self.prev_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )
        return hashlib.sha256(body.encode("utf-8")).hexdigest()


class ChainBreak(BaseModel):
    """Where and how verification failed."""

    seq: int
    record_id: str
    reason: str

    def __str__(self) -> str:
        return f"record {self.seq} ({self.record_id}): {self.reason}"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit (
    seq        INTEGER PRIMARY KEY,
    record_id  TEXT NOT NULL UNIQUE,
    ts_ms      INTEGER NOT NULL,
    actor      TEXT NOT NULL,
    action     TEXT NOT NULL,
    subject    TEXT NOT NULL,
    payload    TEXT NOT NULL,
    prev_hash  TEXT NOT NULL,
    this_hash  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS audit_subject ON audit(subject);
CREATE INDEX IF NOT EXISTS audit_action  ON audit(action);
"""


class AuditChain:
    """SQLite-backed hash chain. Pass `:memory:` for tests.

    WAL is on so a reader (the CLI running `audit --verify`) never blocks the writer (the
    MCP server taking a purchase).
    """

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

    # -- writing -------------------------------------------------------------------

    def append(
        self,
        actor: str,
        action: Action,
        subject: str,
        payload: dict[str, Any] | None = None,
    ) -> AuditRecord:
        cur = self._conn.execute("SELECT seq, this_hash FROM audit ORDER BY seq DESC LIMIT 1")
        row = cur.fetchone()
        seq = (row["seq"] + 1) if row else 1
        prev = row["this_hash"] if row else GENESIS_HASH

        rec = AuditRecord(
            seq=seq,
            record_id=uuid.uuid4().hex,
            ts_ms=int(time.time() * 1000),
            actor=actor,
            action=action,
            subject=subject,
            payload=payload or {},
            prev_hash=prev,
        )
        rec.this_hash = rec.digest()

        self._conn.execute(
            "INSERT INTO audit (seq, record_id, ts_ms, actor, action, subject, payload,"
            " prev_hash, this_hash) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                rec.seq,
                rec.record_id,
                rec.ts_ms,
                rec.actor,
                rec.action.value,
                rec.subject,
                json.dumps(rec.payload, sort_keys=True, separators=(",", ":"), default=str),
                rec.prev_hash,
                rec.this_hash,
            ),
        )
        self._conn.commit()
        return rec

    # -- reading -------------------------------------------------------------------

    def _row_to_record(self, row: sqlite3.Row) -> AuditRecord:
        return AuditRecord(
            seq=row["seq"],
            record_id=row["record_id"],
            ts_ms=row["ts_ms"],
            actor=row["actor"],
            action=Action(row["action"]),
            subject=row["subject"],
            payload=json.loads(row["payload"]),
            prev_hash=row["prev_hash"],
            this_hash=row["this_hash"],
        )

    def __iter__(self) -> Iterator[AuditRecord]:
        for row in self._conn.execute("SELECT * FROM audit ORDER BY seq"):
            yield self._row_to_record(row)

    def __len__(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0])

    def for_subject(self, subject: str) -> list[AuditRecord]:
        rows = self._conn.execute("SELECT * FROM audit WHERE subject = ? ORDER BY seq", (subject,))
        return [self._row_to_record(r) for r in rows]

    # -- verification --------------------------------------------------------------

    def verify(self) -> list[ChainBreak]:
        """Walk the chain. Returns every break found; empty list means intact.

        Three independent things are checked, because they fail differently:
        content tampering (the record no longer hashes to its stored hash), link tampering
        (a record's `prev_hash` does not match its predecessor), and deletion (a gap in the
        sequence). Someone editing a row to hide a refusal trips the first; someone deleting
        the row trips the third.
        """
        breaks: list[ChainBreak] = []
        expected_prev = GENESIS_HASH
        expected_seq = 1

        for rec in self:
            if rec.seq != expected_seq:
                breaks.append(
                    ChainBreak(
                        seq=rec.seq,
                        record_id=rec.record_id,
                        reason=(
                            f"sequence jumped: expected {expected_seq}, found {rec.seq}. "
                            f"{rec.seq - expected_seq} record(s) deleted."
                        ),
                    )
                )
                expected_seq = rec.seq

            recomputed = rec.digest()
            if recomputed != rec.this_hash:
                breaks.append(
                    ChainBreak(
                        seq=rec.seq,
                        record_id=rec.record_id,
                        reason=(
                            "content was modified after writing: stored hash "
                            f"{rec.this_hash[:12]}... but content hashes to "
                            f"{recomputed[:12]}..."
                        ),
                    )
                )

            if rec.prev_hash != expected_prev:
                breaks.append(
                    ChainBreak(
                        seq=rec.seq,
                        record_id=rec.record_id,
                        reason=(
                            f"link broken: prev_hash {rec.prev_hash[:12]}... does not match "
                            f"the previous record's hash {expected_prev[:12]}..."
                        ),
                    )
                )

            expected_prev = rec.this_hash
            expected_seq += 1

        return breaks

    @property
    def head(self) -> str:
        row = self._conn.execute("SELECT this_hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        return row["this_hash"] if row else GENESIS_HASH

    def close(self) -> None:
        self._conn.close()


__all__ = ["GENESIS_HASH", "Action", "AuditChain", "AuditRecord", "ChainBreak"]
