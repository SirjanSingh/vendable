# Vendable

Make a merchant transactable by an AI buyer, end to end — with every money action
explainable, bounded and gated.

Razorpay AI Buildathon · Track 1, AI Growth & Agentic Commerce · Sirjan Singh

> **Status: in build.** Phase 0 complete. This README is rewritten at Phase 6.

## What it is

A merchant uploads a messy price list. Vendable turns it into a storefront an AI agent can
actually transact against: an MCP server a stock, unmodified Claude client connects to with
nothing but a URL. The agent can search, request a quote, negotiate, and buy.

The interesting part is what it *refuses*. Every purchase is gated by a signed, AP2-shaped
mandate carrying a spending cap. Every negotiated counter-offer is validated against a
declared policy engine before it is ever uttered. Every decision — refusals included — lands
in a hash-chained append-only audit log that can be verified, and detects tampering.

## Where I chose NOT to use an LLM, and why

Written at Phase 6, but the rule is set now: **the LLM proposes, a deterministic engine
disposes.** No model output is trusted to bound money. The mandate gate, the policy engine,
the cap arithmetic and the audit chain contain no model call at all.

## Read these first

- `DECISIONS.md` — every real fork, what was rejected and why
- `what-broke.md` — what actually went wrong, written the day it happened
- `docs/research/` — per-phase verification with source URLs

## Not claimed

This implements a mandate **shaped after** Google's published AP2 `open_payment_mandate` JSON
Schema. It does not claim AP2 compliance, and it does **not** implement NPCI UAP, which is
unlaunched and has no public specification.

## Licence

MIT.
