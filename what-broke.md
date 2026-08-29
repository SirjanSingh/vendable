# What broke

Written the day it happens, not reconstructed at the end. Failures that cost real time,
what the actual cause turned out to be, and what changed as a result.

---

## 2026-08-30 · There is no headless Razorpay test payment. The plan assumed there was.

**Expected:** create a Payment Link via API, pay it with the `success@razorpay` test VPA from a
script, watch it reach `captured`. Budgeted: 30 minutes.

**What actually happened:** every server-side path is closed on a default test account.
Payment Links have create / fetch / update / cancel / notify and **no pay endpoint**. The UPI
test VPAs are consumed by Checkout's collect field, not by any REST call. S2S JSON v2 is the
one true server-side path and Razorpay's docs say plainly it is "an on-demand feature — please
raise a request with our Support team", which is an unbounded dependency inside a four-day
window.

**Cost:** an hour of research, and a design assumption that had been sitting under the plan
unexamined since it was written.

**Fix:** a headless Playwright driver completes the hosted Payment Link page. The payment stays
real and still fires a real webhook. Recorded as `DECISIONS.md` D-004.

**What I actually take from this:** the plan called this "Spike A — the payment killer" and
scheduled it first precisely because it could invalidate the design. It did, partially, and it
cost an hour on day one instead of a rewrite on day four. The lesson is not about Razorpay —
it is that the assumption most worth testing first is the one nobody thought to write down.

And it turned into the better story. The gap between *an agent decided to buy* and *the money
actually moved* is exactly the gap agentic-payment rails exist to close. Finding it by hand,
with the doc quote to prove it, is worth more in the README than a demo that glossed over it.

---

## 2026-08-30 · The MCP spec moved under me, and the class I planned against no longer exists

**Expected:** `FastMCP` + `stateless_http=True`, the shape every tutorial online still shows.

**What actually happened:** spec **2026-07-28** landed about a month ago and is a rewrite, not
a point release. `initialize` is gone. `Mcp-Session-Id` is gone. `server/discover` is a new
mandatory RPC. In the SDK (`mcp` 2.1.1) **`FastMCP` no longer exists — the class is
`MCPServer`** — and `stateless_http` is now a legacy-only knob that the modern path never
consults.

Confirmed rather than assumed, by introspecting the installed package instead of trusting the
write-up:

```
>>> [n for n in dir(mcp.server) if not n.startswith('_')]
['CacheHint', 'InitializationOptions', 'MCPServer', ... 'transport_security', ...]
```

**Caught before it cost anything**, because the Phase 0 research checkpoint asked "what is the
current revision" rather than "how do I use the thing I already know". Had the stub been
written from memory it would have failed on an import.

**Two traps banked for later:** `streamable_http_app()` defaults to a **localhost-only**
DNS-rebinding allowlist, so behind a real hostname every request returns **421 Misdirected
Request** until `TransportSecuritySettings(allowed_hosts=[...])` is passed. And Claude Desktop's
custom-connector dialog **cannot send a custom header** — which is why the mandate is a tool
argument, not a bearer token (D-005). Both were found before writing code that depended on the
opposite.

---

## 2026-08-30 · A 400 that was the spec working correctly, not a bug

First raw call to the live spike server:

```json
{"code":-32602,"message":"params._meta must be an object carrying the required
 'io.modelcontextprotocol/protocolVersion' and 'io.modelcontextprotocol/clientCapabilities'
 envelope keys"}
```

Reflex read: the server is broken. It was not. Under the stateless 2026-07-28 model every
request carries its own protocol envelope in `params._meta`, because there is no longer an
`initialize` handshake to carry it once. Adding the envelope turned all three calls green.

Kept here because the error message did its job — it named the missing keys exactly. That set
the bar for Vendable's own errors: **a refusal must tell the buyer agent what would have
worked**, not merely that it failed. An agent that cannot recover unaided from an error message
is an agent the error message failed.

---

## 2026-08-30 · Lost the GCP project mid-build

Cassandra's credits expire 31 Aug and billing was detached, so `cassandra-498318` went away
while Phase 0 was in flight. D-002 had chosen it an hour earlier.

