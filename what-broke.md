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
