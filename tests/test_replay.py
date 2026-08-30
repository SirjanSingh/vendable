"""Tests for the record/replay cassette used to keep negotiation experiments offline.

No network, no credentials, no real OpenAI import -- every completer here is a fake, exactly
as `scripts/verify_offline.py` requires of the whole suite.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vendable.negotiate.replay import RecordingCompleter, ReplayCompleter, ReplayMiss


class FakeCompleter:
    """A scripted `Completer`: hands back queued replies in order, one per call."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)

    def complete(self, system: str, user: str) -> str:
        return self._replies.pop(0)


def test_round_trip_through_record_and_replay(tmp_path: Path) -> None:
    cassette = tmp_path / "cassette.json"
    inner = FakeCompleter(["offer A", "offer B"])
    recorder = RecordingCompleter(inner, cassette, model="gpt-5")

    first = recorder.complete("sys", "buyer wants 10 units")
    second = recorder.complete("sys", "buyer wants 20 units")
    recorder.save()

    player = ReplayCompleter(cassette)
    assert player.complete("sys", "buyer wants 10 units") == first
    assert player.complete("sys", "buyer wants 20 units") == second


def test_same_prompt_replays_in_recorded_order(tmp_path: Path) -> None:
    """This is the dispersion guarantee.

    One experiment sends the identical prompt 30 times to measure how much the model's
    answer varies. Recording captures a list of distinct responses under one key; if replay
    collapsed that to a dict lookup returning the same value every time, the replayed
    experiment would report zero variance -- a false result baked straight into a published
    evidence file. So replay must hand responses back one at a time, in the order recorded.
    """
    cassette = tmp_path / "cassette.json"
    inner = FakeCompleter(["10%", "12%", "8%"])
    recorder = RecordingCompleter(inner, cassette)
    for _ in range(3):
        recorder.complete("sys", "same prompt every time")
    recorder.save()

    player = ReplayCompleter(cassette)
    replayed = [player.complete("sys", "same prompt every time") for _ in range(3)]
    assert replayed == ["10%", "12%", "8%"]


def test_exhaustion_under_strict_raises_replay_miss(tmp_path: Path) -> None:
    cassette = tmp_path / "cassette.json"
    inner = FakeCompleter(["only reply"])
    recorder = RecordingCompleter(inner, cassette)
    recorder.complete("sys", "prompt")
    recorder.save()

    player = ReplayCompleter(cassette, strict=True)
    player.complete("sys", "prompt")
    with pytest.raises(ReplayMiss):
        player.complete("sys", "prompt")


def test_exhaustion_under_lenient_cycles(tmp_path: Path) -> None:
    cassette = tmp_path / "cassette.json"
    inner = FakeCompleter(["A", "B"])
    recorder = RecordingCompleter(inner, cassette)
    recorder.complete("sys", "prompt")
    recorder.complete("sys", "prompt")
    recorder.save()

    player = ReplayCompleter(cassette, strict=False)
    assert [player.complete("sys", "prompt") for _ in range(5)] == ["A", "B", "A", "B", "A"]


def test_unknown_key_raises_even_when_lenient(tmp_path: Path) -> None:
    cassette = tmp_path / "cassette.json"
    inner = FakeCompleter(["reply"])
    recorder = RecordingCompleter(inner, cassette)
    recorder.complete("sys", "recorded prompt")
    recorder.save()

    player = ReplayCompleter(cassette, strict=False)
    with pytest.raises(ReplayMiss):
        player.complete("sys", "a prompt that was never recorded")


def test_unused_counts_responses_never_replayed(tmp_path: Path) -> None:
    cassette = tmp_path / "cassette.json"
    inner = FakeCompleter(["A", "B", "C"])
    recorder = RecordingCompleter(inner, cassette)
    for _ in range(3):
        recorder.complete("sys", "prompt")
    recorder.save()

    player = ReplayCompleter(cassette)
    assert player.unused == 3
    player.complete("sys", "prompt")
    assert player.unused == 2


def test_cassette_file_is_human_readable_sorted_json(tmp_path: Path) -> None:
    cassette = tmp_path / "cassette.json"
    inner = FakeCompleter(["reply"])
    recorder = RecordingCompleter(inner, cassette, model="gpt-5")
    recorder.complete("system prompt", "user prompt")
    recorder.save()

    raw = cassette.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    data = json.loads(raw)
    assert data["model"] == "gpt-5"
    assert "recorded_at" in data
    (_key, entry) = next(iter(data["entries"].items()))
    assert entry["system"] == "system prompt"
    assert entry["user"] == "user prompt"
    assert entry["responses"] == ["reply"]

    # sort_keys=True: re-dumping with the same option must reproduce this file byte-for-byte.
    reserialized = json.dumps(data, sort_keys=True, indent=2) + "\n"
    assert reserialized == raw


def test_missing_cassette_file_raises_clear_error(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.json"
    with pytest.raises(FileNotFoundError):
        ReplayCompleter(missing)