**Impact, honestly assessed:** smaller than it first looked. The risk the night-one deploy
existed to retire was *"can a stock client reach my MCP server by URL and call a tool"* — and
that is answerable on localhost, which it now has been. What genuinely defers is TLS, cold
starts, the 421 hostname trap, and multi-instance behaviour.

**Fix:** local-first. SQLite instead of Firestore, `.env` instead of Secret Manager, `deploy/`
still written and parameterised so the cloud move stays a config change. Allowed hosts read
from an env var from the first commit, so the 421 trap is pre-empted rather than merely known.
Now the top entry in the risk register.

---

## 2026-08-30 · Prompt injection was the best deal on the menu

Found by running the negotiation agent against the real model rather than only against
stubs. Three buyer messages, same SKU, same quantity:

| buyer | conceded | price |
|---|---|---|
| honest, gave reasons | 2% | ₹12.25 |
| pushy, demanded 40% | 7% | ₹11.63 |
| **prompt injection** | **10%** | **₹11.25** |

Every price cleared the margin floor, so nothing unsafe happened and every unit test passed.
The bug was economic, not structural: the hostile fallback handed out the **maximum** discount
authority, so the cheapest way to get the best price was to trip the injection detector. The
defence paid a bounty.

The stub tests could not have caught this. They asserted the floor held — and it did. It took
a live run, and reading the three numbers side by side, to notice that the ordering was
backwards.

**Fix, and it improved the design rather than patching it.** Discount authority is now split
into two kinds:

- **entitlement** — the volume break, which `get_policies` *publishes*. Published means owed.
  A quote is issued at this price automatically; making a buyer haggle for a documented break
  would make the published policy a lie.
- **discretionary** — the stock-ageing allowance. Never given unprompted. This is the only
  thing a negotiation can actually win, which is what makes negotiation more than theatre.

A hostile buyer now receives the entitlement and not one basis point more. Re-run live:

| buyer | conceded | price |
|---|---|---|
| honest | 12% | ₹11.00 |
| pushy | 15% | ₹10.63 |
| **prompt injection** | **10%** | **₹11.25** ← now the worst deal |

Pinned by `test_attacking_is_never_better_than_asking_politely`.

**The lesson worth keeping:** a security control that is *safe* can still be *wrong*. "Did the
floor hold" was the question I had written tests for; "does attacking pay better than asking"
was the question that mattered, and it is not a property any single test run can show — it
only appears when you compare outcomes across adversaries.

---

## 2026-08-30 · ...and then negotiating made you worse off than not negotiating

Immediately after fixing the injection bounty, the same incoherence reappeared from the other
side. Over MCP, on the same SKU and quantity:

```
just asking (request_quote) : ₹11.25  (10%)
negotiating politely        : ₹12.00  ( 4%)   <- worse
```

The model works from **list price** and was conceding 4% of its 10% authority. Perfectly
reasonable behaviour for a salesperson, and it made talking to the sales agent a mistake.

**Fix:** the published entitlement is a *floor on the outcome*, not a starting point the model
is allowed to walk back — `min(proposed, entitled)`. The clamp is one-directional: it lifts a
bad outcome and never caps a good one.

Verified live on genuinely aged stock, where there is discretionary allowance to win:

```
just asking   ₹34.20 (10%)
negotiating   ₹33.44 (12%)  "…if you issue a firm PO for the next 600 now, I'll extend to 15%"
negotiating   ₹33.06 (13%)
attacking     ₹34.20 (10%)
```

**Both bugs were the same mistake wearing different clothes:** I had one notion of "the price"
and three code paths deriving it independently. Splitting entitlement from discretionary
authority gave the three paths a shared vocabulary, and the ordering they have to satisfy —
*attacking ≤ asking ≤ negotiating* — became a property I could actually write a test for.

---

## 2026-08-30 · A client that only spoke JSON, against a server that sometimes speaks SSE

`negotiate` was the first tool slow enough for the server to answer with
`Content-Type: text/event-stream` instead of `application/json`. The probe client called
`resp.json()` unconditionally and died on `Expecting value: line 1 column 1`.

Both content types are valid under the spec. A client that handles only the first works
perfectly until it meets a tool that takes long enough to matter — which is to say, it fails
on exactly the tools worth calling. The probe now decodes either.
