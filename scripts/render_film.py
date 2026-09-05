"""Render `docs/video/film.html` to numbered frames for part one of the pitch video.

    .venv/Scripts/python.exe scripts/render_film.py --probe          # a dozen stills, fast
    .venv/Scripts/python.exe scripts/render_film.py --out G:/vendable-video/frames

The page exposes `window.seek(t)` and promises that the same `t` always paints the same
pixels. This walks `t` in 1/30s steps and screenshots each one, so the cut is reproducible
rather than captured in real time: a dropped frame during a live capture would silently shift
everything after it against the voice track.

The page is served over loopback rather than opened as a `file://` URL, because it loads
`gate-scene.js` alongside it and file-origin loads are restricted. Serving `docs/` also keeps
every asset path in the HTML the same one a browser sees.

Frames belong on G:. At 1920x1080 the full three minutes is ~5,400 files and over a gigabyte,
and C: and D: are both above 95% full.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import json
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

# On-screen reading runs at roughly 3.5 words a second, and a block the viewer cannot read
# twice is a block they did not read. Both numbers come from docs/video/PRODUCTION.md.
READ_WPS, MIN_DWELL = 3.5, 4.0

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
    # Part two is a second page with the same seek(t) contract, so it renders through this
    # script rather than a copy of it. Its cue table lands beside it as <stem>_cues.json.
    ap.add_argument("--page", default="film.html", help="page under docs/video/ to render")
    ap.add_argument("--fps", type=int, default=FPS)
    ap.add_argument("--probe", action="store_true", help="a handful of stills, no full render")
    ap.add_argument(
        "--check",
        action="store_true",
        help="assert seek(t) is a pure function of t, then exit",
    )
    ap.add_argument(
        "--pacing",
        action="store_true",
        help="report reading load per cue, then exit",
    )
    ap.add_argument("--start", type=float, default=0.0, help="first t, seconds")
    ap.add_argument("--end", type=float, default=None, help="last t, seconds")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    httpd, port = serve(DOCS)
    url = f"http://127.0.0.1:{port}/video/{args.page}"
    # film.html keeps writing cues.json, the name build_film.py already looks for.
    stem = Path(args.page).stem
    cues_name = "cues.json" if stem == "film" else f"{stem}_cues.json"

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

            # Dump the cue table the page is actually using. build_film.py needs the same
            # numbers to place the voice files, and a second hand-maintained copy of them
            # would drift the moment a cue is re-timed to the real audio. The page is the
            # authority; this file is derived from it on every run.
            cues = page.evaluate("window.CUES")
            (DOCS / "video" / cues_name).write_text(
                json.dumps({"fps": args.fps, "total": total, "cues": cues}, indent=2) + "\n",
                encoding="utf-8",
            )
            if errors:
                print("page errors before rendering:", *errors, sep="\n  ")
                return 1

            if args.check:
                # Seek all over the timeline between two samples of the same t. If any
                # state is carried forward rather than derived from t, the hashes differ.
                #
                # One sample PER CUE, not one sample overall. This used to compare a
                # single frame at t=42, which is inside scene 2 -- so a scene that
                # carried state anywhere else passed a check that never looked at it.
                # A sampled assertion only covers what it samples.
                jumble = (0.0, 170.0, 91.5, 12.25, 133.0, 60.0, 24.0, 100.0)
                bad = []
                for cue in cues:
                    probe = cue["at"] + cue["dur"] * 0.4
                    page.evaluate("t => window.seek(t)", probe)
                    first = hashlib.sha256(page.screenshot()).hexdigest()
                    for t in jumble:
                        page.evaluate("t => window.seek(t)", t)
                    page.evaluate("t => window.seek(t)", probe)
                    again = hashlib.sha256(page.screenshot()).hexdigest()
                    ok = first == again
                    if not ok:
                        bad.append(cue["id"])
                    print(
                        f"  {'ok  ' if ok else 'FAIL'}  {cue['id']}  t={probe:6.2f}  {first[:32]}"
                    )
                print(
                    "PASS - seek(t) is deterministic in every scene"
                    if not bad
                    else "FAIL - state carried in: " + ", ".join(bad)
                )
                browser.close()
                return 0 if bad else 1

            if args.pacing:
                # Two of the typography rules in PRODUCTION.md are arithmetic: at most about
                # twelve words on screen at once, and every block held long enough to read at
                # READ_WPS. Pacing as an experience still needs a person; this is only the
                # part that does not.
                print(f"{'cue':<5}{'dur':>6}{'peak words':>12}{'read s':>9}{'dwell':>8}   verdict")
                flagged = []
                for cue in cues:
                    peak, last_growth, prev = 0, cue["at"], -1
                    t = cue["at"]
                    while t < cue["at"] + cue["dur"]:
                        page.evaluate("t => window.seek(t)", t)
                        txt = page.evaluate(
                            "() => { const s = document.querySelector('.scene.on');"
                            " return s ? s.innerText : ''; }"
                        )
                        n = len(txt.split())
                        if n > prev:
                            last_growth = t
                        prev, peak = n, max(peak, n)
                        t += 0.5

                    dwell = (cue["at"] + cue["dur"]) - last_growth
                    need = peak / READ_WPS
                    why = []
                    if dwell < MIN_DWELL:
                        why.append(f"final block held {dwell:.1f}s, under {MIN_DWELL}s")
                    if need > cue["dur"]:
                        why.append("more text than there is time to read it")
                    if why:
                        flagged.append(cue["id"])
                    print(
                        f"{cue['id']:<5}{cue['dur']:>6}{peak:>12}{need:>9.1f}{dwell:>8.1f}"
                        f"   {'; '.join(why) or 'ok'}"
                    )
                print()
                print("scenes to look at: " + (", ".join(flagged) or "none"))
                browser.close()
                return 1 if flagged else 0

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

                # Frames are written by index and overwrite in place, so a re-timed film
                # that is SHORTER than the last render leaves the old tail on disk and
                # build_film.py globs it straight back in. The result plays fine and is
                # silently too long, which is the failure mode this repo keeps finding.
                #
                # ONLY on a full render. `last` comes from --end, so on a ranged re-render
                # of one scene this sweep means "delete everything after the scene I just
                # fixed" -- `--start 61 --end 96` would take out frames 2880 to 5579, the
                # whole rest of the film, and report success while doing it. A partial
                # render knows nothing about where the film ends and must not prune.
                ranged = args.start > 0 or args.end is not None
                stale = [] if ranged else [f for f in out.glob("f*.jpg") if int(f.stem[1:]) >= last]
                for f in stale:
                    f.unlink()
                if stale:
                    print(f"removed {len(stale)} stale frames from a longer previous render")

            if errors:
                print("page errors DURING rendering:", *errors, sep="\n  ")
                return 1
            browser.close()
    finally:
        httpd.shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
