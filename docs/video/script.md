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

On screen: `docs/video/gate-scene.js`, animated, in the order the VO names things. A buyer
slides in and is handed seven tools; it asks and is quoted with the volume break already
applied; it pushes for more and the engine deletes the model's proposal; then it tries to pay
the same ₹6,750 cart twice, once against a ₹50 cap and once against ₹10,000. The cart never
changes size and the gate does, both drawn through one pixels-per-rupee constant, so "over the
cap" is something the viewer sees rather than something the film asserts.

This replaced a camera pan across the static `architecture.svg`, which explained nothing to a
viewer who did not already know the system. The SVG still ships for the README and the form.

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

---

# Part 2 narration — seven cues, 3:00 to 5:00

**Changed decision, 2026-09-05.** PRODUCTION.md locked "Sirjan live for 3:00 to 5:00" and a
spoken seam. Part 2 is now narrated too, by the same voice, over a real captured run. The
reason is scheduling and nothing else: the form closes today.

Two consequences, both handled rather than hidden:

1. **The seam line changes.** Cue [6] said *"That is the claim. Here is me running it."* With
   nobody in the second half that sentence is false, so it is now *"That is the claim. Here it
   is running."* Scene 6 gets re-rendered.
2. **What is on screen has to carry the weight the presence used to.** So part 2 is the real
   thing executing, captured by `scripts/capture_run.py` against two live servers with the
   arrival time of every line recorded, and re-typeset at 28px under the same rule as part 1.
   The theatre page appears at the end as a closing shot and is described as what it is, a
   replay, because it is one.

Same voice settings as part 1. Same `[pause]` handling: real silence, not punctuation.

## [7] Two servers · target 3:00-3:18

> Two merchants. Two processes, two ports, two catalogs, two sets of audit records.
>
> *[pause 1.2s]*
>
> They are separate because two suppliers are separate. The contrast that follows does not
> work if they share anything.

On screen: the command, then both servers coming up, typed at their real arrival times.

## [8] Discovery and the quote · target 3:18-3:42

> The buyer is a stock client. It is handed a URL and nothing else. It finds seven tools,
> reads the published policy before it asks for a discount, and is quoted eleven rupees
> twenty five a unit on six hundred.
>
> Nobody asked for the volume break. It was owed, so it was applied.

Provenance: steps 1 through 4 of the captured run.

## [9] The cap · target 3:42-4:06

> Then it tries to pay. The cart is six thousand seven hundred and fifty rupees. The mandate
> allows fifty.
>
> *[pause 1.5s]*
>
> Refused, and the refusal names the overage. A buyer told only no cannot fix anything.

Provenance: step 10, `amount_over_cap`.

## [10] The other three · target 4:06-4:26

> A mandate minted for the other shop. Refused before anything is priced. An expired one, the
> same. The identical purchase replayed, and it is not charged twice.
>
> Four refusals, four different grounds, no model call in any of them.

Provenance: steps 11, 12 and 14.

## [11] The money · target 4:26-4:44

> A correct mandate, and the same cart is authorised and paid on Razorpay test mode. Then a
> card that is meant to decline, which declines, and nothing is marked paid.

Provenance: step 13 and the decline leg. Both legs are real test-mode payments.

## [12] The chain · target 4:44-4:56

> Every decision above, refusals included, is on a hash linked chain that verifies with the
> servers switched off.

On screen: `verify_offline.py`, and the word INTACT.

## [13] What is not claimed · target 4:56-5:00

> Mandate gated payment is Razorpay's. The self serve path to it is mine.

Cut on the line. The theatre page scrolls underneath, labelled as a replay.

## Timing

Roughly 210 words. The rest of the two minutes is the run playing at the speed it actually
ran, which is the point of capturing the timings rather than the text alone.
