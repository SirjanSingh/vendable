# Pitch video — production checklist

**This file is the handoff.** An agent session dies and takes its context with it; this file
does not. Anyone picking this up cold reads the next block and starts there.

---

## NEXT ACTION

> **Mount G:.** Then run, from `D:\projs\vendable`:
>
> ```
> .venv/Scripts/python.exe scripts/render_film.py --out G:/vendable-video/frames
> ```
>
> Nothing before that step is outstanding. See the checklist for what is already done.

**Blocked on Sirjan:** G: mounted · an ElevenLabs key in `.env` · the OBS take for part 2.

---

## The shape

5:00 hard cap, target 4:50. Two halves with a deliberate, spoken seam.

| Time | Who | On screen |
|---|---|---|
| 0:00-0:22 | AI VO | Cold open: the MSMED refusal types itself out |
| 0:22-0:55 | AI VO | The problem: hand-integrated launch merchants vs the long tail |
| 0:55-1:30 | AI VO | `architecture.svg` assembles as the VO names each part |
| 1:30-2:05 | AI VO | Real terminal output of the four refusals |
| 2:05-2:45 | AI VO | The experiment table builds; the persistence row lights amber |
| 2:45-3:00 | AI VO | Handoff, cut to black |
| 3:00-4:35 | **Sirjan** | OBS: two servers, the demo, the console, chain verify |
| 4:35-4:50 | **Sirjan** | Close: what is not claimed, and what broke |

Seam line, spoken: *"That is the claim. Here is me running it."*

## Locked decisions (do not relitigate)

- **No generative footage.** Every frame of part 1 is a real artifact from this repo or a
  typographic animation of a real result. The submission's thesis is that its claims are
  measured rather than asserted; AI b-roll of a warehouse would contradict that on screen.
- **AI narrator for 0:00-3:00, Sirjan live for 3:00-5:00.** The seam is stated, not hidden.
- **Indian English narrator.** Part 2 is Sirjan's voice; an American narrator makes the 3:00
  seam loud. First choice **Raju**, second **Monika Sogam**, fallback Adam. Audition all three
  on cue [1] before committing, it is one line and it sets the register.
- **Pay for ElevenLabs Starter ($6).** The free tier is non-commercial and requires attributing
  ElevenLabs on the video. Key goes in `.env` as `ELEVENLABS_API_KEY`, never into a chat.
- **`film.html` must stay deterministic.** No CSS transitions, no `requestAnimationFrame`.
  Every animation state is a pure function of `t`. If the same `t` stops producing the same
  pixels, the frames drift against the voice track and the whole timeline is wrong.

## Typography (locked)

On-screen type is where this kind of video usually fails. Rules, not preferences:

- **Sentence case for everything that is prose.** All caps costs 10-15% reading speed, because
  identical letter heights turn every word into the same rectangle and force letter-by-letter
  reading. It also reads as shouting. No Title Case either; it is a headline convention doing
  nothing here.
- **ALL CAPS only for stamps**: `REFUSED`, `INTACT`, `AUTHORISED`. Three to nine characters,
  tracked +0.08em, never a sentence.
- **Size floor: 28px at 1920x1080** for body, which is ~2.6% of frame height and survives a
  phone at 360p. Headlines 64-96px. Nothing smaller than 24px ever.
- **Line length under 46 characters** for the serif statements. Long measures are unreadable in
  motion because the eye has to track back.
- **Twelve words maximum on screen at once**, and each block holds for at least 4 seconds.
  On-screen reading runs ~3.5 words/second, and the viewer must be able to read it twice.
- **Do not screenshot the terminal.** Re-typeset its real text as HTML at 28px+. A screenshot of
  a real 12pt terminal is destroyed by YouTube's compression: thin mono glyphs are exactly what
  the encoder throws away. Same characters, legible.
- Contrast is already handled by the console palette: `--amber #E0A458` and `--b #B6BEC8` on
  `--ink #080A0E` both clear WCAG AA at these sizes.

## Why not Remotion

Considered and declined for this submission, not on merit. Remotion renders frame by frame
and is deterministic in the same way, so it offers no correctness advantage over the page
here, and it costs a Node plus React install with a build step on drives at 97% and 99% full
in a repo with no JavaScript tooling at all. Playwright was already a dependency, so the
renderer is a hundred lines and installs nothing.

