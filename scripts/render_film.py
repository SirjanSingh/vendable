"""Render `docs/video/film.html` to numbered frames for part one of the pitch video.

    .venv/Scripts/python.exe scripts/render_film.py --probe          # a dozen stills, fast
    .venv/Scripts/python.exe scripts/render_film.py --out G:/vendable-video/frames

The page exposes `window.seek(t)` and promises that the same `t` always paints the same
pixels. This walks `t` in 1/30s steps and screenshots each one, so the cut is reproducible
rather than captured in real time: a dropped frame during a live capture would silently shift
everything after it against the voice track.

The page is served over loopback rather than opened as a `file://` URL, because it fetches
`../architecture.svg` and file-origin fetches are blocked. Serving `docs/` also keeps the
image path in the HTML the same one a browser sees.

Frames belong on G:. At 1920x1080 the full three minutes is ~5,400 files and over a gigabyte,
and C: and D: are both above 95% full.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import os
import socketserver
import threading
from pathlib import Path

# Set before Playwright launches, same as scripts/verify_console.py. Chromium is ~700 MB and
# C: runs at under 400 MB free.
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "D:/tmp/pw-browsers")

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "docs"

WIDTH, HEIGHT, FPS = 1920, 1080, 30

# Stills that between them touch every scene and every animated transition, for eyeballing a
# design change without paying for a full render.
PROBE_TIMES = (
    0.5,
    8.0,
    17.0,
    20.0,
    24.0,
    30.0,
    40.0,
    57.0,
    66.0,
    75.0,
    82.0,
    88.0,
    92.0,
    100.0,
    112.0,
    120.0,
    128.0,
    140.0,
    152.0,
    160.0,
    167.0,
    172.0,
)


def serve(directory: Path) -> tuple[socketserver.TCPServer, int]:
    """Serve `directory` on a loopback port the OS picks for us."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    # Quiet: one log line per frame times 5,400 frames is not useful output.
    handler.log_message = lambda *a, **k: None  # type: ignore[assignment]
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def main() -> int:
    ap = argparse.ArgumentParser(description="Render part one of the pitch video to frames.")
    ap.add_argument("--out", default="G:/vendable-video/frames", help="frame directory")
    ap.add_argument("--fps", type=int, default=FPS)
    ap.add_argument("--probe", action="store_true", help="a handful of stills, no full render")
    ap.add_argument(
        "--check",
        action="store_true",
        help="assert seek(t) is a pure function of t, then exit",
    )
    ap.add_argument("--start", type=float, default=0.0, help="first t, seconds")
    ap.add_argument("--end", type=float, default=None, help="last t, seconds")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    httpd, port = serve(DOCS)
    url = f"http://127.0.0.1:{port}/video/film.html"

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})

            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

            page.goto(url, wait_until="load")
            # Web fonts load asynchronously. Rendering before they arrive gives the first
            # frames a fallback face, which is a difference no later frame repeats -- the
            # exact kind of non-determinism this script exists to avoid.
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(600)

            total = page.evaluate("window.TOTAL")
            if errors:
                print("page errors before rendering:", *errors, sep="\n  ")
                return 1

            if args.check:
                # Seek all over the timeline between two samples of the same t. If any
                # state is carried forward rather than derived from t, the hashes differ.
                page.evaluate("t => window.seek(t)", 42.0)
                first = hashlib.sha256(page.screenshot()).hexdigest()
                for t in (0.0, 170.0, 91.5, 12.25, 133.0, 60.0):
                    page.evaluate("t => window.seek(t)", t)
                page.evaluate("t => window.seek(t)", 42.0)
                again = hashlib.sha256(page.screenshot()).hexdigest()
                ok = first == again
                print(f"t=42 rendered twice, out of order in between: {first[:32]}")
                print("PASS - seek(t) is deterministic" if ok else "FAIL - seek(t) carries state")
                browser.close()
                return 0 if ok else 1

            if args.probe:
                for t in PROBE_TIMES:
                    if t > total:
                        continue
                    page.evaluate("t => window.seek(t)", t)
                    page.screenshot(path=str(out / f"probe_{t:07.2f}.png"))
                print(f"{len(PROBE_TIMES)} probe stills -> {out}")
            else:
                end = total if args.end is None else min(args.end, total)
                first, last = int(args.start * args.fps), int(end * args.fps)
                for i in range(first, last):
                    page.evaluate("t => window.seek(t)", i / args.fps)
                    page.screenshot(path=str(out / f"f{i:06d}.jpg"), quality=92, type="jpeg")
                    if i % 300 == 0:
                        pct = (i - first) / max(1, last - first) * 100
                        print(
                            f"  {i - first:>5}/{last - first}  {pct:5.1f}%  t={i / args.fps:6.2f}s"
                        )
                print(f"{last - first} frames -> {out}")

            if errors:
                print("page errors DURING rendering:", *errors, sep="\n  ")
                return 1
            browser.close()
    finally:
        httpd.shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
