# Razorpay AI Buildathon — "Build. Show. Get hired."

Researched 2026-08-23. Source of truth: the copy embedded in the live page bundle at
`razorpay.com/buildathon/` (the page is client-rendered, so plain fetches return an empty
shell) plus the live Google Form. Re-verify before submitting.

**This is not a hackathon. It is a hiring funnel with a build artifact as the resume.**
There is no prize pool. The prize is an internship offer.

## The offer

- INR 75,000 / month stipend
- 6 or 12 months, candidate's choice
- **In-person, Bangalore, starting September**
- Role: AI Builder Intern — "turn ambiguous business and product problems into working AI
  systems, prototypes, automations, and agentic experiences"

## Hard gates (check these before spending a single hour)

| Gate | Value | Note |
|------|-------|------|
| Who | **Students only** | "student-only program" |
| Graduation year | **2027, 2028 or 2029 only** | The form's dropdown has exactly these three options. No other value can be submitted. |
| Location | Bangalore, in-person, from September | The form asks yes/no. "No" is a visible disqualifier. |
| Deadline | **Applications close 5 September 2026** | ~13 days from 2026-08-23 |
| Team | Not mentioned anywhere; the form collects one name | Treat as **solo**. |

## Process

Four steps, per the page:

1. Pick a track
2. Build something real
3. Show your work: repo, 5-min video, architecture
4. If it has signal, they call you in

No resume screening. No aptitude test. No group discussion. Shortlisted builders go
straight to a panel. The `/ai-builders` sibling page claims a **48-hour** callback.
They still collect a resume; they say they do not screen on it.

## The form — 12 answers, one shot

`https://forms.gle/d9r2gvxp8cmoZhon9` (titled "Razorpay AI Builder Internship 2026")

About you: Full name · College name · Graduation year (2027/2028/2029) ·
In-person from September (yes/no) · 6 or 12 month preference

About the build: Selected track · Project name/title · Project objectives ("What does it
solve?") · **GitHub repo URL, public** · **5-min pitch video link** (unlisted is fine) ·
**Build challenges & technical obstacles** ("What issues did you face while building, and
how did you solve them?")

Then: a required confirmation checkbox reading *"I confirm that this is my official final
project submission. I understand that no further changes or edits can be made after
submitting."*

> **Operational consequence: do not open the form until the repo and video are final.**
> There is no edit-after-submit. The site's own note says the last question — what broke
> and how you got out — "is the one we read first."

The site's checklist also lists a resume file; the form as served has no upload field.
Have a PDF ready either way.

## The five tracks (verbatim briefs and pass bars)

### Track 1 — AI Growth & Agentic Commerce
*Grow the merchant's revenue, and make them sellable to AI buyers.*
- **Brief:** an agent that grows revenue for a merchant on **Razorpay test-mode APIs**, or
  that makes a merchant transactable by an AI buyer end to end.
- **Why now:** NPCI's UAP and the protocol race (ACP, AP2, x402) make agent-to-agent
  commerce the open problem of the year; Razorpay's in-app pilots are already live.
- **Directions:** conversational in-app checkout · agent-readable catalog · upsell &
  cross-sell agent · campaign orchestrator
- **Pass bar:** every money action explainable, bounded and gated. Show the audit trail and
  one failure handled gracefully.

### Track 2 — AI Risk Manager
*Stop the merchant losing money to fraud, returns and chargebacks.*
- **Brief:** a working detector, verifier or auto-responder for **one** class of loss, with
  measured precision and recall on a **held-out test set**.
- **Directions:** chargeback evidence responder · return-risk scorer · fraud-spike detector
  · abuse-ring sentinel
- **Pass bar:** honest metrics **including false-positive cost**. Strictly defense-only —
  anything offense-capable is **disqualified**.

### Track 3 — AI Revenue Recovery
*Find revenue that's slipping away and win it back.*
- **Brief:** an agent that detects revenue at risk, determines the right intervention, and
  **executes a bounded recovery workflow** — payment failures, checkout abandonment,
  overdue receivables.
- **Directions:** payment degradation → root cause → recovery action · checkout drop-off
  recovery · failed-subscription recovery · B2B receivables chaser · mandate retry
  sequencer · Hinglish voice recovery · promise-to-pay tracker
- **Pass bar:** don't just identify the problem. Show **measured money recovered across a
  batch**, with compliant escalation, stopping rules, and an audit trail.

### Track 4 — AI Finance Controller
*Run the books and the cash position.*
- **Brief:** an agent that closes one finance-ops loop across a **50+ record batch of
  synthetic data**, reporting its match rate and the exceptions it could not resolve.
- **Why now:** "verification capacity, not generation speed, is the bottleneck."
- **Directions:** multi-source reconciliation · settlement Q&A agent · forward cash
  forecaster · tax-line matcher
- **Pass bar:** throughput + measured accuracy + an honest exception list. One cherry-picked
  match proves nothing.

### Open Track
*Build what you believe should exist.* Any domain. Explicitly **not** an easier bar:
"Show a real problem, a working product, meaningful use of AI, and evidence that it creates
value. The same bar for execution, reliability, and depth applies here."

## Rubric (their words)

| Signal | What they ask |
|--------|---------------|
| Problem taste | did you pick something that actually matters |
| Build quality | does it run, is it structured, would you trust it |
| AI judgment | the right tool in the right place, **and where you chose not to use one** |
| Failure recovery | what broke, and what you did about it |

## Reading the rubric against our other two hackathons

The shared demand across all three is the same: **an agent that takes bounded action and
proves it with numbers.** But note where Razorpay is *stricter* than Devpost:

- **Measured metrics on a batch are mandatory** in tracks 2/3/4. Devpost judges accept a
  single happy-path demo; Razorpay explicitly rejects "one cherry-picked match."
- **They want the failure story in writing.** Devpost never asks. Keep a running
  `what-broke.md` from day one — do not reconstruct it on Sep 4.
- **No Google Cloud requirement.** ATA forces Gemini 3.5+ / ADK / a GCP service.
  Razorpay does not care what stack you use, which means the ATA stack is free to reuse.
- **AI judgment includes restraint** — "where you chose not to use one." A deterministic
  reconciler with an LLM only at the exception boundary scores *better* here, and is also
  cheaper to build.

## Useful Razorpay tech (real, not README name-dropping)

- **Razorpay MCP Server** — remote (hosted, `npx` setup) or local (Docker). 35+ tools over
  the payments API. Auto-detects environment from the key.
- **Test-mode API keys** (`rzp_test_...`) — track 1's brief names test mode directly.
- 400+ documented API endpoints and an `llms.txt` in the developer docs.
- Prior art they brag about: Slash, Call-E, Agentic Platform, Agentic Payments, Agent Studio.
  Do not rebuild one of these badly.

## Calendar collision

- **1 Sep** — All Things Agentic
- **5 Sep** — Razorpay Buildathon (this)
- **10 Sep** — Agentic Cinema

Razorpay lands in the 4-day gap after ATA. That is not enough time to build a fintech agent
from zero *and* the ATA agent. The only sane plays are (a) one architecture serving multiple
submissions, or (b) drop one.

## Open questions for Sirjan

1. Graduation year — is it 2027, 2028 or 2029? If not, this is over before it starts.
2. Bangalore, in person, from September — yes or no? An honest "no" almost certainly ends it.
3. Does a 6-12 month in-person internship starting next month fit around the AARM work?