Where Remotion would genuinely win is step 8: matching cue boundaries to the real voice
durations, which its Studio does against a waveform. If that step turns painful, reconsider
there. Not before.

## Paths

```
D:\projs\vendable\docs\video\
  PRODUCTION.md      this file
  script.md          the six narration cues
  film.html          the animated page, window.seek(t)
  assets\            real captured output, committed

G:\vendable-video\               (working files, never committed)
  raw\      OBS takes, vo_01..06.mp3
  frames\   ~5400 JPEGs at 30fps, ~1.3 GB
  out\      part1.mp4, master.mp4, upload.mp4
```

`ffmpeg` is at `C:\ProgramData\chocolatey\bin\ffmpeg.exe`. Playwright's Chromium is at
`D:/tmp/pw-browsers` (C: has no room; the scripts set this themselves).

## Checklist

### Session 1 — no Sirjan, no paid key needed
- [x] Schedule a session checkpoint so unfinished work is committed, not lost
- [x] This file, committed before any asset work
- [x] `docs/video/script.md`
- [x] Capture real assets from a live run (demo output, MSMED string, console shots)
- [x] `film.html` with deterministic `seek(t)` — proved by `render_film.py --check`
- [x] `scripts/render_film.py` and `scripts/build_film.py`
- [ ] Render part 1 silent, and **watch all three minutes**

### Session 2 — needs Sirjan
- [ ] Audition Raju / Monika Sogam / Adam on cue [1], pick one
- [ ] Generate `vo_01..06.mp3`, one file per cue so a bad read is re-rendered alone
- [ ] Measure real VO durations, re-time the cue boundaries in `film.html`, re-render
- [ ] Record the OBS take for part 2 (beats below)
- [ ] `scripts/build_film.py`, trim under 5:00, watch it start to finish
- [ ] Upload unlisted, paste the link here

## Part 2 beats (~95s), for the OBS take

Before recording: mount G:, and start the stack **in a terminal you own** — a server an agent
starts is a child of that job and dies with it.

```
.venv/Scripts/python.exe scripts/serve_demo.py     # acme :8080, shakti :8081
```

OBS: one scene, one window capture at 1920x1080, mic on its own audio track so levels can be
fixed without re-recording. Terminal font at ~18pt; the default is unreadable after YouTube
compresses it.

1. `demo_buy.py --decline`, and let it run. Do not narrate every line. Call out the volume
   break landing unasked, and the four refusals as they scroll.
2. `localhost:8080/console`, Ledger view. Refusals render as documents, approvals as
   hairlines. Say why: a refusal a merchant has to decode is one they learn to ignore.
3. Rehearsal tab. Type a prompt injection live. Flagged, 0% of discretionary spent.
4. Chain tab. Walk the chain. **INTACT.**
5. The declined payment: the authorisation stays valid, the money leg fails, nothing is
   marked paid.

Close: what is deliberately not claimed (not UAP, not a compliance product, two merchants not
three, nothing deployed), then one sentence on the `ToolError` bug, because the form says the
"what broke" question is the one they read first.

**Record a clean take early.** There is no time to discover on the 4th that the only take has
a stutter at 0:40.

## Verification (nothing is done because it was generated)

| Check | How |
|---|---|
| `film.html` is deterministic | Render `t=42.0` twice, the JPEGs must be byte-identical |
| Frames match the VO | Frame count equals `30 x` total VO seconds, within one frame |
| Part 1 plays | Watch all three minutes, not a thumbnail |
| Nothing on screen is fake | Every number greps back to `evidence/` or a captured run |
| Under the cap | `ffprobe` reports duration < 300s |
| Audio is level | `loudnorm` across the seam; VO and live mic do not jump |
| Repo still passes | `verify_offline.py` and the full suite, since `scripts/` gained files |

## Out of scope

Re-recording the negotiation cassette (costs money and ~26 minutes; the committed numbers are
the published result), `ngrok` for `payment.failed`, and deploying anything.

## Still blocking the submission, unrelated to this video

The repo is **private** and the form collects a **public** GitHub URL. Sirjan's call: going
public publishes SECURITY.md's H1/H2 and all of `what-broke.md`, which is deliberate and is an
asset for the question they read first, but it is a one-way door.
