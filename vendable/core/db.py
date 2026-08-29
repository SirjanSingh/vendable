"""One place that opens SQLite connections, so every store gets the same settings.

Five components keep their own connection to the same file: the catalog, the audit chain,
the spend ledger, the commerce store, and the webhook de-duplicator. That is deliberate --
each owns its own schema and none reaches into another's tables -- but it means concurrent
writers are normal, not exceptional.

The default `sqlite3.connect` settings are wrong for that. Two of them specifically:

- **`timeout` defaults to 5 seconds and, more importantly, a blocked writer raises
  `OperationalError: database is locked` rather than waiting** in several common paths. A
  Razorpay webhook arriving while `/healthz` walks the audit chain is enough to produce it,
  which is exactly how this was found: the webhook returned 500 instead of the 400 it had
  correctly computed.
- **WAL is not the default.** Without it, a single reader blocks every writer, which for a
  server that verifies its own audit chain on every health check is a self-inflicted outage.

`busy_timeout` is set as a PRAGMA as well as via `timeout=`, because the two are not
reliably the same knob across Python versions.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

BUSY_TIMEOUT_MS = 15_000

# One connection per database file, shared by every store that opens it.
#
# WAL plus a busy timeout was not enough on its own: a webhook writing to the audit chain
# while another store held a write transaction still raised `database is locked`, and the
# handler returned 500 instead of the 400 it had already correctly computed.
#
# Sharing a single connection makes the problem go away rather than making it rarer. Python's
# sqlite3 reports `threadsafety == 3` (serialized), so one connection is safe to use from
# multiple threads and the driver serialises statements for us. Writers queue instead of
# colliding, which for a single-merchant storefront is exactly the behaviour wanted -- the
# alternative is tuning retry backoffs for contention that need not exist.
#
# `:memory:` is deliberately never shared: each in-memory database must stay isolated or
# every test would scribble on every other test's tables.
_POOL: dict[str, sqlite3.Connection] = {}
_LOCK = threading.Lock()


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Return the shared connection for `db_path`, opening it on first use."""
    path = str(db_path)
    if path == ":memory:":
        return _open(path)

    with _LOCK:
        existing = _POOL.get(path)
        if existing is not None:
            return existing
        conn = _open(path)
        _POOL[path] = conn
        return conn


def _open(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path, check_same_thread=False, timeout=BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    if path != ":memory:":
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        # NORMAL is the right durability trade under WAL: a crash can lose the last commits,
        # but the audit chain detects that as a truncation rather than silently accepting a
        # gap, and the alternative costs an fsync on every refusal we record.
        conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def close(db_path: Path | str) -> None:
    """Close and forget the shared connection for a path. Mostly for tests."""
    path = str(db_path)
    with _LOCK:
        conn = _POOL.pop(path, None)
    if conn is not None:
        conn.close()


__all__ = ["BUSY_TIMEOUT_MS", "close", "connect"]
