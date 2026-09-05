"""Bring the generated narration to a consistent broadcast level, in place.

As generated, the cues came off the TTS at -25.0 and -22.5 LUFS: too quiet for
web delivery (YouTube targets -14 and only ever attenuates, so a quiet master
stays quiet) and 2.5 LU apart from each other, which is audible as the level
lifting between scenes.

This runs a two-pass `loudnorm` to -16 LUFS / -1.5 dBTP, which is the usual
target for spoken content and leaves headroom under YouTube's own pass. Pass one
measures, pass two applies the measured values in `linear=true` mode, which
scales the whole file by a constant. That matters more than the level does: a
dynamic (single-pass) loudnorm would ride the gain and could shift where a word
sits, and every cue window in content.ts is cut to a measured duration.

Durations are asserted unchanged at the end for exactly that reason.

    .venv/Scripts/python video-remotion/scripts/normalize_vo.py
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "video-remotion" / "audio"
PUBLIC = ROOT / "video-remotion" / "public" / "audio"

TARGET_I = -16.0
TARGET_TP = -1.5
TARGET_LRA = 11.0


def duration(path: pathlib.Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def measure(path: pathlib.Path) -> dict:
    """Pass one: loudnorm in analysis mode prints a JSON blob on stderr."""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
         "-af", f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:print_format=json",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    blob = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", proc.stderr, re.S)
    if not blob:
        sys.exit(f"could not parse loudnorm analysis for {path.name}:\n{proc.stderr[-800:]}")
    return json.loads(blob.group(0))


def apply(path: pathlib.Path, m: dict, dest: pathlib.Path) -> None:
    """Pass two: apply the measured values, linearly, at the same format."""
    af = (
        f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}"
        f":measured_I={m['input_i']}:measured_TP={m['input_tp']}"
        f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
        f":offset={m['target_offset']}:linear=true:print_format=summary"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path),
         "-af", af, "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(dest)],
        check=True,
    )


def main() -> None:
    global SRC
    # Optional first argument: an alternate take directory (e.g. audio_aoede).
    # Only the take that is actually being cut gets copied into public/.
    if len(sys.argv) > 1:
        SRC = pathlib.Path(sys.argv[1])
        if not SRC.is_absolute():
            SRC = ROOT / SRC
    cues = sorted(SRC.glob("vo_0*.wav"))
    if not cues:
        sys.exit(f"no cues found in {SRC}")
    PUBLIC.mkdir(parents=True, exist_ok=True)

    for cue in cues:
        before = duration(cue)
        m = measure(cue)
        tmp = cue.with_suffix(".norm.wav")
        apply(cue, m, tmp)
        after = duration(tmp)

        # The whole reason for linear mode. If this ever trips, the cue windows
        # in content.ts no longer describe the audio and the film must be re-timed.
        if abs(after - before) > 0.02:
            sys.exit(f"{cue.name}: duration moved {before:.3f}s -> {after:.3f}s, refusing")

        tmp.replace(cue)
        shutil.copy2(cue, PUBLIC / cue.name)
        print(f"{cue.name}  {float(m['input_i']):6.1f} -> {TARGET_I:.1f} LUFS   {after:6.2f}s")

    print(f"\nnormalized {len(cues)} cues, copied to {PUBLIC.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
