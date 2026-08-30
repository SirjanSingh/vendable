# Razorpay Buildathon — saturation map and differentiation research

Researched 2026-08-23. Purpose: answer "what will everyone else build, and what is the
defensible idea?" This brief exists because the obvious answer is a trap.

## The finding that changes the pick

**Razorpay's "directions" list on the buildathon page is largely a description of products
they have already shipped.**

Agent Studio launched at FTX 2026 with **eight production agents**, built on Anthropic's
Claude Agent SDK. Map them against the buildathon's suggested directions:

| Buildathon "direction" | Razorpay already ships |
|---|---|
| T2 · chargeback evidence responder | **Dispute Responder** — auto-responds to chargebacks with optimised evidence |
| T2 · return-risk scorer | **RTO Shield** — flags high-risk COD orders pre-shipment |
| T2 · fraud-spike detector | **Vulcan** — foundation model doing fraud detection, 8× more intl card fraud caught |
| T3 · failed-subscription recovery | **Subscription Recovery** — smart retry + personalised outreach |
| T3 · mandate retry sequencer | **Subscription Recovery** (same agent) |
| T3 · checkout drop-off recovery | **Abandoned Cart Conversion** — shipped *twice* (SuperU and Nugget by Zomato) |
| T3 · payment degradation → root cause | **Vulcan** — routing and success-rate optimisation |
| T4 · forward cash forecaster | **Cashflow Forecaster** — 3-7 day cash position, payroll risk alerts |
| T4 · settlement Q&A agent | **Settlement Insights** — daily payout summaries over WhatsApp |
| T4 · multi-source reconciliation | **Agentic Dashboard** — upload a bank statement, instant reconciliation vs settlements, posts entries to ERP |

If you pick a direction off that list, you are building a worse version of a shipped
Razorpay product, in a 5-minute video, for a panel staffed by the engineers who shipped it.
The page even warns you: it lists Slash, Call-E, Agentic Platform, Agentic Payments and
Agent Studio under "we're doing a lot with AI."

## Directions with no shipped Razorpay equivalent

Everything below survived the map above. These are the parts of the published list that are
still genuinely open:

- T1 · **agent-readable catalog** ← strategically hot, see below
- T2 · **abuse-ring sentinel** (collusion / ring detection across merchants)
- T3 · **B2B receivables chaser**
- T3 · **promise-to-pay tracker**
- T4 · **tax-line matcher**

Note that "Hinglish voice recovery" is probably covered by Call-E and should be treated as
occupied until proven otherwise.

## Predicted crowd distribution

Reasoning from how the page is written, not from a survey:

- **Track 3 is the pile-up.** It has seven listed directions — by far the most guidance —
  and "build a revenue recovery agent" is the first thing any LLM outputs when handed this
  page. Expect the largest share of submissions and the highest clone density.
- **Track 2 is second.** Fraud detection is the default student ML project; everyone has a
  Kaggle-shaped version of it already.
- **Track 4 draws the reconciliation crowd**, who will discover mid-build that the
  Agentic Dashboard already does it.
- **Track 1 will be thinnest.** It is the only track that requires understanding a live
  protocol race (UCP, ACP, AP2, x402, and NPCI's unlaunched UAP) before you can write a
  line of code. That barrier is exactly why it is the opportunity.
- **Open Track** attracts contrarians, but the page explicitly says Open is not an easier
  bar, and an Open submission forfeits the "this person understands our business" signal
  that a track submission carries.

General hackathon context for 2026: judges report fatigue with LLM wrappers and chatbots,
and reward multi-system orchestration with real tool use. That is table stakes now, not a
differentiator.

## The strategic gap nobody at this buildathon will notice

Razorpay's agentic commerce work is **live but bespoke**:

- Feb 2026, with NPCI, at the India AI Impact Summit: agentic payments on **Claude** —
  order from Zomato, Swiggy, Zepto without leaving the conversation. Pilot, select users.
- FTX 2026: in-app agentic pilots with **Zomato, PVR INOX, Vodafone Idea, Bluestone,
  Honasa**.
- Built on **UPI Reserve Pay** (NPCI's Single Block Multiple Debits): the user blocks funds
  against a merchant with a cap and expiry, and the agent transacts inside that block
  without re-authenticating. The merchant must surface block, remaining balance, expiry and
  history, and allow revocation.

Every one of those is a named, large, hand-integrated enterprise. Razorpay has millions of
long-tail merchants and **no self-serve path for any of them to become transactable by an
AI buyer.**

Meanwhile the demand side is already moving: Adobe measured AI-sourced traffic to US retail
up **393% YoY** in Q1 2026, converting **42% better** than organic. Google's UCP went live
January 2026 with Shopify, Target, Etsy, Walmart. ACP is live in ChatGPT with Stripe. x402
has real production traction (Stripe on Base, Cloudflare, AWS Bedrock AgentCore). AP2 is the
authorization layer. The protocols stack rather than compete.

And **NPCI's UAP is not launched** — still in industry consultation, still needs RBI
approval. That matters: nobody can copy an existing UAP implementation, and any submission
claiming to *implement* UAP is bluffing.

## The compliance angle Razorpay is personally sore about

When Vulcan launched (Aug 2026), Medianama and others pressed on questions Razorpay had not
answered: whether the 3 trillion training data points include consumer-identifying data
(which decides whether DPDP applies at all), whether a merchant can opt out or have its
learned data removed, and whether a declined borrower can be told why.

Separately, the **DPDP Rules 2025** put core obligations into force on **14 May 2027**, with
penalties to ₹250 crore. For automated decisions the expectation is explainable (what drove
it), auditable (tamper-evident trail of inputs, model version, prompt, context, output) and
reviewable (a path to dispute and trigger human re-examination).

Track 1's pass bar — *"every money action explainable, bounded and gated, show the audit
trail and one failure handled gracefully"* — is that regulatory posture restated. Building
to it is not gold-plating; it is the rubric.

## Build-quality tells the panel will recognise

- **Rate limits.** Razorpay rate-limits hard on concurrent requests, and an agent naively
  iterating hundreds of payments to reconcile *will* hit it. Backoff, batching, idempotency
  keys and resumability are cheap to add and read as production experience.
- **Restraint.** The rubric credits "the right tool in the right place, **and where you
  chose not to use one**." Deterministic money paths with the LLM confined to the
  unstructured boundary is both cheaper and higher-scoring.
- **The failure question.** The form's last field asks what broke and how you got out, and
  the site says it is the one they read first. Keep `what-broke.md` from day one.

## Stack note

Agent Studio is built on **Anthropic's Claude Agent SDK**. Razorpay imposes no stack
requirement on the buildathon. All Things Agentic *does* require Google ADK + Gemini 3.5+ +
a GCP service. A build shared between the two must go Google, which is off Razorpay's house
style. That is an acceptable cost, but do not pretend it is a bonus.

## Sources

Razorpay Agent Studio blog and product page · Razorpay + NPCI agentic payments blog ·
Razorpay Vulcan / foundation-model page · razorpay/ai-playbook · Medianama on Vulcan ·
NPCI UAP coverage (Business Standard, Medianama, Outlook Business) · NPCI Reserve Pay
circular coverage · protocol comparisons (Crossmint, Orium, ATXP) · Adobe agentic-traffic
figures via UCP/agentic-commerce readiness writeups · DPDP Rules 2025 compliance guides.
