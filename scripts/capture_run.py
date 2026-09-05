"""Run the buyer demo for real and record what it printed, and when.

    .venv/Scripts/python.exe scripts/capture_run.py --out docs/video/assets/run_capture.json

Part two of the pitch video is the system actually executing. The rule in
`docs/video/PRODUCTION.md` is that terminal scrollback never goes on screen as a
screenshot -- thin 12pt mono glyphs are exactly what YouTube's encoder throws away -- so the
real text gets re-typeset at 28px instead. To re-typeset it *as it happened* rather than as a
finished block, the renderer needs the timing as well as the text.

So this drives `scripts/demo_buy.py` as a subprocess against two live servers and writes one
record per line: the text, and the seconds from launch at which it appeared. Nothing is
simulated and nothing is re-flowed. A line that took four seconds to come back because a model
was thinking, or because Razorpay was, is four seconds late in the capture and will be four
seconds late on screen.

Stdout is read unbuffered and line by line, and `PYTHONUNBUFFERED` is set on the child, because
the default block buffering would batch the whole run into a handful of arrival times and the
timing would be a fiction.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description="Capture a real demo run, with timings.")
    ap.add_argument("--out", default="docs/video/assets/run_capture.json")
    ap.add_argument(
        "--demo-args",
        default="--decline",
        help="passed through to demo_buy.py",
    )
    args = ap.parse_args()

    cmd = [sys.executable, str(REPO / "scripts" / "demo_buy.py"), *args.demo_args.split()]
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}

    print(f"$ {' '.join(cmd)}", flush=True)
    t0 = time.monotonic()
    lines: list[dict] = []

    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.stdout is not None
    for raw in proc.stdout:
        t = round(time.monotonic() - t0, 3)
        line = raw.rstrip("\n")
        lines.append({"t": t, "s": line})
        print(f"{t:7.2f}  {line}", flush=True)
    code = proc.wait()
    elapsed = round(time.monotonic() - t0, 3)

    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"elapsed": elapsed, "exit": code, "lines": lines}, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"\n{len(lines)} lines over {elapsed:.2f}s, exit {code} -> {out}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
