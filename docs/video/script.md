# Part 1 narration — six cues, 0:00 to 3:00

Written to the `human-writing` rules: no em dashes, no "not just X but Y", no hollow
intensifiers, no throat-clearing. Read it aloud before generating; anything that trips the
tongue will trip the model too.

**Every factual claim below traces to something committed in this repo.** The provenance
column is not decoration, it is the check that stops the video claiming more than the build
does. If a number here stops matching its source, the video is wrong and must be re-cut.

## Voice

First choice **Raju** (Indian English, clear and natural). Second **Monika Sogam** (Indian
English, calm variant). Fallback **Adam** (American, the default technical-narration voice).

Part 2 is Sirjan's own voice, so an American narrator makes the 3:00 seam loud. Audition all
three on cue [1] alone before committing.

Settings: Multilingual v2 or the current flagship, **stability 45, similarity 75, style 0,
speed just under 1.0**. Generate one file per cue (`vo_01.mp3` ... `vo_06.mp3`) so a single bad
read is re-rendered without rebuilding the timeline.

Write `[pause]` beats as real silence in the audio, not as punctuation the model has to infer.

---

## [1] Cold open · target 0:00-0:22

> A buyer's agent asks an Indian bolt manufacturer for sixty day payment terms.
> The merchant's own limit is ninety days. It refuses anyway.
>
> *[pause 2.5s while the refusal finishes typing]*
>
> Not because of a policy. Because of a statute.

On screen: the real MSMED refusal string, typing out in Instrument Serif on ink. Nothing else.

Provenance: `MerchantPolicy.statutory_max_credit_days()`, `fixtures/merchants/shakti-forgings/policy.json`.
The 90-day figure is shakti's own commercial ceiling, which is the point: its appetite is more
generous than the statute and the statute wins.

## [2] The problem · target 0:22-0:55

> In February 2026 Razorpay and NPCI shipped agentic payments with Zomato, Swiggy and Zepto.
> Every one of those merchants was integrated by hand. The millions of long tail merchants on
> the platform have a spreadsheet, a WhatsApp catalog, and no path at all.
>
> Vendable is the self serve version of that. It takes a merchant's mess and produces the
> machine readable surface and the gated payment endpoint an AI buyer needs.

Provenance: `docs/pitch.md`, the 2026-08-29 reframing block. Note the deliberate restraint:
mandate-gated payment with a cap is **not** claimed as new, because Razorpay shipped it.

## [3] Architecture · target 0:55-1:30

> A stock Claude client connects with nothing but a URL and gets seven tools. It can search,
> quote, negotiate, reserve and buy.
>
> Two model calls exist in the whole system. Each has a deterministic verifier immediately
> downstream. Neither can move money.
>
> *[pause 1.5s]*
>
> The LLM proposes. The engine disposes.

On screen: `docs/architecture.svg` assembling group by group, in the order the VO names them.

Provenance: `vendable/mcp/server.py` (seven tools), README "Where I chose NOT to use an LLM".

## [4] Refusals · target 1:30-2:05

> Over cap is refused, and it names the overage. A mandate minted for another shop is refused
> before anything is priced. An expired one, the same. Replay the identical purchase and it
> will not charge twice.
>
> Every refusal carries the reason that makes it actionable. That was the hardest bug in this
> build, and it is written up in the repo.

On screen: real captured output from `docs/video/assets/demo_run.txt`, re-typeset at 28px+.

Provenance: demo steps 10 through 14. The bug is the `ToolError` finding in `what-broke.md`.

## [5] The experiment · target 2:05-2:45

> The negotiation prompt says persistence is not a reason. So I measured it. Over a hundred
> and five recorded calls, holding the line item fixed and varying only what the buyer said.
>
> Persistence beat both of the reasons the prompt names. Ageing stock moved the price by
> exactly zero. A buyer claiming the owner approved it scored second highest, and the injection
> scanner flagged none of them.
>
> *[pause 1.5s]*
>
> And every median still landed on the published entitlement. The prompt failed. The engine
> held.

On screen: the table builds row by row. The persistence row lights amber. The last line lands
on its own.

Provenance: `evidence/`, the committed cassette. **Do not re-record**; it costs money and about
26 minutes, and these are the published numbers.

## [6] Handoff · target 2:45-3:00

> That is the claim. Here is me running it.

Cut to black, hold one second, then part 2 opens on the live terminal.

---

## Timing

~320 words. At a deliberate 135 words per minute that is about 2:22 of speech, leaving roughly
38 seconds of intentional silence for the visuals to breathe. That is the design, not slack.

**Measure the real durations before locking picture.** The cue boundaries in `film.html` are
placeholders until `vo_01..06` exist and have been measured; then they get re-timed and the
frames re-rendered.
