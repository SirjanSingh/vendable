"""Prove the test suite passes with no network and no credentials.

The README claims this. A claim nobody can re-run is a claim nobody should believe, so it
lives here as one command:

    .venv/Scripts/python.exe scripts/verify_offline.py

It runs pytest in a child process that refuses to connect to any address other than
loopback, and with every credential-shaped environment variable stripped. A test that
quietly reaches the network, or quietly depends on a key sitting in someone's shell,
fails loudly here.

Loopback is permitted because `asyncio` builds its event loop's self-pipe out of a TCP
socket pair on 127.0.0.1. Nothing in the suite starts a server, so the exception buys a
working event loop and gives up nothing: the claim is that no packet leaves this machine,
not that no socket object is ever constructed.
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
#
# Loopback is allowed, and the distinction is not a loosening of the claim. The claim is that
# nothing leaves this machine and no credential is read; it was never that no socket object may
# exist. On Windows, `asyncio` builds its event loop's self-pipe out of a real TCP socket pair
# on 127.0.0.1, so a blanket ban made every async test fail with "network access blocked" while
# no packet had gone anywhere. Refusing every non-loopback address is the property worth
# enforcing, and it is enforced below on the address, not on the call.
GUARD = """
import ipaddress
import socket

LOOPBACK_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost", ""}


def _is_local(address):
    host = address[0] if isinstance(address, tuple) else address
    if not isinstance(host, str):
        return False
    if host.lower() in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _guard(original, describe):
    def wrapper(*args, **kwargs):
        target = describe(*args, **kwargs)
        if _is_local(target):
            return original(*args, **kwargs)
        raise OSError(
            f"network access blocked ({target!r}): this suite must pass with no network. "
            "A test that needs the network belongs in tests/live/, not here."
        )

    return wrapper


socket.socket.connect = _guard(socket.socket.connect, lambda self, address: address)
socket.socket.connect_ex = _guard(socket.socket.connect_ex, lambda self, address: address)
socket.create_connection = _guard(socket.create_connection, lambda address, *a, **k: address)
socket.getaddrinfo = _guard(socket.getaddrinfo, lambda host, *a, **k: host)

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
    print("sockets:         every address except loopback is refused\n")

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
