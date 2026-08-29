# Decisions

One entry per real fork in the road. Each records what was chosen, what was rejected, and
the reason — so the reasoning survives even where the code changes.

---

## D-001 — Python 3.13 everywhere, no version split
**2026-08-30**

Local interpreter is 3.13.2. The reused Cassandra Dockerfile pins `python:3.11-slim`.

**Chosen:** pin `python:3.13-slim` in the Cloud Run image so local and deployed runtimes match.

**Rejected:** keeping the 3.11 image. A version split between the machine where tests pass and
the runtime where the demo runs is exactly the kind of gap that surfaces at 2 a.m. on the last
day. Every dependency in `pyproject.toml` resolved cleanly on 3.13 in the first install — no
wheel lag was observed — so the usual argument for the older pin does not apply.

---

## D-002 — No GCP. Local-first, cloud deferred until new billing exists
**2026-08-30** · reversed the same day

The first version of this entry chose to reuse `cassandra-498318`. **That is no longer
available:** its credits expire 31 Aug and billing has been detached from the project. A new
billing account will be added later.

**Chosen:** build and verify **entirely on localhost**. Everything on the critical path is
local-capable:

- The MCP server runs under uvicorn on `127.0.0.1:8080`, and
  `claude mcp add --transport http vendable http://localhost:8080/mcp` connects a **stock,
  unmodified client** to it. The centrepiece demo — an agent given only a URL — is provable
  without a single cloud resource. The default `TransportSecuritySettings` allowlist is
  localhost-only, which is exactly right here.
- Persistence is **SQLite (WAL)** rather than Firestore. The audit chain's integrity comes from
  the hash chain, not from the store, so nothing is weakened. It also makes `pytest` runnable
  with no network and no credentials, which was already a Phase 1 gate.
- Razorpay test mode is a public API; it needs keys, not GCP.
- Gemini via the `google-genai` SDK works with a plain `GEMINI_API_KEY` — no Vertex, no project.

**Deferred, not cancelled:** the Cloud Run deploy. `deploy/` is still written and kept
parameterised by `PROJECT_ID`, so the deploy is a config change rather than a rewrite when
billing lands.

**Cost of this, stated honestly:** D-006 existed to retire deployment risk on night one, and
that is no longer possible. Two specific traps are now deferred rather than dead — the
`TransportSecuritySettings` → `421` hostname trap, and Cloud Run cold-start latency on the
first tool call. Both are pre-empted in code (allowed hosts read from an env var from the
start), but neither is *proven* until a real deploy happens. **This is now the top entry in the
risk register**, and if billing does not arrive in time, the submission ships as a
run-it-locally repo with a documented one-command start. That is a weaker demo than a live URL,
but not a broken one — and the README will say which it is.

---

## D-003 — Caches and venv live on D:, never C:
**2026-08-30**

C: has 443 MB free (100% used). pip's default cache is under `C:\Users\...\AppData\Local` and
will fail mid-install.

**Chosen:** `.venv` at `D:\projs\vendable\.venv`, `PIP_CACHE_DIR=D:\tmp\pipcache`. Any tool
that downloads large artefacts (Playwright browsers, model files) gets its cache path
explicitly redirected to D: before first use.

---

## D-004 — Headless payment: Payment Link -> netbanking -> mocksharp simulator
**2026-08-30** · this entry was written twice, and the second version is the true one

**First conclusion (wrong):** research said no headless test payment exists, so the last mile
needs a human or a scripted browser fighting a captcha. Recorded, then tested.

**What the live probe actually found.** Against real `rzp_test_` keys:

- `POST /v1/payments/create/json` (S2S) returns **HTTP 400, "The requested URL was not found
  on the server"** -- not routed at all until Razorpay enables it per merchant. Confirmed.
- **UPI is disabled** on this account: `/v1/preferences` reports `upi: false`,
  `upi_type: {collect: 0, intent: 0}`. The `success@razorpay` VPA is unreachable, so the
  path every tutorial recommends does not exist here.
- **Cards are a dead end for automation.** The flow hits an RBI save-card modal and then
  **hCaptcha**, which is designed to stop exactly what we are doing. It also needs a 3DS OTP.
- **Netbanking is enabled with 40 banks, and it is the way through.** Selecting a bank
  redirects to `https://api.razorpay.com/v1/gateway/mocksharp/payment` -- Razorpay's own test
  simulator, captioned *"This is just a demo bank page. You can choose whether to make this
  payment successful or not: Success / Failure"*. Two buttons. **No captcha, no OTP.**

