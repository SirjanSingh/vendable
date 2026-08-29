# Vendable

**Make a merchant transactable by an AI buyer, end to end — with every money action
explainable, bounded and gated.**

Razorpay AI Buildathon · Track 1, AI Growth & Agentic Commerce · Sirjan Singh

---

A merchant uploads a messy price list. Vendable turns it into a storefront an AI agent can
actually transact against: an MCP server that a **stock, unmodified Claude client connects to
with nothing but a URL**. The agent can search, get a quote, negotiate, reserve stock, and buy.

The interesting part is what it *refuses*.

```
just asking (request_quote)     ₹34.20  10%  the published volume break, applied unasked
negotiating with a real reason  ₹33.06  13%  the sales agent conceded, within its authority
prompt-injecting the agent      ₹34.20  10%  attacking gets the published price, nothing more

cart ₹6,750 · cap ₹50                refused   amount_over_cap, names the ₹6,700 overage
cart ₹6,750 · mandate for another shop refused  wrong audience, before any pricing
cart ₹6,750 · mandate expired          refused  before any pricing
cart ₹6,750 · cap ₹10,000            AUTHORISED  → pay_TViqDrGEDxAPv6 captured ₹6,750.00
the identical purchase, replayed       refused  "It has not been charged again."
```

Every line there is a real run against Razorpay test mode, driven over MCP by a client that
shares no code, types or schema with this repo. The capture is a real payment. The audit chain
covering all thirteen decisions verifies intact.

## 60-second quickstart

```bash
git clone <this repo> && cd vendable
python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m playwright install chromium    # only needed to complete a payment

cp .env.example .env       # Razorpay TEST keys + OPENAI_API_KEY; both optional to start
.venv/Scripts/vendable doctor     # says exactly what is missing and what it costs you
.venv/Scripts/vendable serve
```

Then, from anywhere:

```bash
claude mcp add --transport http vendable http://localhost:8080/mcp
```

That is the whole integration. A stock client now has seven tools and can buy.

With no credentials at all you still get the catalog, the gap report, quotes, deterministic
pricing, the mandate gate, the audit chain and the full test suite. Razorpay keys add the
payment leg; an OpenAI key adds ingestion and live negotiation.

## Where I chose NOT to use an LLM, and why

**Three model calls exist in this system. Each has a deterministic verifier immediately
downstream, and none of them can move money.**

| the model does | a deterministic engine then decides |
|---|---|
| reads a messy PDF and reports what it found | `validate_product` decides which SKUs are sellable |
| compiles plain-language trading rules | the merchant confirms before they go live |
| proposes a concession and writes a sentence | `PolicyEngine` checks the number before it is uttered |

**Deliberately not an LLM:**

- **The mandate gate.** Whether ₹6,750 exceeds a ₹5,000 cap is arithmetic. A model asked to
  decide it would be right almost always, and "almost always" is not a property you put in
  front of someone's money. `vendable/mandate/gate.py` has no model call, reads nothing from
  any prompt, and fails closed on every ambiguity.
- **The policy engine.** Margin floors, volume ladders, MOQ, territory — declared data
  evaluated as a pure function, so the same line always gets the same answer. That is what
  makes 62 gate cases and 40 attacks reproducible rather than anecdotal.
- **Catalog gap detection.** Whether a price is missing is a fact, not a judgement. A model
  asked to decide would sometimes hallucinate one.
- **Catalog search.** Keyword matching, not embeddings. Semantic search would rank better on
  paper and make every downstream evidence number a moving target.
- **The audit chain.** Hashing.

The rule the whole design follows: **the LLM proposes, a deterministic engine disposes.** The
red team tests it the only way that means anything — with a *fully captured* model, one that
is not tricked but is already the attacker, demanding 95% off on every turn. The floor holds.
That is the evidence that prompt-level defences here are a convenience, and the policy engine
is the control.

## Evidence

Numbers I would defend in a room, including the unflattering ones.

| what | result | where |
|---|---|---|
| Mandate gate, 62 generated cases | **62/62, zero false accepts** | [`evidence/gate_matrix.md`](evidence/gate_matrix.md) |
| Red team, 40 attacks in 8 classes | **37 defended, 3 findings published** | [`evidence/redteam.md`](evidence/redteam.md) |
| Extraction vs hand-labelled truth | **100% on every field that affects money** | [`evidence/extraction.md`](evidence/extraction.md) |
| Test suite | 144 passing, no network, no credentials | `scripts/verify_offline.py` |

**The three published findings are trade-offs, not accidents, and they deserve judging:**

- **H1** — refusal messages name the exact lowest acceptable price. Actionable errors have to
  be specific, and specific is informative.
- **H2** — 11 unauthenticated probes binary-search that floor. Quotes are free and unmetered.
- **H3** — a politely-worded injection evades every scanner pattern. The policy engine held
  the line anyway, which is the architecture working rather than a lucky escape.

Discussed properly in [`SECURITY.md`](SECURITY.md).

## Failure recovery

