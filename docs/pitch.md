# Vendable — make a long-tail merchant transactable by AI buyers

- Status: **LOCKED WINNER** (2026-08-29)
- Last scored: 2026-08-23 · reframed 2026-08-29 after deep research
- Dual-submit: **none.** ATA and Cinema both dropped — Razorpay is the sole target.
- Build plan: see `docs/PLAN.md`. Protocol decisions: `docs/research/agentic-commerce-protocols.md`.
  Crowd and Cassandra lessons: `docs/research/crowd-recon.md`.

> **2026-08-29 reframing — read this before the one-liner below.**
> Razorpay + NPCI shipped agentic payments in production in Feb 2026 ("Agentic Payments on
> Claude", live with Zomato, Swiggy, Zepto, via UPI Reserve Pay: per-merchant cap, no
> per-transaction PIN, instant revoke). **Mandate-gated agent payment with a spending cap is
> therefore not a new claim.** What is still absent publicly: merchant-facing developer docs, a
> machine-readable catalog schema, and any self-serve path — all three launch merchants were
> hand-integrated. Vendable is **the self-serve version of what they demoed for Zomato**, built
> on public test-mode primitives. Pitch it that way, not as an invention.
>
> Two additions from the same research: implement an **AP2-*shaped*** mandate
> (`open_payment_mandate`, `payment.amount_range.max`) and claim compliance with nothing; and
> ship a namespaced `hsnCode` / `gstRate` catalog extension, because **no agentic-commerce
> standard has a GST or HSN field** — an India-shaped gap worth naming.

## One-liner

Razorpay's agentic commerce pilots work beautifully for Zomato, PVR INOX and Bluestone
because each one was integrated by hand, while the millions of long-tail merchants on the
platform have no path at all to being bought from by an AI agent. Vendable takes a
merchant's existing mess — a Shopify export, a WhatsApp catalog, a PDF price list — and
autonomously produces and maintains the machine-readable surface plus the gated payment
endpoint an AI buyer needs, then proves it worked by letting a buyer agent that has never
seen the merchant complete a purchase.

## Tracks

- Razorpay Buildathon: **Track 1 — AI Growth & Agentic Commerce**, second half of the brief
  ("makes a merchant transactable by an AI buyer end to end")
- All Things Agentic: **Taskmaster**
- Agentic Cinema partner: none that is honest. See risks.

### Why Track 1 and not Track 3

Per `docs/research/razorpay-saturation-map.md`: eight of Razorpay's shipped Agent Studio agents map onto
the published direction list, and Track 3 owns the densest cluster of them. Track 1's
"agent-readable catalog" has no shipped equivalent, is the hardest to enter (you must
understand UCP / ACP / AP2 / x402 / Reserve Pay first), and is Razorpay's stated strategic
frontier. Thinnest field, highest signal.

## Who hurts, what happens without the agent

A mid-size Indian merchant on Razorpay. AI-sourced retail traffic grew 393% YoY and
converts 42% better than organic, and every protocol that matters (UCP, ACP, AP2) assumes
the merchant exposes structured catalog, real-time price and availability, policy metadata,
and an authorization-aware payment endpoint. This merchant has none of that. They have a
spreadsheet, a WhatsApp catalog, and GST invoices. Today the only way they become
agent-transactable is if Razorpay assigns engineers to them, which happens for Zomato and
does not happen for them.

## What the agent does (not what it says)

1. **Ingests the mess.** Shopify/Woo export, PDF price list, website, WhatsApp catalog
   dump. LLM used here — extraction from genuinely unstructured input is what it is for.
2. **Normalises to a canonical product graph** and deterministically validates the fields
   agentic commerce actually requires: price, real-time availability, GST/HSN, shipping
   promise, returns policy, territory. Missing fields become a work queue, not a silent gap.
3. **Chases the gaps.** Where a required field cannot be derived, the agent asks the
   merchant one bounded question at a time and re-validates. This is the async Taskmaster
   loop.
