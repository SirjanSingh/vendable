"""Synthesize a five-minute ambient bed to sit under the whole film.

    .venv/Scripts/python video-remotion/scripts/make_music_bed.py [--seconds 302]

Same argument as `make_intro_sfx.py`: nothing downloaded, everything generated from an
expression, so the film rebuilds from the repo with no licensed asset in a gitignored folder
waiting to die quietly. It also sidesteps the licence question entirely, which for a
submission video is worth more than a better-sounding track would be.

Tuned in F#, because the intro card's impact is 45Hz and 92Hz and landing the bed a few cents
away from that would beat audibly against it at the cut. The partials here are F#1, F#2, the
C#3 fifth and F#3.

Two things make it usable under narration rather than merely quiet:

  * **The speech band is scooped out.** Two wide bell cuts at 900Hz and 2.6kHz, which is
    where consonants live. A bed that is simply turned down still masks speech; a bed with a
    hole in it does not, and can then sit louder without fighting.
  * **Nothing has an onset.** No drums, no arpeggio, no melody. Every voice moves on a slow
    LFO between 19 and 37 seconds, none of them in phase with another, so the texture
    changes without any event for the ear to catch on. Anything with a transient pulls
    attention off the narrator every time it fires.

Written deliberately quiet, around -34 dB mean, on the assumption it is raised to taste in an
editor rather than used at unity. Duck it another 6 to 9 dB under each voice cue.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEST = ROOT / "video-remotion" / "public" / "audio" / "music_bed.wav"
SR = 48000

# (frequency, amplitude, LFO period in seconds, LFO phase)
PARTIALS = [
    (46.25, 0.30, 37.0, 0.0),  # F#1, the floor
    (92.50, 0.22, 23.0, 1.1),  # F#2
    (138.59, 0.13, 29.0, 2.2),  # C#3, the fifth
    (185.00, 0.07, 19.0, 0.4),  # F#3
    (277.18, 0.035, 31.0, 3.0),  # C#4, barely there, keeps it from sounding synthetic
]


def voice(freq: float, amp: float, period: float, phase: float, dur: float) -> str:
    """One partial, breathing on its own slow LFO."""
    lfo = f"(0.55+0.45*sin(2*PI*t/{period}+{phase}))"
    return f"aevalsrc='{amp}*sin(2*PI*{freq}*t)*{lfo}':d={dur}:s={SR}"


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate the ambient bed.")
    # 302 rather than 298: the film is 298.10s and the 4s intro card goes in front of it.
    # Running long is free, running short means a silent tail nobody notices until upload.
    ap.add_argument("--seconds", type=float, default=302.0)
    args = ap.parse_args()
    dur = args.seconds

    DEST.parent.mkdir(parents=True, exist_ok=True)

    sources = [voice(f, a, p, ph, dur) for f, a, p, ph in PARTIALS]
    # A breath of air on top so the bed is not purely sub. Filtered hard, and swelling on its
    # own slow cycle so it never arrives as an event.
    sources.append(
        f"anoisesrc=d={dur}:c=pink:a=0.10:r={SR}"
    )

    cmd: list[str] = ["ffmpeg", "-y", "-loglevel", "error"]
    for src in sources:
        cmd += ["-f", "lavfi", "-i", src]

    chains = [f"[{i}:a]anull[s{i}]" for i in range(len(PARTIALS))]
    chains.append(
        f"[{len(PARTIALS)}:a]highpass=f=5200,lowpass=f=11000,"
        f"volume=volume='0.05*(0.5+0.5*sin(2*PI*t/41))':eval=frame[air]"
    )

    mix_in = "".join(f"[s{i}]" for i in range(len(PARTIALS))) + "[air]"
    chains.append(f"{mix_in}amix=inputs={len(PARTIALS) + 1}:duration=longest:normalize=0[mix]")

    chains.append(
        "[mix]"
        # Keep the rumble out of the room and the hiss out of the top.
        "highpass=f=32,lowpass=f=12000,"
        # The hole the narration sits in.
        "equalizer=f=900:width_type=o:width=2.2:g=-11,"
        "equalizer=f=2600:width_type=o:width=2.0:g=-9,"
        # A slow stereo spread, so it is not a mono block in the middle of the image
        # where the voice also is.
        "aecho=0.8:0.7:410|730:0.22|0.16,"
        "alimiter=limit=0.85:level=disabled,"
        "volume=0.30,"
        f"afade=t=in:st=0:d=4,afade=t=out:st={dur - 6:.3f}:d=6,"
        f"apad=whole_dur={dur},atrim=0:{dur},"
        "aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=stereo[out]"
    )

    cmd += ["-filter_complex", ";".join(chains), "-map", "[out]", str(DEST)]
    subprocess.run(cmd, check=True)

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(DEST)],
        capture_output=True, text=True, check=True,
    )
    got = float(probe.stdout.strip())
    print(f"wrote {DEST.relative_to(ROOT)}  {got:.2f}s")
    if abs(got - dur) > 0.2:
        raise SystemExit(f"expected {dur:.2f}s, got {got:.2f}s")


if __name__ == "__main__":
    main()
