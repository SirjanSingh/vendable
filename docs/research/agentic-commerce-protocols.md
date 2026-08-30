# Agentic commerce protocol landscape

Researched 2026-08-29 against primary sources (live GitHub raw files where possible).
Purpose: decide what Vendable actually implements, and what it must never claim.

## The one-line answer

**Implement an AP2-*shaped* mandate. Claim compliance with nothing.**

## AP2 — Agent Payments Protocol (Google)

Real, published, Apache 2.0: `github.com/google-agentic-commerce/AP2`. Announced Sep 2025
with 60+ launch partners (Mastercard, PayPal, Amex, Coinbase, Salesforce). Now **v0.2.0**;
governance moving to the **FIDO Alliance**.

The model changed from the old blog-era "IntentMandate / CartMandate" sketch to
**SD-JWT Verifiable Credentials**. Four mandate types ship as JSON Schemas under
`code/sdk/schemas/ap2/`:

| Schema | `vct` | Purpose |
|---|---|---|
| `checkout_mandate.json` | `mandate.checkout.1` | one-shot cart, merchant-signed JWT |
| `open_checkout_mandate.json` | `mandate.checkout.open.1` | durable, delegated, `constraints[]` |
| `payment_mandate.json` | `mandate.payment.1` | one-shot payment authorization |
| **`open_payment_mandate.json`** | — | **the cap primitive Vendable needs** |

`open_payment_mandate` constraint types, verbatim from the schema:

- `payment.amount_range` → `{currency, max, min}` — **a hard ceiling in minor units.** This
  is the over-cap refusal, already specified by Google.
- `payment.budget` — cumulative cap across recurring use
- `payment.allowed_payees` — merchant scope
- `payment.allowed_payment_instruments`, `payment.allowed_pisps`
- `payment.agent_recurrence` — `ON_DEMAND / DAILY / WEEKLY / ...`
- `payment.execution_date`, `payment.reference`

Plus `iat` / `exp` for expiry and an RFC 7800 `cnf` claim for holder key-binding.

**What is realistic in 7 days.** Full SD-JWT VC compliance (selective disclosure,
key binding) is a multi-week lift. Borrowing the *shape* — a JSON mandate carrying `vct`,
`payee`, `constraints[{type: "payment.amount_range", currency: "INR", max: N}]`, `iat`,
`exp`, signed as an ordinary JWT you mint and verify — is a day or two and is honest.

**No official AP2 MCP server exists.** The FAQ says one is "being worked on." So Vendable's
MCP layer is its own work, not a wrapper around someone else's.

## ACP — Agentic Commerce Protocol (OpenAI + Stripe)

Real, Apache 2.0, current stable spec `2026-04-17`. Checkout OpenAPI + delegated-payment
OpenAPI + JSON Schemas + RFCs. Payment primitive is Stripe's **Shared Payment Token**.

**Use it for product-feed field naming only.** The payment leg is Stripe-bound and does not
map onto Razorpay. Claiming ACP compliance while paying through Razorpay would be wrong.

## UCP — Universal Commerce Protocol (Google + Shopify)

Real. Launched Jan 2026, co-developed with Shopify, Etsy, Wayfair, Target, Walmart.
`ucp.dev`, `github.com/universal-commerce-protocol/ucp`.

**Critical clarification: UCP and AP2 are complementary, not competing.** Per AP2's own FAQ,
UCP orchestrates the full lifecycle (discovery → checkout → identity → post-purchase) for
Google's AI surfaces, and **AP2 plugs into UCP as the payment-authorization extension**. The
AP2 repo already ships `code/sdk/schemas/ucp/` types.

**This does not kill Vendable.** UCP is a specification, and Shopify merchants get compliance
*through Shopify*. A merchant with a PDF price list has no on-ramp. Vendable is the on-ramp —
it *produces* a compliant surface from a mess. Publishing a `/.well-known/`-style discovery
manifest is ~1 hour and makes the project standards-aware instead of a bespoke island.

## x402 (Coinbase)

