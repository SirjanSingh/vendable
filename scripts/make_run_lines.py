"""Select the lines part two puts on screen, straight out of the captured run.

    .venv/Scripts/python.exe scripts/make_run_lines.py

Reads `docs/video/assets/run_capture.json` and writes `docs/video/run_lines.js`, a classic
script assigning `window.RUN_LINES`. `part2.html` loads it the same way `film.html` loads
`gate-scene.js`: no fetch, because a fetch is asynchronous and the renderer would screenshot
whatever had arrived by then, which is the one thing a deterministic render cannot tolerate.

The point of generating rather than transcribing: every string on screen in part two is
traceable to a line a real process actually printed, and re-capturing the run regenerates the
film's text instead of silently disagreeing with it. `run.json` for the theatre page was
transcribed by hand and its own module docstring calls that out as the reason it cannot
self-update. This does not repeat that.

Selection is by step heading. `GROUPS` names the headings each scene shows; every line under
a heading travels with it, minus the decorative rules.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "docs" / "video" / "assets" / "run_capture.json"
DST = REPO / "docs" / "video" / "run_lines.js"

# Scene key -> the step numbers it shows. Steps 7 and 8, the negotiation and the injection,
# are deliberately absent: part one is already about both, and on the day of this capture they
# cost seven minutes of model latency between them. Their absence is stated on screen rather
# than papered over.
GROUPS: dict[str, list[int]] = {
    # Step 2, the catalog, is dropped: `render_film.py --pacing` put this scene 5 seconds
    # over what a viewer can read, and the catalog is the one thing here part one already
    # shows. Every cut below was made by that check rather than by eye.
    "discover": [1, 3, 4],
    "cap": [10],
    "others": [11, 12, 14],
    "money": [13, 15, 16, 17],
    "chain": [18],
}

# Hard cap on lines per scene, applied after KEEP. The audit trail prints twelve near
# identical rows and their point lands in five; the rest is reading load with no argument
# in it.
LIMIT: dict[str, int] = {"chain": 9}

# The run prints commentary for a reader as well as results for a viewer, and the commentary
# is what makes a scene unreadable at 28px in fifteen seconds. KEEP is a whitelist of markers:
# a line survives if it is a step heading or contains one of these. The strings still come
# from the capture; this only chooses which of them are on screen.
KEEP: dict[str, tuple[str, ...]] = {
    "discover": (
        "Vendable —",
        "tools discovered",
        "500+ units",
        "list ₹12.50",
        "total ₹6,750.00",
        "without being asked",
    ),
    "cap": ("authorised=", "Refused ₹6,750.00", "Fix the reason"),
    # No `authorised=False code=` rows here. The reason line under each one already carries
    # the verdict and the ground, and three duplicated status rows cost a third of the
    # scene's reading budget to say it twice.
    "others": ("Refused before any pricing", "Refused ₹6,750.00"),
    "money": (
        "authorised=True",
        "amount ₹6,750.00",
        "Authorised ₹6,750.00",
        "Razorpay exposes no agent-facing",
        "crosses the last mile",
        "status=paid",
        # Two spaces: the bare word also appears in the sentence "nothing was
        # captured", which is prose and belongs on the page rather than the screen.
        "  captured ",
        "a second, smaller order",
        "status=created",
    ),
    "chain": ("mandate.", "payment.requested", "quote.issued", "chain: "),
}

# Step 18 does not exist in demo_buy.py; the audit trail is printed under a bare heading.
BARE = {18: "Audit trail"}

HEAD = re.compile(r"^(\d+)\.\s")


def main() -> int:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    lines = data["lines"]

    # step number -> [{t, s}], heading included, rules and blanks dropped
    steps: dict[int, list[dict]] = {}
    cur: int | None = None
    for rec in lines:
        s = rec["s"]
        bare = s.strip()
        if not bare or set(bare) <= set("="):
            continue
        m = HEAD.match(bare)
        if m:
            cur = int(m.group(1))
            steps[cur] = []
        elif bare in BARE.values():
            cur = next(k for k, v in BARE.items() if v == bare)
            steps[cur] = []
        if cur is None:
            continue
        steps[cur].append({"t": rec["t"], "s": s.rstrip()})

    out: dict[str, list[dict]] = {}
    for key, wanted in GROUPS.items():
        keep = KEEP[key]
        picked: list[dict] = []
        for n in wanted:
            if n not in steps:
                raise SystemExit(f"step {n} not found in {SRC.name}")
            for rec in steps[n]:
                bare = rec["s"].strip()
                if HEAD.match(bare) or bare in BARE.values():
                    picked.append({**rec, "head": True})
                elif any(k in rec["s"] for k in keep):
                    picked.append(rec)
        # Check the markers BEFORE the cap. After it, a marker the cap trimmed is
        # indistinguishable from a marker the run stopped printing, and the warning would
        # blame the run for a decision made three lines below.
        unmatched = [k for k in keep if not any(k in r["s"] for r in picked)]
        if unmatched:
            print(f"  WARNING {key}: no line matches {unmatched}")

        cap = LIMIT.get(key)
        if cap is not None and len(picked) > cap:
            # Keep the last line, always. In the audit trail it is
            # "chain: 165 records, verify -> INTACT", which is the only line in the scene
            # that is an argument rather than an example, and a plain head-truncation
            # drops precisely it.
            picked = picked[: cap - 1] + [picked[-1]]
        # A marker matching nothing means the run changed shape and the scene is quietly
        # shorter than it was designed to be, which is why it is reported above.
        out[key] = picked

    body = json.dumps({"elapsed": data["elapsed"], "groups": out}, indent=1, ensure_ascii=False)
    DST.write_text(
        "/* GENERATED by scripts/make_run_lines.py from\n"
        " * docs/video/assets/run_capture.json. Do not edit by hand: re-capture the run\n"
        " * and re-run the generator, so the film and the run cannot disagree. */\n"
        f"window.RUN_LINES = {body};\n",
        encoding="utf-8",
    )
    total = sum(len(v) for v in out.values())
    for key, v in out.items():
        print(f"  {key:<9} {len(v):>3} lines")
    print(f"{total} lines -> {DST.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