4. **Publishes three parallel surfaces**, because that is what agent-ready means in
   practice: JSON-LD / schema.org on the product page, an enriched feed, and an **MCP
   endpoint** an agent orchestrator can call directly.
5. **Stands up a gated payment intent endpoint** on **Razorpay test-mode**. Before it will
   create an order it verifies an authorization chain in the AP2 / Reserve Pay shape: who
   authorized, what scope, what cap, what expiry, is it revoked. Over cap, expired or
   unscoped is refused, with a reason.
6. **Writes an append-only audit record** for every money action: the authorization chain,
   the inputs, the decision, the outcome. DPDP-shaped — explainable, auditable, reviewable.
7. **Keeps it true.** Continuously reconciles published surface against the merchant's
   source of truth and republishes on drift. A stale price shown to an AI buyer is a
   mispriced sale.

## The demo shot that cannot be faked

A **second, adversarial buyer agent** — separate process, no shared state, never seen this
merchant — is pointed at the published MCP endpoint and told to buy something under a
₹2,000 mandate.

1. It discovers the catalog and assembles a cart.
2. It attempts an over-cap purchase. **Vendable refuses it, with a reason.** (This is
   Track 1's required "one failure handled gracefully," and it is real, not staged.)
3. It retries within cap, presents a valid mandate, and the payment completes on Razorpay
   test mode.
4. Cut to the audit record: authorization chain, why attempt one was refused, why attempt
   two was allowed.

An agent that has never seen the merchant buying from it end to end is self-proving. No
judge has to take your word for anything.

## Must-use stack (eventual build)

- Gemini 3.5+ via: Vertex AI (required by ATA; Razorpay is stack-agnostic)
- Agent framework: **Google ADK**
- GCP service visible in demo: **Cloud Run** (agent + published endpoints) + **Firestore**
  (product graph, mandates, append-only audit trail)
- Razorpay: test-mode orders / payment links, and the **Razorpay MCP server** where it
  earns its place rather than as decoration
- Deliberately **not** LLM: mandate verification, cap arithmetic, idempotency, field
  validation, drift detection. This is the answer to "where did you choose not to use one."

## Judging scores (0–10)

- Razorpay problem taste **10** / AI judgment **9** / failure recovery **9** /
  build quality: TBD on execution
- ATA utility 8 / architecture 9 / demo 9
- Cinema: not scored — see risks
- Kill filters hit: **none** for ATA and Razorpay

## Risks to the deadline

- **Cinema does not fit honestly.** The M&E variant is a rights/licensing catalog (stock
  footage, music) made transactable to a buyer agent, which is real, but ClickHouse has no
  load-bearing role and the IBM variant puts an unverified partner surface on the critical
  path with days to spare. Per the kill filters this is a **stretch dual-submit** and the
  honest move is ATA + Razorpay, with Cinema dropped or forked later. Do not force it.
- **Do not claim UAP.** It is unlaunched and pending RBI approval, with no public spec.
  Build to AP2 / Reserve Pay patterns and say plainly "UAP-shaped, not UAP-claiming." The
  panel will know, and the honesty scores.
- **Bigger than a dunning bot.** Ingestion, validation, three publish surfaces, mandate
  gating, buyer agent. Ruthless scoping: **one merchant shape, one product category, one
  protocol shape.** Breadth here kills the deadline.
- **Rate limits.** Razorpay throttles concurrent requests; anything that iterates the API
  needs backoff, idempotency keys and resumability from the start.
- Two agents means two things to keep alive on demo day. Record a clean take early.

## Why not Maya-cloned healthcare

Nothing here survives a swap to "clinic." Mandates, caps, HSN codes, Reserve Pay blocks and
buyer-agent discovery are payments-native. The AARM inheritance is only the shape of the
work — chasing a counterparty for the fields missing from an incomplete packet until it
validates — and here that packet is a product catalog and the counterparty is a merchant.
