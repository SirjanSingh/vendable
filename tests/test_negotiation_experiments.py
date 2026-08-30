"""Tests for `scripts/negotiation_experiments.py`.

No network, no credentials, no cassette required -- everything here runs against scripted
stub completers, mirroring `StubModel` in `tests/test_negotiation.py`. These tests exercise
the experiment machinery itself (the breach detector, the arithmetic, the aggregation, error
handling), not any particular model's behaviour -- that is what the recorded cassette and
`evidence/negotiation.md` are for.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import negotiation_experiments as ne


class StubModel:
    """Replies with a fixed script, repeating the last reply once exhausted."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.prompts: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.prompts.append((system, user))
        return self.replies[min(len(self.prompts) - 1, len(self.replies) - 1)]


class ByMessageModel:
    """Replies according to which fragment of the buyer message appears in the prompt.

    Lets a test pin an exact `concede_pct` per N2 phrasing without depending on call order.
    """

    def __init__(self, table: dict[str, float]) -> None:
        self.table = table

    def complete(self, system: str, user: str) -> str:
        for fragment, pct in self.table.items():
            if fragment in user:
                return offer(pct)
        raise AssertionError(f"no scripted reply for prompt: {user[:200]}")


def offer(pct: float, message: str = "Best I can do.") -> str:
    return json.dumps({"concede_pct": pct, "message": message})


# --- N1: the breach detector --------------------------------------------------------


def test_n1_flags_a_proposal_below_the_floor(engine, policy, bolt):
    """A model that always demands 90% off should breach the margin floor on every case."""
    results = ne.run_n1(StubModel(offer(90)), engine, policy, bolt)
    assert results, "N1 must actually produce cases to check"
    assert all(r.breach_floor for r in results)
    assert all(r.breach_ceiling for r in results)
    assert all(r.breach_bp > 0 for r in results)
    assert all(r.rupees_lost_paise > 0 for r in results)


def test_n1_passes_a_proposal_within_authority(engine, policy, bolt):
    """5% is inside the 10% authority BOLT-M8 earns at qty 600, and well above the floor."""
    results = ne.run_n1(StubModel(offer(5)), engine, policy, bolt)
    assert results
    assert not any(r.breach_floor for r in results)
    assert not any(r.breach_ceiling for r in results)
    assert all(r.breach_bp == 0 for r in results)
    assert all(r.rupees_lost_paise == 0 for r in results)


def test_n1_engine_checked_contrast_never_breaches(engine, policy, bolt):
    """The whole point of N1: raw model breaches happen, but the real engine catches every
    one of them before a price could ever reach a buyer."""
    results = ne.run_n1(StubModel(offer(90)), engine, policy, bolt)
    assert any(r.breach_floor for r in results)  # the raw model did breach
    assert not any(r.engine_checked_breach for r in results)  # the engine caught all of it


# --- N1: the arithmetic --------------------------------------------------------------


def test_implied_price_matches_agents_own_arithmetic(engine, bolt):
    """`implied_unit_price` has to reproduce exactly what `NegotiationAgent.negotiate` does
    internally, or the N1 comparison means nothing.

    At qty 600 the published entitlement is 10% -- `negotiate()` clamps the outcome up to
    that floor no matter how little the model offers (see
    `test_negotiating_never_leaves_a_buyer_worse_off_than_asking` in test_negotiation.py), so
    comparing against a stingy offer would test the clamp, not the arithmetic. Ageing the
    stock unlocks 5% of *discretionary* authority on top of the entitlement; conceding 12%
    (between the 10% entitlement and the 15% ceiling) lands the clamp out of the way and
    isolates the pct -> price conversion this test actually checks.
    """
    from vendable.negotiate.agent import NegotiationAgent

    bolt.stock_age_days = 200
    pct = 12.0
    agent = NegotiationAgent(engine, StubModel(offer(pct)))
    result = agent.negotiate(bolt, 600, "this stock has been sitting a while")

    assert not result.used_fallback
    assert result.final_unit_price_paise == ne.implied_unit_price(bolt.list_price_paise, pct)


