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

**Two model calls exist in this system. Each has a deterministic verifier immediately
downstream, and neither can move money.**

| the model does | a deterministic engine then decides |
|---|---|
| reads a messy PDF and reports what it found | `validate_product` decides which SKUs are sellable |
| proposes a concession and writes a sentence | `PolicyEngine` checks the number before it is uttered |

A third was planned — compiling the merchant's plain-language trading rules into a
`MerchantPolicy` for them to confirm — and was cut. The policy is a hand-written
`fixtures/merchants/<id>/policy.json` instead, validated on load with unknown fields
rejected. Cutting it removed convenience, not reasoning: the engine that enforces those
rules is unchanged, and a compiler would only have written a file a merchant still has to
read and approve.

**Deliberately not an LLM:**

- **The mandate gate.** Whether ₹6,750 exceeds a ₹5,000 cap is arithmetic. A model asked to
  decide it would be right almost always, and "almost always" is not a property you put in
  front of someone's money. `vendable/mandate/gate.py` has no model call, reads nothing from
  any prompt, and fails closed on every ambiguity.
- **The policy engine.** Margin floors, volume ladders, MOQ, territory — declared data
  evaluated as a pure function, so the same line always gets the same answer. That is what
  makes 62 gate cases and 47 attacks reproducible rather than anecdotal.
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
| Red team, 47 attacks in 9 classes | **44 defended, 3 findings published** | [`evidence/redteam.md`](evidence/redteam.md) |
| Extraction vs hand-labelled truth | **100% on every field that affects money** | [`evidence/extraction.md`](evidence/extraction.md) |
| Test suite | 186 passing, no network, no credentials | `scripts/verify_offline.py` |

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
  confusion matrix caught what 47 hand-written attacks could not.
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

### Payment terms are half the negotiation

In Indian B2B, *"kya rate hai"* and *"kitne din ka credit"* are one question, not two. Nobody
pays the printed list price, and the number that gets agreed depends as much on when you pay
as on how much you buy. `2/10 Net 30` — two percent off for settling inside ten days — is
ordinary practice, and sellers routinely concede 60 or 90 days to close.

So `payment_terms_days` is an argument to `request_quote` and `negotiate`, and the ladder is
published in `get_policies` and `llms.txt`. Paying sooner earns a discount the same way a
volume break does: automatically, because it is a declared rule, not something a buyer should
have to haggle for.

It is bound, too. The terms are inside the quote's `cart_hash`, so taking the early-payment
price and then paying at 60 days is not a loophole — it is a different cart, and the capture
is refused by the same tamper check that catches an edited unit price.

### The statute no agentic-commerce protocol models

Under **s.15 of the MSMED Act**, where the supplier is a Udyam-registered micro or small
enterprise, the buyer must pay within **45 days** where a written agreement exists, or **15**
where none does. Breach carries compound interest at **three times the RBI bank rate** (s.16),
and since 1 April 2024 **s.43B(h) defers the buyer's own deduction** on the expense until it
is actually paid.

The consequence is the interesting part: a buyer's agent that negotiates Net 90 with such a
supplier wins a discount that costs its principal more than it saves, and creates a statutory
liability nobody at the table modelled. So Vendable refuses those terms rather than pricing
them, and says why:

> Net 60 cannot be agreed. This supplier is a Udyam-registered small manufacturer, so under
> s.15 of the MSMED Act a written agreement caps the period at 45 days. Paying later obliges
> the buyer to compound interest at three times the RBI bank rate under s.16, and defers the
> buyer's own deduction on the expense under s.43B(h) until it is actually paid. Ask for Net
> 45 or shorter.

**The exclusions are encoded as carefully as the rule**, because a guard that fired on every
Indian merchant would refuse business the law permits. Medium enterprises are outside the
protection. Udyam **traders** are outside s.43B(h), which reaches manufacturers and service
providers. `acme-fasteners` is a registered small *trader* and is therefore unconstrained;
`shakti-forgings` is a registered small *manufacturer* and is capped at 45 days. Both ship in
`fixtures/merchants/`, and the difference is the demo.

None of this is an LLM. It is `MerchantPolicy.statutory_max_credit_days()` — the whole statute
as a pure function, seven lines and no model call. OpenAI's ACP documentation states plainly
that "returns, tax, and fraud modeling are out of scope"; UCP and AP2 have no notion of
statutory payment terms either.

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
| [`docs/pitch.md`](docs/pitch.md) | the locked problem statement, and the claims that are banned |
| [`docs/PLAN.md`](docs/PLAN.md) | the build plan the phases were executed against |
| `docs/research/` | per-phase verification, the protocol landscape, and the competitive read — every claim with a source URL |
| `evidence/` | the numbers, each reproducible with one command |
| `redteam/suite.py` | `python -m redteam.suite` |
| `fixtures/merchants/` | two merchants, each a `catalog.json` beside a `policy.json` |
| `scripts/` | spikes, scorers, and the end-to-end demo |

## Verify it yourself

```bash
.venv/Scripts/python scripts/verify_offline.py    # tests pass with every socket blocked
.venv/Scripts/python -m redteam.suite             # 47 attacks
.venv/Scripts/python scripts/gate_matrix.py       # 62 gate cases
.venv/Scripts/python scripts/score_extraction.py  # extraction vs ground truth (needs a key)
.venv/Scripts/python scripts/demo_buy.py          # the full buy, over the wire
.venv/Scripts/vendable audit verify               # walk the hash chain
```

## Licence

MIT.