**Chosen:** create a Payment Link, drive the hosted page with headless Chromium -- contact ->
Netbanking -> a bank -> **Success** on the mocksharp page.

Proven end to end with no human in the loop: link `plink_TViW6flmEw9j0t` reached
`status: paid`, and `pay_TViWVsPZPJM6Xa` fetched back as **`captured`, ₹499.00, netbanking**.

**Rejected:** S2S (not routed), UPI (disabled), cards (captcha), mocking the payment (the
submission's claim is that the money action is real), handing a human the link (breaks the
autonomy the demo exists to show).

**What this is, said precisely, because overclaiming here would be the worst kind of lie.**
The payment is a genuine Razorpay test-mode transaction: a real order, a real capture, a real
webhook. The *authorisation* leg is fully autonomous and fully gated -- mandate verified, cap
enforced, decision audited. The *settlement* leg still crosses a page built for a human
thumb, and Vendable drives it with a browser because Razorpay exposes no agent-facing entry
point for it. Choosing the Failure button instead is what produces the failure-path evidence
in Phase 5, which is a genuine gift: the simulator makes a declined payment reproducible on
demand.

That gap -- between *an agent decided to buy* and *the money moved* -- is the thing AP2 and
the agentic-payment rails exist to close. **This belongs in the README and the video, stated
plainly rather than glossed.** It is a better answer to Track 1's "show one failure handled
gracefully" than anything that could have been staged.

**Kept from the first version:** `PLAYWRIGHT_BROWSERS_PATH` is redirected to D: per D-003.
Chromium is 702 MB and C: has under 400 MB free.

## D-005 — The mandate travels as a tool argument, not an HTTP header
**2026-08-30** · supersedes the plan's "mandate-as-bearer on purchase only"

The plan assumed the buyer agent would present its mandate as `Authorization: Bearer`. Research
(`docs/research/PHASE-0.md` §G) shows **Claude Desktop's custom-connector dialog cannot send a
custom header** — it accepts a URL and optional OAuth client credentials, nothing else. Claude
Code *can* (`claude mcp add --header`), but a demo that only works in one client is a worse demo.

**Chosen:** `create_purchase(mandate: str, ...)` takes the compact-JWS mandate as a **tool
argument**. Works from any client, including Claude Desktop, with no OAuth.

**Rejected:**
- *Header-only* — excludes Desktop.
- *Full OAuth 2.1* — the SDK path demands an `issuer_url` and publishes an RFC 9728 discovery
  document. Days of work to gate one tool with a static token.
- *Token in the URL path* — leaks the credential into connector config, logs and screenshots.

**Security note this forces, and it is a good forcing:** because the mandate is an argument the
buyer supplies, the server may trust *nothing* about it until it has verified the signature,
`exp`, `aud`, and `jti` replay status itself. The gate has to be real. That is the correct
posture anyway; the transport constraint just removes the temptation to shortcut it.

---

## D-006 — Prove the transport on night one, locally
**2026-08-30** · amended by D-002

The original intent was to deploy a stub to Cloud Run immediately, to retire deployment risk
early. With billing gone (D-002), the deploy cannot happen tonight.

**What survives, and it is most of the value:** the risk being retired was never *Cloud Run*
specifically — it was **"can a stock, unmodified Claude client connect to my MCP server given
only a URL and actually call a tool?"** That is answerable on `localhost` tonight, against
spec 2026-07-28, with the real SDK and a real client. Spike B does exactly that.

**Chosen:** Phase 0 stands up a stub MCP server on localhost and connects Claude Code to it by
URL before any domain code exists. Every subsequent phase keeps that connection working —
if a stock client cannot call the tools, nothing downstream matters.

**Genuinely deferred:** TLS, cold starts, the `421` hostname trap, and multi-instance
behaviour. Tracked in D-002.

---

## D-007 — `amount == cap` is ALLOWED
**2026-08-30**

The AP2 `open_payment_mandate` constraint is `payment.amount_range { min, max }`. A range's
`max` is conventionally inclusive, and a buyer authorising "up to ₹5,000" who is refused at
exactly ₹5,000 would reasonably call that a bug.

**Chosen:** the gate refuses when `amount > max`, permits `amount == max`, and the audit record
names the boundary explicitly. `min` is treated the same way — `amount == min` passes.

Written down deliberately because it is the exact off-by-one a red-team suite should probe,
and an undocumented answer here is indistinguishable from an accident. Tests
`test_gate_allows_amount_equal_to_cap` and `test_gate_refuses_one_minor_unit_over_cap` pin it.

**All money is handled in integer minor units (paise).** No float ever touches an amount.