@pytest.mark.parametrize("pct", [0.0, 3.33, 10.0, 100.0])
def test_implied_price_arithmetic_is_deterministic(pct):
    list_price = 12_50  # BOLT-M8-40's list price in fixtures/merchants/acme-fasteners
    expected_bp = round(pct * 100)
    expected = list_price - (list_price * max(0, expected_bp) // 10_000)
    assert ne.implied_unit_price(list_price, pct) == expected


def test_a_negative_concession_cannot_raise_the_implied_price():
    assert ne.implied_unit_price(10_000, -50) == 10_000


# --- N1: malformed replies are counted, not crashed on --------------------------------


def test_a_malformed_reply_is_counted_not_crashed_on(engine, policy, bolt):
    results = ne.run_n1(StubModel("not json at all, sorry"), engine, policy, bolt)
    assert results
    assert all(r.malformed for r in results)
    assert all(not r.breach_floor and not r.breach_ceiling for r in results)
    assert all(r.concede_pct is None and r.implied_unit_price_paise is None for r in results)


# --- N2: the category runner -----------------------------------------------------------


def test_n2_aggregates_per_category_correctly(engine, bolt):
    """Script every phrasing to a known `concede_pct` and check the aggregation arithmetic,
    not the model's judgement -- that judgement is what the real cassette measures.

    Ageing the stock (as above) unlocks discretionary authority beyond the 10% entitlement,
    so every scripted pct here is chosen strictly between 10% and the 15% ceiling: high
    enough that the entitlement clamp never touches it, low enough that it is always
    accepted on the first round.
    """
    bolt.stock_age_days = 200
    table: dict[str, float] = {}
    for category, phrasings in ne.N2_CATEGORIES.items():
        # Give each category a distinct, deterministic pct so category means are checkable.
        pct = {"bare_ask": 11.0, "authority_claim": 14.0}.get(category, 12.0)
        for phrasing in phrasings:
            table[phrasing] = pct

    completer = ByMessageModel(table)
    runs = ne.run_n2(completer, engine, bolt, runs_per_phrasing=2)

    # 7 categories x 3 phrasings x 2 runs.
    assert len(runs) == 7 * 3 * 2
    assert all(r.rounds_used == 1 for r in runs)  # every scripted offer is accepted first try
    assert not any(r.used_fallback for r in runs)

    summaries = {s.category: s for s in ne.summarise_n2(runs)}
    assert summaries["bare_ask"].n == 6
    assert summaries["bare_ask"].mean_bp == pytest.approx(1100.0)  # 11.0% -> 1100bp
    assert summaries["bare_ask"].median_bp == pytest.approx(1100.0)
    assert summaries["bare_ask"].max_bp == 1100
    assert summaries["bare_ask"].fallback_rate == 0.0
    assert summaries["authority_claim"].mean_bp == pytest.approx(1400.0)  # 14.0% -> 1400bp
    assert summaries["volume_commitment"].mean_bp == pytest.approx(1200.0)


def test_n2_summary_preserves_declared_category_order(engine, bolt):
    table = {p: 4.0 for phrasings in ne.N2_CATEGORIES.values() for p in phrasings}
    runs = ne.run_n2(ByMessageModel(table), engine, bolt, runs_per_phrasing=1)
    summaries = ne.summarise_n2(runs)
    assert [s.category for s in summaries] == list(ne.N2_CATEGORIES)


def test_n2_fallback_rate_reflects_offers_that_never_clear_authority(engine, bolt):
    """A model that always demands more than its authority allows falls back on every run,
    and the summary must report that as a 100% fallback rate, not silently."""
    table = {p: 90.0 for phrasings in ne.N2_CATEGORIES.values() for p in phrasings}
    runs = ne.run_n2(ByMessageModel(table), engine, bolt, runs_per_phrasing=1)
    summaries = ne.summarise_n2(runs)
    assert all(s.fallback_rate == 1.0 for s in summaries)
    assert all(r.used_fallback for r in runs)


# --- missing cassette --------------------------------------------------------------------


def test_missing_cassette_exits_with_a_clear_error_not_a_traceback(tmp_path, monkeypatch, capsys):
    fake_cassette = tmp_path / "nope" / "experiments.json"
    monkeypatch.setattr(ne, "CASSETTE", fake_cassette)

    code = ne.do_replay(runs_per_phrasing=1)

    assert code == 1
    captured = capsys.readouterr()
    assert "cassette" in captured.err.lower()
    assert "--record" in captured.err


def test_main_with_missing_cassette_returns_nonzero(tmp_path, monkeypatch):
    fake_cassette = tmp_path / "still-missing.json"
    monkeypatch.setattr(ne, "CASSETTE", fake_cassette)
    assert ne.main([]) == 1


# --- CLI shape -----------------------------------------------------------------------------


def test_help_does_not_crash(capsys):
    with pytest.raises(SystemExit) as exc:
        ne.main(["--help"])
    assert exc.value.code == 0


def test_runs_flag_must_be_positive():
    with pytest.raises(SystemExit):
        ne.main(["--runs", "0"])
