"""Prove the test suite passes with no network and no credentials.

The README claims this. A claim nobody can re-run is a claim nobody should believe, so it
lives here as one command:

    .venv/Scripts/python.exe scripts/verify_offline.py

It runs pytest in a child process with every socket call replaced by a raising stub and
every credential-shaped environment variable stripped. A test that quietly reaches the
network, or quietly depends on a key sitting in someone's shell, fails loudly here.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Names that would hand a test a credential without it asking.
SECRET_MARKERS = ("RAZORPAY", "GEMINI", "GOOGLE", "GCP", "API_KEY", "APIKEY", "TOKEN", "SECRET")

# Block the act of connecting, not the socket class itself. `ssl` subclasses `socket.socket`
# at import time, so replacing the class outright breaks the interpreter before pytest starts
# -- which looks like a network failure and is not one.
GUARD = """
import socket


def _blocked(*args, **kwargs):
    raise OSError(
        "network access blocked: this suite must pass with no network. "
        "A test that needs the network belongs in tests/live/, not here."
    )


socket.socket.connect = _blocked
socket.socket.connect_ex = _blocked
socket.create_connection = _blocked
socket.getaddrinfo = _blocked

import pytest

raise SystemExit(pytest.main(["tests/", "-q"]))
"""


def main() -> int:
    env = {k: v for k, v in os.environ.items() if not any(m in k.upper() for m in SECRET_MARKERS)}
    stripped = sorted(set(os.environ) - set(env))

    # The suite reads .env through pydantic-settings. Point it at nothing so a developer's
    # local keys cannot silently satisfy a test that should not need them.
    env["VENDABLE_ENV"] = "offline-verify"

    print(f"repo:            {REPO}")
    print(f"python:          {sys.executable}")
    print(f"env vars hidden: {', '.join(stripped) if stripped else '(none were set)'}")
    print("sockets:         blocked\n")

    result = subprocess.run(
        [sys.executable, "-c", GUARD], cwd=REPO, env=env, text=True, check=False
    )
    if result.returncode == 0:
        print("\nPASS - the suite is green with no network and no credentials.")
    else:
        print("\nFAIL - something in the suite reached for the network or a credential.")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
