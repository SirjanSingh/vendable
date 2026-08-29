"""The audit chain does not prevent tampering. It makes tampering detectable.

That is a weaker claim than "immutable" and a much more honest one, so these tests are
written to prove the detection actually works -- including against someone with write access
to the database, which is the only threat model that matters here.
"""

from __future__ import annotations

import sqlite3
from itertools import pairwise

import pytest

from vendable.audit.chain import GENESIS_HASH, Action, AuditChain


@pytest.fixture
def chain(tmp_path):
    c = AuditChain(tmp_path / "audit.db")
    yield c
    c.close()


def seed(chain: AuditChain, n: int = 5) -> None:
    for i in range(n):
        chain.append(
            actor="buyer:agent-7",
            action=Action.QUOTE_ISSUED if i % 2 else Action.QUOTE_REFUSED,
            subject=f"quote-{i}",
            payload={"amount_paise": 1000 * (i + 1)},
        )


def test_an_untouched_chain_verifies(chain):
    seed(chain, 20)
    assert chain.verify() == []
    assert len(chain) == 20


def test_the_first_record_links_to_genesis(chain):
    rec = chain.append("system", Action.CATALOG_INGESTED, "acme", {})
    assert rec.prev_hash == GENESIS_HASH
    assert rec.seq == 1


def test_each_record_links_to_the_one_before(chain):
    seed(chain, 4)
    records = list(chain)
    for prev, cur in pairwise(records):
        assert cur.prev_hash == prev.this_hash


def test_refusals_are_recorded_not_just_successes(chain):
    """A log of successes cannot answer 'why did it say no', which is the whole question."""
    seed(chain, 6)
    actions = {r.action for r in chain}
    assert Action.QUOTE_REFUSED in actions


# --- detection ---------------------------------------------------------------------


def test_editing_a_payload_in_the_database_is_detected(chain):
    """The realistic attack: someone with DB access quietly raises an amount."""
    seed(chain, 10)
    conn = sqlite3.connect(chain.db_path)
    conn.execute("UPDATE audit SET payload = ? WHERE seq = 5", ('{"amount_paise":999999}',))
    conn.commit()
    conn.close()

    breaks = chain.verify()
    assert breaks, "a modified payload went undetected"
    assert breaks[0].seq == 5
    assert "modified after writing" in breaks[0].reason


def test_deleting_a_record_is_detected(chain):
    """Removing an inconvenient refusal leaves a hole in the sequence."""
    seed(chain, 10)
    conn = sqlite3.connect(chain.db_path)
    conn.execute("DELETE FROM audit WHERE seq = 4")
    conn.commit()
    conn.close()

    breaks = chain.verify()
    reasons = " ".join(b.reason for b in breaks)
    assert "deleted" in reasons
    assert "link broken" in reasons


def test_rewriting_a_record_and_its_own_hash_still_breaks_the_link(chain):
    """A careful attacker recomputes the hash of the row they edited. The *next* record's
    prev_hash still points at the old value, so the chain catches it one link along."""
    seed(chain, 6)
    records = list(chain)
    victim = records[2]
    victim.payload = {"amount_paise": 1}
    recomputed = victim.digest()

    conn = sqlite3.connect(chain.db_path)
    conn.execute(
        "UPDATE audit SET payload = ?, this_hash = ? WHERE seq = ?",
        ('{"amount_paise":1}', recomputed, victim.seq),
    )
    conn.commit()
    conn.close()

    breaks = chain.verify()
    assert breaks, "a self-consistent forgery went undetected"
    assert breaks[0].seq == victim.seq + 1
    assert "link broken" in breaks[0].reason


def test_changing_the_actor_is_detected(chain):
    """Every field is in the digest, not just the amount."""
    seed(chain, 3)
    conn = sqlite3.connect(chain.db_path)
    conn.execute("UPDATE audit SET actor = 'someone-else' WHERE seq = 2")
    conn.commit()
    conn.close()
    assert chain.verify()


# --- determinism and queries -------------------------------------------------------


def test_the_digest_is_stable_across_runs(chain):
    """Verification is worthless if the same record hashes differently on another machine."""
    rec = chain.append("a", Action.PAYMENT_CAPTURED, "s", {"z": 1, "a": [2, {"b": 3}]})
    assert rec.digest() == rec.this_hash
    assert rec.digest() == rec.digest()


def test_unicode_in_a_payload_round_trips(chain):
    """Refusal messages contain ₹. If that broke hashing it would break silently."""
    rec = chain.append("a", Action.QUOTE_REFUSED, "s", {"why": "over cap by ₹1,000.00"})
    assert chain.verify() == []
    assert list(chain)[-1].payload["why"] == rec.payload["why"]


def test_records_can_be_pulled_by_subject(chain):
    chain.append("a", Action.QUOTE_ISSUED, "quote-1", {})
    chain.append("a", Action.MANDATE_REFUSED, "quote-2", {})
    chain.append("a", Action.PAYMENT_CAPTURED, "quote-1", {})
    assert [r.action for r in chain.for_subject("quote-1")] == [
        Action.QUOTE_ISSUED,
        Action.PAYMENT_CAPTURED,
    ]


def test_head_advances_with_every_append(chain):
    assert chain.head == GENESIS_HASH
    first = chain.append("a", Action.QUOTE_ISSUED, "s", {})
    assert chain.head == first.this_hash
    second = chain.append("a", Action.QUOTE_ISSUED, "s", {})
    assert chain.head == second.this_hash != first.this_hash


def test_the_chain_survives_reopening(tmp_path):
    """WAL mode, a real file, and a second process's worth of separation."""
    path = tmp_path / "audit.db"
    c1 = AuditChain(path)
    seed(c1, 5)
    head = c1.head
    c1.close()

    c2 = AuditChain(path)
    assert c2.verify() == []
    assert c2.head == head
    rec = c2.append("a", Action.PAYMENT_CAPTURED, "s", {})
    assert rec.seq == 6
    assert rec.prev_hash == head
    c2.close()
