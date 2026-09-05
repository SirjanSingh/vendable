"""Assemble the pitch video from rendered frames, the voice files, and the live take.

    .venv/Scripts/python.exe scripts/build_film.py --silent      # picture only, no voice yet
    .venv/Scripts/python.exe scripts/build_film.py               # picture + vo_01..06
    .venv/Scripts/python.exe scripts/build_film.py --part2 G:/vendable-video/raw/take3.mkv

The stages are separate on purpose. Part one can be watched and re-cut long before a voice
exists, and the voice can be re-recorded without touching the frames.

Voice placement comes from `docs/video/cues.json`, which `render_film.py` writes out of the
page itself. Each `vo_NN.mp3` is delayed to its cue's start, so re-timing a cue moves both
the picture and the voice and they cannot disagree.

Nothing here writes into the repo. Everything lands in `--out`, which defaults to G:.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CUES = REPO / "docs" / "video" / "cues.json"

# The submission form's hard cap. Going over is not a style note, it is a rejection.
MAX_SECONDS = 300.0


def ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        sys.exit(
            "ffmpeg is not on PATH. It ships with the chocolatey install at\n"
            "  C:\\ProgramData\\chocolatey\\bin\\ffmpeg.exe"
        )
    return exe


def run(args: list[str]) -> None:
    print("  $ ffmpeg " + " ".join(args[1:6]) + " ...")
    proc = subprocess.run(args, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        # ffmpeg puts everything on stderr, including the actual error, and it is long.
        # The last lines are the ones that say what went wrong.
        sys.exit("ffmpeg failed:\n" + "\n".join(proc.stderr.strip().splitlines()[-15:]))


def duration(path: Path) -> float:
    probe = shutil.which("ffprobe") or "ffprobe"
    out = subprocess.run(
        [
            probe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(out.stdout.strip())


def build_picture(frames: Path, fps: int, out: Path, name: str = "part1_silent.mp4") -> Path:
    n = len(list(frames.glob("f*.jpg")))
    if n == 0:
        sys.exit(f"no frames in {frames}. Run scripts/render_film.py first.")
    print(f"picture: {n} frames at {fps}fps = {n / fps:.2f}s")

    dst = out / name
    run(
        [
            ffmpeg(),
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frames / "f%06d.jpg"),
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(dst),
        ]
    )
    return dst


def add_voice(
    picture: Path,
    vo_dir: Path,
    out: Path,
    cues_file: Path | None = None,
    first: int = 1,
    name: str = "part1.mp4",
) -> Path:
    """Mix vo_NN onto the picture, each delayed to the start of its cue.

    `first` is the cue number the page's first scene corresponds to. Part one's scenes are
    vo_01..06 and part two's are vo_07..13, so the second half passes first=7 rather than
    keeping a second copy of this function.
    """
    cues_path = cues_file or CUES
    if not cues_path.exists():
        sys.exit(f"{cues_path} is missing. Run scripts/render_film.py to generate it.")
    cues = json.loads(cues_path.read_text(encoding="utf-8"))["cues"]

    files, delays = [], []
    for i, cue in enumerate(cues, start=first):
        # WAV as well as MP3: make_vo.py writes LINEAR16 WAVs, and looking only for .mp3
        # made every cue "missing" and the film silent, with a per-cue note that scrolled
        # past as if it were routine.
        found = next(
            (p for p in (vo_dir / f"vo_{i:02d}.wav", vo_dir / f"vo_{i:02d}.mp3") if p.exists()),
            None,
        )
        if found is None:
            print(f"  missing vo_{i:02d}.wav/.mp3 (cue {cue['id']}) -- skipping")
            continue
        files.append(found)
        delays.append(int(cue["at"] * 1000))

    if not files:
        sys.exit(f"no vo_NN.wav or .mp3 in {vo_dir}. See docs/video/script.md for the cues.")
    if len(files) != len(cues):
        # A cue with no voice is a silent stretch of finished film. It has to be loud here
        # or it is only discovered by watching all five minutes.
        sys.exit(f"only {len(files)} of {len(cues)} cues have audio in {vo_dir}. Refusing.")

    # A voice longer than the cue it belongs to keeps playing over the next scene, so two
    # narrators talk at once for the overlap. It is a fraction of a second, it sounds like a
    # bad edit rather than a bug, and nothing else here would catch it: the picture is
    # correct, the mix succeeds, and the duration is unchanged. Refuse instead.
    over = []
    for f, cue in zip(files, cues):
        vd = duration(f)
        if vd > cue["dur"]:
            over.append(f"{f.name} is {vd:.2f}s in a {cue['dur']}s cue ({cue['id']})")
    if over:
        print("voice does not fit its cue:", *over, sep="\n  ")
        sys.exit("Lengthen the cue in the page and re-render, or shorten the line.")

    print(f"voice: {len(files)} of {len(cues)} cues present, all inside their cues")

    args = [ffmpeg(), "-y", "-i", str(picture)]
    for f in files:
        args += ["-i", str(f)]

    chains = [f"[{i + 1}:a]adelay={d}|{d}[a{i}]" for i, d in enumerate(delays)]
    mix = "".join(f"[a{i}]" for i in range(len(files)))
    # normalize=0 keeps each cue at the level it was rendered at. With normalize on,
    # ffmpeg divides by the input count and every cue comes out quiet.
    # The mix ends when the last cue's voice ends, which is always before the picture does:
    # the final scene holds after its line. Two wrong ways to handle that, both tried:
    #
    #   -shortest alone      trims the PICTURE to the voice. Part two built at 139.68s
    #                        against 144s of frames and lost its closing line.
    #   apad + -shortest     apad generates silence forever and -shortest did not stop it
    #                        here, so ffmpeg encoded audio into an ever-growing file. It ran
    #                        27 minutes on a 30-second job before it was killed.
    #
    # So pad the audio, and bound the output by the picture's own measured length rather
    # than by whichever stream ffmpeg decides is shortest.
    chains.append(f"{mix}amix=inputs={len(files)}:normalize=0,apad[mixed]")
    picture_secs = duration(picture)

    dst = out / name
    run(
        args
        + [
            "-filter_complex",
            ";".join(chains),
            "-map",
            "0:v",
            "-map",
            "[mixed]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-t",
            f"{picture_secs:.3f}",
            str(dst),
        ]
    )
    got = duration(dst)
    # The failure both bugs above produced was a file of the wrong length that played fine.
    # Check the length against the picture that went in, every time.
    if abs(got - picture_secs) > 0.15:
        sys.exit(f"{dst.name} is {got:.2f}s but the picture is {picture_secs:.2f}s. Refusing.")
    print(f"{dst.name}  {got:.2f}s, matching the picture")
    return dst


def join(part1: Path, part2: Path, out: Path) -> Path:
    """Concatenate the two halves, normalising part 2 to part 1's format first.

    The concat *demuxer* would be cheaper but it requires identical codecs, resolution and
    timebase, and an OBS capture will not match a libx264 encode of JPEGs. The concat
    *filter* re-encodes, which is slower and correct.
    """
    dst = out / "master.mp4"
    run(
        [
            ffmpeg(),
            "-y",
            "-i",
            str(part1),
            "-i",
            str(part2),
            "-filter_complex",
            (
                "[0:v]scale=1920:1080,fps=30,setsar=1[v0];"
                "[1:v]scale=1920:1080,fps=30,setsar=1[v1];"
                "[0:a]aresample=48000[a0];[1:a]aresample=48000[a1];"
                "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]"
            ),
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "19",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(dst),
        ]
    )
    return dst


def level(src: Path, out: Path) -> Path:
    """One loudness pass across the whole cut.

    The AI narrator and a live microphone will not arrive at the same level, and the seam at
    3:00 is exactly where a jump is most audible. -16 LUFS is what YouTube normalises to, so
    matching it means the platform leaves the audio alone.
    """
    dst = out / "upload.mp4"
    run(
        [
            ffmpeg(),
            "-y",
            "-i",
            str(src),
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(dst),
        ]
    )
    return dst


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble the pitch video.")
    ap.add_argument("--frames", default="G:/vendable-video/frames")
    ap.add_argument("--vo", default="G:/vendable-video/raw")
    ap.add_argument("--out", default="G:/vendable-video/out")
    ap.add_argument("--part2", default=None, help="the finished second half, to join on")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--silent", action="store_true", help="stop after the picture")
    # Part two is a second rendered page rather than an OBS take, so it is built by this
    # same script: different frames, its own cue table, and cues numbered from 7.
    ap.add_argument("--part", type=int, default=1, choices=(1, 2))
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    two = args.part == 2
    silent_name = "part2_silent.mp4" if two else "part1_silent.mp4"
    voiced_name = "part2.mp4" if two else "part1.mp4"
    cues_file = (REPO / "docs" / "video" / "part2_cues.json") if two else CUES
    first_cue = 7 if two else 1

    final = build_picture(Path(args.frames), args.fps, out, silent_name)
    if not args.silent:
        final = add_voice(final, Path(args.vo), out, cues_file, first_cue, voiced_name)
        if args.part2:
            final = level(join(final, Path(args.part2), out), out)

    secs = duration(final)
    print(f"\n{final}  {secs:.2f}s  {final.stat().st_size / 1e6:.1f} MB")

    if final.name == "upload.mp4":
        if secs > MAX_SECONDS:
            print(f"OVER THE CAP by {secs - MAX_SECONDS:.1f}s. The form rejects over 5:00.")
            return 1
        print(f"under the 5:00 cap, with {MAX_SECONDS - secs:.1f}s to spare")
    else:
        print("this is an intermediate. Pass --part2 to produce upload.mp4.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