Real, and **unusable here.** Revives HTTP 402: agent receives payment terms, signs a
stablecoin transfer (USDC on Base/Solana), retries with proof. No INR rail, no UPI, no fiat
path found. Do not use, do not mention except to say why it was ruled out.

## NPCI UAP — Unified Agent Protocol

**Not launched. No public spec. RBI approval not reported as granted.** Business Standard,
July 2026: NPCI is developing it "in consultation with the industry," built on **UPI Circle**
and **UPI Reserve Pay** delegated-payment frameworks. No timeline.

Razorpay's Feb 2026 "Agentic Payments on Claude" launch with Zomato/Swiggy/Zepto uses UPI
Circle / Reserve Pay mandates — that is a **product pilot, not evidence UAP is public.**

**Hard rule: never write or say "UAP-compliant."**

Safe, accurate, citable framing:

> A mandate-gated payment endpoint on Razorpay test mode, with a spending-cap constraint
> modeled on Google's published AP2 `open_payment_mandate` JSON Schema, and aligned in spirit
> with NPCI's delegated-payment direction (UPI Circle / Reserve Pay). It does not implement
> NPCI UAP, which is unlaunched and has no public specification.

## Catalog fields an AI buyer actually needs

**schema.org Product/Offer JSON-LD** — bare minimum for any agent to parse:
`price` (plain number), `priceCurrency` (ISO 4217), `availability` (full URL form, e.g.
`https://schema.org/InStock`). SKU/GTIN/MPN strongly recommended.

**OpenAI Agentic Commerce product feed** — required: `id`, `title` (≤150),
`description` (≤5000), `brand` (≤70), `url`, `image_url`, `price`, `availability`
(`in_stock`/`out_of_stock`/`pre_order`/`backorder`/`unknown`), `is_eligible_search`,
`is_eligible_checkout`, `seller_name`, `target_countries`. Conditionally required:
`availability_date`, `seller_privacy_policy` / `seller_tos` when checkout-eligible,
`gtin` or `mpn` unless `identifier_exists=no`.

### The gap worth claiming

**No agentic-commerce catalog standard has a GST or HSN field.** Not schema.org, not
OpenAI's feed spec, not UCP. India-specific tax data has no first-class slot anywhere.

That is a real, defensible, India-shaped contribution: a clearly namespaced `hsnCode` /
`gstRate` extension, with a written note on why it is required for an Indian merchant to be
legitimately transactable by an agent. It costs almost nothing and it is the kind of detail a
Razorpay panel will recognise immediately as someone who has actually thought about Indian
commerce rather than porting a US demo.

## Reference implementations worth reading

- **`NVIDIA-AI-Blueprints/Retail-Agentic-Commerce`** (69★) — the best architecture reference
  found. Implements both ACP and UCP: FastAPI merchant API, FastAPI PSP service with payment
  delegation and vault tokens, an MCP server for search/cart/checkout, Next.js demo UI.
  Apache 2.0 for the blueprint code. Steal the *shape*, not the payment leg.
- **`google-agentic-commerce/AP2`** — copy `code/sdk/schemas/ap2/open_payment_mandate.json`
  directly. Python Pydantic models under `code/sdk/python/ap2/models/`.
- `Shopify/Shopify-AI-Toolkit` (522★, MIT) — official MCP server stack for a real catalog.
- `nguthrie/ucp-mcp-server` (9★) — small MCP server that shops via UCP.
- `commercetools/commerce-mcp`, `thomastx05/magento-mcp` — catalog tool exposure, no
  mandate gating anywhere.

**Nobody found is doing mandate-gated purchase over MCP for a long-tail merchant.** That is
the empty square.

## Unverified, flagged

- `ap2-protocol.org/specification/` returned 404; field data above came from live raw GitHub
  schema files (high confidence). UCP capability-list narrative came via secondary
  summarization — treat as paraphrase, not verbatim spec.
- x402 fiat/INR support: none found, treated as crypto-only.
- UAP field structure: does not exist publicly. Anything claiming otherwise is invented.
