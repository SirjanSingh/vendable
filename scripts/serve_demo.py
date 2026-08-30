"""Start both demo merchants, one per port, in one terminal.

The demo needs two storefronts because the MSMED scene is a *contrast* -- one supplier that
may grant Net 60 and one that legally may not. A merchant is a process here rather than a
tenant inside one, which is the honest shape: each runs its own catalog, its own policy file
and its own audit records, and the buyer's agent reaches them at different URLs exactly as it
would reach two real suppliers.

    .venv/Scripts/python.exe scripts/serve_demo.py

Ctrl-C stops both. Anything either server prints is prefixed with the merchant it came from,
so a traceback is attributable without hunting for the window it happened in.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MERCHANTS = (
    ("acme-fasteners", 8080),
    ("shakti-forgings", 8081),
)


def pump(name: str, stream) -> None:
    """Relay one server's output, tagged. Runs until the pipe closes."""
    for raw in iter(stream.readline, ""):
        line = raw.rstrip()
        if line:
            print(f"[{name}] {line}", flush=True)


def main() -> int:
    procs: list[tuple[str, subprocess.Popen]] = []
    for merchant, port in MERCHANTS:
        env = dict(os.environ, VENDABLE_MERCHANT=merchant, PORT=str(port))
        proc = subprocess.Popen(
            [sys.executable, "-m", "vendable.mcp.server"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        procs.append((merchant, proc))
        threading.Thread(target=pump, args=(merchant, proc.stdout), daemon=True).start()
        print(f"[{merchant}] starting on :{port}  ->  http://localhost:{port}/mcp", flush=True)

    print("\nboth merchants up. In another terminal:")
    print("  .venv/Scripts/python.exe scripts/demo_buy.py")
    print("\nCtrl-C to stop.\n", flush=True)

    try:
        while True:
            for merchant, proc in procs:
                if proc.poll() is not None:
                    print(f"\n[{merchant}] exited with {proc.returncode}. Stopping the rest.")
                    raise KeyboardInterrupt
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for merchant, proc in procs:
            if proc.poll() is None:
                # SIGTERM on POSIX, TerminateProcess on Windows -- uvicorn handles both, and
                # a hard kill here would leave the SQLite write-ahead log for the next run.
                proc.send_signal(signal.SIGTERM)
        for merchant, proc in procs:
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                print(f"[{merchant}] did not stop in 8s; killing.")
                proc.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