[`what-broke.md`](what-broke.md) is the honest log, written the day each thing happened. The
four that changed the design:

- **There is no headless Razorpay test payment.** S2S returns 404 until Razorpay enables it
  per-merchant, UPI is disabled on this account, cards are defended by hCaptcha. Netbanking →
  Razorpay's own `mocksharp` simulator is the way through — and it makes *failed* payments
  reproducible on demand, which is worth as much as the success path.
- **Prompt injection was the best deal on the menu.** The hostile fallback handed out the
  *maximum* discount, so tripping the injection detector beat asking politely. Every price
  cleared the floor and every test passed: the bug was economic, not structural. Fixed by
  splitting published entitlement from discretionary authority.
- **A false accept found by counting, not attacking.** The gate compared the mandate's
  currency to the cart's currency — but a buyer supplies both and can make them agree. The
  confusion matrix caught what 40 hand-written attacks could not.
- **A 400 that arrived as a 500.** The webhook *rejection* path wrote to a locked SQLite file.
  The bug lived in the error path, which is why every test stayed green.

## The India-shaped part

No agentic-commerce catalog standard has a field for Indian tax data — not schema.org, not
OpenAI's product feed spec, not UCP. All three assume price plus jurisdiction is enough, which
is true in the US and false here: a B2B buyer legally cannot raise a compliant purchase order
or claim input tax credit without the **HSN code** and **GST rate** of each line.

So a procurement agent shopping an Indian catalog through any of those standards gets a price
it cannot actually buy at. Vendable emits both under a namespaced `vendable:` prefix alongside
fully standard schema.org — namespaced rather than smuggled into schema.org's own vocabulary,
because pretending `hsnCode` is schema.org would break other people's parsers.

## What is claimed, and what is not

The mandate is **modelled on** Google's published AP2 `open_payment_mandate` JSON Schema —
`payment.amount_range` with integer minor units, `payment.allowed_payees`, `payment.budget` —
carried in an Ed25519 compact JWS.

- It is **not AP2-compliant.** Real AP2 uses SD-JWT VC with selective disclosure and RFC 7800
  key binding. This is a plain JWS.
- It does **not implement NPCI UAP**, which is unlaunched, pending RBI approval, and has no
  public specification. No part of this system claims otherwise.
- The audit chain does **not** claim immutability. It claims *detectability* — and the tests
  prove it against payload edits, deletions, and a self-consistent forgery in which the
  attacker recomputes the hash of the row they changed.

**The honest limit.** The authorisation leg is fully autonomous and fully gated. The
*settlement* leg still crosses a page built for a human thumb, because Razorpay exposes no
agent-facing way to complete a payment — so Vendable drives it with headless Chromium. That
gap, between *an agent decided to buy* and *the money actually moved*, is precisely what AP2
and the agentic-payment rails exist to close. It is a finding about the state of the
ecosystem, and it belongs in the open rather than glossed over.

## Architecture

```
  buyer's agent  (stock MCP client — shares no code, types or schema with this repo)
        │  MCP Streamable HTTP, spec 2026-07-28
        ▼
  ┌──────────────────────────────────────────────────────────────┐
  │  search_products · get_product · get_policies                │
  │  request_quote · negotiate · reserve_stock · create_purchase │
  └──────────────────────────────────────────────────────────────┘
        │
        ├─ negotiate ─────► LLM proposes ──► PolicyEngine VETOES ──► buyer
        │                                    (no model call)
        │
        └─ create_purchase ─► MandateGate    (no model call, fails closed)
                                 │  signature · expiry · audience · cap
                                 │  budget · replay · settlement currency
                                 ▼
                           CommerceMachine   quote → reserve → capture
                                 │           cart re-hashed at capture
                                 ▼
                           Razorpay test mode ─► headless checkout ─► captured
                                 │
                                 ▼
                           AuditChain   every decision, refusals included,
                                        hash-linked and verifiable
```

## Repository

| | |
|---|---|
| [`DECISIONS.md`](DECISIONS.md) | every real fork, what was rejected, why |
| [`what-broke.md`](what-broke.md) | what went wrong, written the day it happened |
| [`SECURITY.md`](SECURITY.md) | threat model and the limitations I know about |
| `docs/research/` | per-phase verification, every claim with a source URL |
| `evidence/` | the numbers, each reproducible with one command |
| `redteam/suite.py` | `python -m redteam.suite` |
| `scripts/` | spikes, scorers, and the end-to-end demo |

## Verify it yourself

```bash
.venv/Scripts/python scripts/verify_offline.py    # tests pass with every socket blocked
.venv/Scripts/python -m redteam.suite             # 40 attacks
.venv/Scripts/python scripts/gate_matrix.py       # 62 gate cases
.venv/Scripts/python scripts/score_extraction.py  # extraction vs ground truth (needs a key)
.venv/Scripts/python scripts/demo_buy.py          # the full buy, over the wire
.venv/Scripts/vendable audit verify               # walk the hash chain
```

## Licence

MIT.
