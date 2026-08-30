"""Record real LLM responses once, replay them forever after.

`scripts/verify_offline.py` asserts the whole test suite passes with no network and no
credentials, and every `evidence/*.md` claims to reproduce deterministically on any machine.
A live call to an LLM breaks both of those guarantees the moment someone without an API key --
or without network -- tries to reproduce the run.

So a negotiation experiment is run once against a real `Completer`, wrapped in
`RecordingCompleter`, which writes every exchange to a JSON cassette. From then on,
`ReplayCompleter` reads that cassette and answers identically, with no network involved.

The one subtlety that matters: one experiment sends the *same* prompt many times on purpose,
to measure how much a model's answer varies from one call to the next. If replay collapsed
that into a single cached response, it would report zero dispersion -- a false result baked
into a published evidence file. So responses are not a dict lookup, they are a list consumed
in the order they were recorded, one per call, via a cursor kept per key.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from vendable.negotiate.agent import Completer


class ReplayMiss(RuntimeError):
    """A cassette could not answer a call: an unknown prompt, or an exhausted one."""


def _key(system: str, user: str) -> str:
    return hashlib.sha256(f"{system}\x00{user}".encode()).hexdigest()


@dataclass(slots=True)
class _Entry:
    system: str
    user: str
    responses: list[str] = field(default_factory=list)
    cursor: int = 0


class RecordingCompleter:
    """Wraps a real `Completer`. Passes calls through, records every exchange.

    Repeated identical prompts accumulate a list under one key -- that list, replayed in
    order, is what lets a replayed experiment reproduce the original dispersion.
    """

    def __init__(self, inner: Completer, path: Path | str, *, model: str = "") -> None:
        self.inner = inner
        self.path = Path(path)
        self.model = model
        self._entries: dict[str, _Entry] = {}

    def complete(self, system: str, user: str) -> str:
        response = self.inner.complete(system, user)
        key = _key(system, user)
        entry = self._entries.setdefault(key, _Entry(system=system, user=user))
        entry.responses.append(response)
        return response

    def save(self) -> None:
        """Write the cassette. `sort_keys=True` so a diff between two recordings is legible."""
        payload = {
            "model": self.model,
            "recorded_at": datetime.now(UTC).isoformat(),
            "entries": {
                key: {
                    "system": entry.system,
                    "user": entry.user,
                    "responses": entry.responses,
                }
                for key, entry in self._entries.items()
            },
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, sort_keys=True, indent=2) + "\n"
        self.path.write_text(text, encoding="utf-8")


class ReplayCompleter:
    """Replays a cassette recorded by `RecordingCompleter`. Never touches the network.

    `strict=True` (the default) is for tests and CI: an unknown prompt or an exhausted
    response list is always a bug -- either the code drifted from what was recorded, or the
    cassette is stale -- and both must fail loudly rather than hand back a guess.

    `strict=False` is for exploratory use, where cycling back through the recorded responses
    on exhaustion is more useful than stopping. An unknown key still raises even here: a
    prompt that was never recorded is never something to paper over, in any mode.
    """

    def __init__(self, path: Path | str, *, strict: bool = True) -> None:
        self.path = Path(path)
        self.strict = strict
        if not self.path.is_file():
            raise FileNotFoundError(
                f"No cassette at {self.path}. Record one first with RecordingCompleter, "
                "or point at the right file -- there is no live fallback."
            )
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self._entries: dict[str, _Entry] = {
            key: _Entry(system=v["system"], user=v["user"], responses=list(v["responses"]))
            for key, v in data.get("entries", {}).items()
        }

    def complete(self, system: str, user: str) -> str:
        key = _key(system, user)
        entry = self._entries.get(key)
        if entry is None:
            raise ReplayMiss(
                f"No cassette entry for key {key[:12]}... -- this prompt was never recorded. "
                f"Re-record the cassette at {self.path}."
            )
        if entry.cursor >= len(entry.responses):
            if self.strict:
                raise ReplayMiss(
                    f"Cassette entry {key[:12]}... is exhausted: {len(entry.responses)} "
                    f"response(s) recorded, but response #{entry.cursor + 1} was requested. "
                    f"Re-record the cassette at {self.path} with more calls."
                )
            entry.cursor = 0
        response = entry.responses[entry.cursor]
        entry.cursor += 1
        return response

    @property
    def unused(self) -> int:
        """Responses recorded but never handed back by a `complete()` call."""
        return sum(len(entry.responses) - entry.cursor for entry in self._entries.values())


__all__ = ["RecordingCompleter", "ReplayCompleter", "ReplayMiss"]
