"""Generate the part-1 narration, one WAV per cue, from docs/video/script.md.

The text below is copied from the script, which is the source of truth. Pauses
written as [pause Ns] in the script are generated as real silence here rather
than left for the model to infer from punctuation, exactly as the script asks.

Voice: the script's first choice is ElevenLabs "Raju" (Indian English). No
OpenAI voice is Indian English, so this uses `onyx` (the closest analogue to the
script's stated fallback, "Adam, American, default technical-narration") and the
`instructions` field to hold the delivery to a measured read. Swap VOICE and
re-run to audition another; each cue is a separate file so one bad read is
re-rendered without touching the rest.

Windows note: the system Python's CA bundle has expired certs, so the SSL
context is built from the venv's certifi rather than the default store.

    .venv/Scripts/python video-remotion/scripts/make_vo.py [--voice onyx] [--only 1]
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import ssl
import subprocess
import sys
import urllib.request

import certifi

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "video-remotion" / "audio"
MODEL = "gpt-4o-mini-tts"
VOICE = "onyx"

# Delivery, OpenAI path only. Chirp 3: HD takes plain text and ignores all of this, so on
# the GCP path the voice itself is the only lever and these do nothing.
#
# "calm" was the original and it is the reason part one sounds flat: it explicitly forbids
# enthusiasm and inflection. That was right for a film with a person in the second half to
# supply the energy. With both halves narrated it reads as monotone for five minutes.
STYLES = {
    "calm": (
        "Measured, calm technical narration for a documentary-style product film. "
        "Unhurried and low-key, with quiet authority. Land each full stop fully. "
        "No sales enthusiasm, no rising inflection at the end of sentences, no "
        "smiling tone. Read numbers and statute references plainly."
    ),
    "punchy": (
        "Energetic, confident narration for a product film that has something to prove. "
        "Lean forward. Vary the pitch and the pace: drive through the setup, then slow "
        "down and hit the numbers hard, because the numbers are the argument. Put real "
        "weight on the refusals -- 'refused', 'over the cap', 'veto' -- and let a short "
        "sentence land with a beat after it. Warm and human, never a hard sell and never "
        "an announcer. Crisp consonants."
    ),
}
INSTRUCTIONS = STYLES["calm"]

# One entry per cue. Strings are spoken; floats are seconds of real silence.
CUES: dict[str, list] = {
    "vo_01": [
        "A buyer's agent asks an Indian bolt manufacturer for sixty day payment terms. "
        "The merchant's own limit is ninety days. It refuses anyway.",
        2.5,
        "Not because of a policy. Because of a statute.",
    ],
    "vo_02": [
        "In February 2026, Razorpay and N P C I shipped agentic payments with Zomato, "
        "Swiggy and Zepto. Every one of those merchants was integrated by hand. The "
        "millions of long tail merchants on the platform have a spreadsheet, a WhatsApp "
        "catalog, and no path at all.",
        0.9,
        "Vendable is the self serve version of that. It takes a merchant's mess and "
        "produces the machine readable surface and the gated payment endpoint an A I "
        "buyer needs.",
    ],
    "vo_03": [
        "A stock Claude client connects with nothing but a U R L, and gets seven tools. "
        "It can search, quote, negotiate, reserve and buy.",
        0.7,
        "Two model calls exist in the whole system. Each has a deterministic verifier "
        "immediately downstream. Neither can move money.",
        1.5,
        "The L L M proposes. The engine disposes.",
    ],
    "vo_04": [
        "Over cap is refused, and it names the overage. A mandate minted for another shop "
        "is refused before anything is priced. An expired one, the same. Replay the "
        "identical purchase and it will not charge twice.",
        0.9,
        "Every refusal carries the reason that makes it actionable. That was the hardest "
        "bug in this build, and it is written up in the repo.",
    ],
    "vo_05": [
        "The negotiation prompt says persistence is not a reason. So I measured it. Over a "
        "hundred and five recorded calls, holding the line item fixed and varying only "
        "what the buyer said.",
        0.9,
        "Persistence beat both of the reasons the prompt names. Ageing stock moved the "
        "price by exactly zero. A buyer claiming the owner approved it scored second "
        "highest, and the injection scanner flagged none of them.",
        1.5,
        "And every median still landed on the published entitlement. The prompt failed. "
        "The engine held.",
    ],
    # Changed 2026-09-05. Part 2 is narrated rather than presented live, so
    # "here is me running it" is no longer true and the seam line says what the
    # second half actually is. Scene 6 of film.html re-renders to match.
    "vo_06": [
        "That is the claim. Here it is running.",
    ],
    # ---- part 2, 3:00 to 5:00, over the captured run --------------------
    "vo_07": [
        "Two merchants. Two processes, two ports, two catalogs, two sets of audit records.",
        1.2,
        (
            "They are separate because two suppliers are separate. The contrast that "
            "follows does not work if they share anything."
        ),
    ],
    "vo_08": [
        (
            "The buyer is a stock client. It is handed a U R L and nothing else. It finds "
            "seven tools, reads the published policy before it asks for a discount, and is "
            "quoted eleven rupees twenty five a unit on six hundred."
        ),
        0.8,
        "Nobody asked for the volume break. It was owed, so it was applied.",
    ],
    "vo_09": [
        (
            "Then it tries to pay. The cart is six thousand seven hundred and fifty "
            "rupees. The mandate allows fifty."
        ),
        1.5,
        "Refused, and the refusal names the overage. A buyer told only no cannot fix anything.",
    ],
    "vo_10": [
        (
            "A mandate minted for the other shop. Refused before anything is priced. An "
            "expired one, the same. The identical purchase replayed, and it is not charged "
            "twice."
        ),
        0.8,
        "Four refusals, four different grounds, no model call in any of them.",
    ],
    "vo_11": [
        (
            "A correct mandate, and the same cart is authorised and paid on Razorpay test "
            "mode. Then a card that is meant to decline, which declines, and nothing is "
            "marked paid."
        ),
    ],
    "vo_12": [
        (
            "Every decision above, refusals included, is on a hash linked chain that "
            "verifies with the servers switched off."
        ),
    ],
    "vo_13": [
        "Mandate gated payment is Razorpay's. The self serve path to it is mine.",
    ],
}


GCP_PROJECT = "cassandra-498318"
GCP_VOICE = "en-IN-Chirp3-HD-Aoede"


def speak_gcp(text: str, dest: pathlib.Path, token: str, voice: str) -> None:
    """Google Cloud TTS. Chirp 3: HD is the only en-IN option that actually
    sounds Indian, which is what the script asked for and what no OpenAI voice
    can give. Note Chirp 3: HD takes plain text only, no SSML, so the [pause]
    beats stay real silence spliced in by build() exactly as before.

    LINEAR16 at 24kHz mono is requested so the bytes are drop-in compatible with
    the OpenAI path and with normalize_vo.py; the response is a full WAV.
    """
    import base64

    payload = json.dumps(
        {
            "input": {"text": text},
            "voice": {"languageCode": "-".join(voice.split("-")[:2]), "name": voice},
            "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": 24000},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://texttospeech.googleapis.com/v1/text:synthesize",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "x-goog-user-project": GCP_PROJECT,
            "Content-Type": "application/json",
        },
    )
    ctx = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(req, context=ctx, timeout=180) as resp:
        body = json.load(resp)
    dest.write_bytes(base64.b64decode(body["audioContent"]))


def gcp_token() -> str:
    tok = os.environ.get("GOOGLE_ACCESS_TOKEN", "").strip()
    if not tok:
        sys.exit(
            "GOOGLE_ACCESS_TOKEN not set. In PowerShell:\n"
            "  $env:GOOGLE_ACCESS_TOKEN = (gcloud auth print-access-token)"
        )
    return tok


def api_key() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("OPENAI_API_KEY="):
            return line.split("=", 1)[1].strip()
    sys.exit("OPENAI_API_KEY not found in .env")


def speak(text: str, dest: pathlib.Path, key: str, voice: str) -> None:
    payload = json.dumps(
        {
            "model": MODEL,
            "voice": voice,
            "input": text,
            "instructions": INSTRUCTIONS,
            "speed": 0.98,
            "response_format": "wav",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    ctx = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(req, context=ctx, timeout=180) as resp:
        dest.write_bytes(resp.read())


def silence(seconds: float, dest: pathlib.Path) -> None:
    # Matches the TTS output format so concat never has to resample.
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r=24000:cl=mono",
            "-t",
            f"{seconds}",
            str(dest),
        ],
        check=True,
    )


def duration(path: pathlib.Path) -> float:
    out = subprocess.run(
        [
            "ffprobe",
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


def build(
    cue: str, parts: list, key: str, voice: str, work: pathlib.Path, provider: str = "openai"
) -> float:
    pieces: list[pathlib.Path] = []
    for i, part in enumerate(parts):
        piece = work / f"{cue}_{i:02d}.wav"
        if isinstance(part, (int, float)):
            silence(float(part), piece)
        elif provider == "gcp":
            speak_gcp(part, piece, key, voice)
        else:
            speak(part, piece, key, voice)
        pieces.append(piece)

    listing = work / f"{cue}.txt"
    listing.write_text("\n".join(f"file '{p.as_posix()}'" for p in pieces) + "\n", encoding="utf-8")
    dest = OUT / f"{cue}.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c",
            "copy",
            str(dest),
        ],
        check=True,
    )
    return duration(dest)


def select(spec: str) -> list[str]:
    """Cue keys for '1', '6,7,8' or '6-13'.

    Thirteen cues is too many to invoke one at a time, and the GCP path needs a fresh
    access token per session, so a single command that does the lot is the difference
    between one token and thirteen.
    """
    want: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = (int(x) for x in part.split("-", 1))
            want.extend(range(lo, hi + 1))
        elif part:
            want.append(int(part))
    keys = [f"vo_{n:02d}" for n in want]
    missing = [k for k in keys if k not in CUES]
    if missing:
        sys.exit(f"no such cue(s): {', '.join(missing)}")
    return keys


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="openai", choices=["openai", "gcp"])
    ap.add_argument("--voice", default=None)
    ap.add_argument(
        "--only",
        default=None,
        help="cue numbers: '1', a list '6,7,8', or a range '6-13'",
    )
    ap.add_argument("--suffix", default="", help="appended to the output dir name")
    ap.add_argument(
        "--style",
        default="calm",
        choices=sorted(STYLES),
        help="delivery, OpenAI path only; Chirp 3: HD ignores it",
    )
    args = ap.parse_args()
    if args.voice is None:
        args.voice = GCP_VOICE if args.provider == "gcp" else VOICE

    global OUT, INSTRUCTIONS
    INSTRUCTIONS = STYLES[args.style]
    if args.provider == "gcp" and args.style != "calm":
        print(f"note: --style {args.style} is ignored on the gcp path (Chirp 3: HD is plain text)")

    if args.suffix:
        OUT = OUT.with_name(OUT.name + "_" + args.suffix)
    OUT.mkdir(parents=True, exist_ok=True)
    work = OUT / "parts"
    work.mkdir(exist_ok=True)

    key = gcp_token() if args.provider == "gcp" else api_key()
    wanted = CUES if not args.only else {k: CUES[k] for k in select(args.only)}

    # Start from what is already measured. `--only` regenerates a subset, and writing just
    # that subset back would drop the durations of every cue it did not touch -- which is
    # the file build_film.py places the voice from, so the cut would silently lose them.
    durations = OUT / "durations.json"
    measured: dict[str, float] = {}
    if durations.exists():
        measured = json.loads(durations.read_text(encoding="utf-8"))

    total = 0.0
    for cue, parts in wanted.items():
        d = build(cue, parts, key, args.voice, work, args.provider)
        measured[cue] = round(d, 2)
        total += d
        print(f"{cue}  {d:6.2f}s", flush=True)
    print(f"total {total:.2f}s for {len(wanted)} cue(s)  voice={args.voice}")

    measured = {k: measured[k] for k in sorted(measured)}
    durations.write_text(json.dumps(measured, indent=2) + "\n", encoding="utf-8")
    print(f"durations.json now holds {len(measured)} cue(s)")


if __name__ == "__main__":
    main()
