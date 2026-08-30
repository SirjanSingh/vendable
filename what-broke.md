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

---

## 2026-08-30 · A false accept found by counting, not by attacking

The red-team suite scored 37/37. Then the confusion matrix — 62 generated cases where the
right answer is known in advance — found a real one:

```
CCY-EUR-EUR   EUR mandate against a EUR cart
              expected refuse, got ALLOW
              "Authorised ₹100.00 ... within its ₹5,000.00 cap."
```

The gate compared **the mandate's currency to the cart's currency**. Both of those are
supplied by the buyer. An attacker who controls both can simply make them agree — and then
the amounts are compared as bare integers against a cap that means *paise*, at a merchant
that can only ever be paid in INR.

**Agreement between two attacker-supplied values is not validation.** The cart's currency is
now checked against the merchant's own settlement currency, which is server-side
configuration and not something a buyer can influence.

**Why the red team missed it and the matrix caught it.** Every red-team case was an attack I
thought of, and I had already decided the currency check was fine, so I wrote the test that
confirmed it (`USD mandate vs INR cart` — which passes). The matrix generated the
combination I had not considered because it enumerates a grid rather than a hypothesis. Those
are genuinely different instruments, and this is the argument for building both:

- the red team asks *"can I break the thing I am worried about?"*
- the matrix asks *"over everything, where does the answer disagree with the answer key?"*

Fixed, pinned by `test_a_cart_in_a_currency_the_merchant_cannot_settle_is_refused`, and the
matrix is now 62/62 with zero false accepts.

---

## 2026-08-30 · A 400 that arrived as a 500, because SQLite was locked

Testing the webhook receiver with a deliberately wrong secret:

```
wrong secret : (500, 'Internal Server Error')
```

It should have been a 400 — and the handler had already *computed* the 400 correctly. It
died on the next line, writing the rejection to the audit chain:

```
File "vendable/audit/chain.py", line 164, in append
sqlite3.OperationalError: database is locked
```

Five components keep their own connection to the same SQLite file: catalog, audit chain,
spend ledger, commerce store, webhook de-duplicator. That separation is deliberate — each
owns its schema and none reaches into another's tables — but it makes concurrent writers
normal rather than exceptional, and the default `sqlite3.connect` settings are wrong for
that.

**First fix, which was not enough.** WAL plus a 15-second `busy_timeout`. It made the error
rarer and left it there: an unsubscribed event still 500'd, because `SeenEvents` committed an
insert and the audit chain's write on the very next line still collided.

**Second fix, which actually removes the problem.** One shared connection per database file.
Python's sqlite3 reports `threadsafety == 3` (serialized), so a single connection is safe
across threads and the driver queues statements instead of letting them collide. Writers wait
their turn rather than racing for a file lock.

Worth noticing which fix is which: the first made a race less likely, the second made it
impossible. Given a choice between tuning a retry and removing the contention, remove the
contention.

**The part that nearly hid this.** The bug was in the *error* path, so the happy path was
green throughout and the tests all passed — `parse_delivery` is unit-tested thoroughly and
never touches a database. It only appeared because the manual probe checked what a *rejected*
webhook returns, not just an accepted one. Error paths need exercising with the same care as
success paths, and mine had a database write in it.

---

## A syntax error passed 179 tests

**2026-08-30, while publishing payment terms to `llms.txt`.**

A heredoc ate an escape and wrote a literal newline into a string literal in
`vendable/publish/surfaces.py`. The file could not be imported at all. The full suite ran
green immediately afterwards: **179 passed**.

Nothing imported the module. `llms.txt`, the JSON-LD storefront and the `/.well-known`
manifest — the three surfaces a buyer's agent reads *before* it calls a single tool — had no
test touching them. The discovery layer was the least-tested code in a project whose entire
pitch is "an agent finds this merchant and transacts".

It surfaced by accident, from a manual check of what the new terms section actually rendered.
Had that check been skipped, the first symptom would have been the server failing to start on
camera.

**Fixed:** `tests/test_surfaces.py`, starting with `test_every_surface_builds` — the trivial
smoke test that would have caught it. It also pins the thing that actually matters: the margin
floor and cost price appear on no published surface, while the MSMED statutory limit
deliberately does, because one is a secret and the other is a rule.

**The lesson is about the shape of the gap, not the typo.** A green suite measures the code it
imports. 179 passing tests said nothing whatsoever about a module none of them loaded, and the
number was reassuring enough that I nearly moved on.

---

## An evidence file that claimed determinism flickered between runs

**2026-08-30.**

`evidence/gate_matrix.md` opens with "Generated deterministically, so these numbers reproduce
on any machine." Regenerating it after an unrelated change produced **61/62**, down from
62/62 — a false reject on `EXP-1s-left`, a mandate minted with one second of validity left.

Three consecutive runs on identical code gave 62, 61, 62.

The case sampled `now` once at the top of the script and then built every mandate from it. A
run that took longer than a second to reach the expiry group watched a one-second mandate
expire underneath it. Nothing to do with the change being tested; it had been racing since the
file was written, and had simply won every previous roll.

**Fixed:** 30 seconds of headroom instead of 1. The boundary itself is still tested exactly by
`just-expired` at one second the other side, so no coverage was lost — the flaky case was not
even the one pinning the behaviour.

**Why it mattered more than one test:** an evidence artifact is a claim, and this one asserted
reproducibility in its own first paragraph. A judge who ran it twice would have caught the
project contradicting itself. The number being *nearly* always right is exactly the property
this repo argues against everywhere else.

---

## The engine approved a sale at minus 11.79% margin

**2026-08-30.**

A property sweep across both merchants — every SKU, quantities straddling every ladder
threshold, every payment-terms window — found `PIPE-GI-40` quoting at **-11.79% margin
against a 15% floor**. About ₹230 lost per unit, ₹2,300 on a ten-unit order. `allowed=True`,
`violations=[]`, explanation reading `Approved`.

The SKU has a list price of ₹1,950 against a cost of ₹2,180. That defect was *planted* in the
seed catalog on purpose — `source_ref` says "cost entered per case, price per unit, so it
sells at a loss" — and `validate_product` correctly returns a **blocking** gap for it. The
gap report has been right the whole time. `vendable review` has been printing it.

Nothing connected the report to the sales path.

The engine computed a margin floor above list price and then did this:

```python
# Never quote above list -- if the floor computes higher than list, the SKU is
# mispriced and the gap validator has already flagged it.
best_price = min(best_price, list_price)
```

The comment is the bug. "Has already flagged it" was true and irrelevant: flagging happens in
a report a merchant reads, and the clamp then sold the thing anyway. I wrote that line
believing the validator was a gate. It was a printer.

**Fixed:** a hard `LIST_BELOW_FLOOR` gate that no quantity, term or discount reaches past. The
refusal is addressed to the merchant rather than the buyer, because nothing the buyer does can
fix it — it names the per-unit loss and the price the SKU must be repriced to.

**How it was found matters more than the bug.** Not by a hand-written attack — the red team
has 47 of those and every one passed. By enumerating properties and counting. That is the
second time in this repo that counting beat attacking; the currency false accept was the
first. Both times the attack suite was looking where I already suspected trouble, and the
sweep looked everywhere.

The sweep now runs 5,292 evaluations across seven invariants with zero violations, and the
one guarding the ₹12.00-vs-₹11.25 regression holds in all 5,292 — previously that fix was
guarded only by a comment.

---

## Two experiments that would have published confident nonsense

**2026-08-31.** Both caught before the real recording pass, one by a smoke test and one by
reading the first output carefully.

### An experiment with nothing to measure

The reason-vs-persistence experiment holds a line item fixed and varies only the buyer's
message. The first recording came back with all seven categories at **exactly 1000.0 bp** —
mean, median and max identical. That reads as admirable consistency.

It was nothing of the sort. The fixed line was `BOLT-M8-40`, whose stock is 45 days old. The
ageing ladder's first rung is 90 days, so no ageing authority unlocked and the entire discount
was the published volume break: `discretionary_bp` was **zero**. `NegotiationAgent` floors
every outcome at the published entitlement, so the buyer's message could not change the answer
*by construction*. The experiment measured the clamp, not the model.

Moved to `BOLT-M12-75`, 200 days old, which unlocks the 5% ageing rung — 500bp of
discretionary room that only a negotiation can reach. Then the categories separated, and the
separation is the finding.

What makes this worth writing down: seven identical rows do not look like a bug. They look
like a clean result, and would have gone into the README as one.

### A breach rate from four samples

`run_n1` iterated its four cases exactly once, ignoring `--runs`. A single unlucky reply would
have published as *"25% of raw proposals breach the margin floor"* — a headline number resting
on n=4. Now each case repeats `--runs` times: 20 proposals rather than 4.

Same failure mode as the syntax error that passed 179 tests, and as the gate matrix that
claimed determinism while flickering. The measurement apparatus was wrong in a way the output
did not reveal. Three times now, so it is a pattern rather than bad luck: **check what the
number would look like if the thing being measured were absent.** Seven identical rows, or a
rate from four samples, should both have failed that check immediately.

---

## 2026-08-31 · Every refusal reached the buyer with its reason stripped off

**Expected:** the MSMED refusal — the sentence naming s.15, the 45-day cap, the s.16 interest
and the s.43B(h) deferral — arrives at the buyer's agent, which reads it and asks for Net 45
instead. That message is the entire India-shaped claim in this project. It is quoted in the
README.

**What actually happened:** wiring the two-merchant scene into `demo_buy.py` and watching it
over the wire for the first time, the buyer received:

```
net 60: REFUSED -- Error executing tool request_quote
```

Nothing else. No statute, no cap, no suggested alternative.

**Cause:** the MCP SDK classifies exceptions out of a tool body into two kinds. A `ToolError`
is *anticipated* — the message is handed to the caller to read and act on. **Anything else is
a crash, and the SDK deliberately withholds the text** so an unhandled exception cannot leak
internals to a stranger. Correct behaviour, and every refusal in `vendable/mcp/server.py`
raised `ValueError`. Eight of them. All eight arrived as crashes: the MSMED refusal, the
margin-floor refusal, the unknown-SKU message, and every malformed-argument hint.

**Fix:** `raise ToolError` throughout, with a comment at the import explaining the distinction,
because the next person to add a tool will reach for `ValueError` exactly as I did.

**Why nothing caught it, which is the actual finding.** 216 tests were green. Not one of them
was on the far side of the tool dispatcher — every test called `Storefront` directly, where the
message is still sitting on the exception object, fully intact. The tests asserted that the
*storefront* produces a good refusal, which it always did. The buyer never got it.

So the wire surface — seven tools, every output model, every refusal path, the thing an
external agent actually consumes — had **zero test coverage**, in a project whose central claim
is that a stranger's agent can transact against it. The strongest evidence in the repo was
generated by scripts that call the engine in-process, and they were all still right.

`tests/test_mcp_tools.py` now drives `mcp.call_tool`, which runs the same classification the
HTTP transport runs without needing a socket, and asserts the statute survives the trip. One of
its tests greps the source for `raise ValueError`, because this failure is silent at runtime and
a behavioural test only catches it on the exact path it happens to cover.

**The pattern, for the fourth time.** A syntax error that passed 179 tests. An evidence file
that claimed determinism while flickering. Seven identical rows that read as consistency. Now
216 green tests over a transport that was discarding the payload. Every one of them is the same
shape: *the measurement did not include the part that was broken.* The check that catches all
four is the same one — ask what the output would look like if the thing you care about were
absent, and if the answer is "identical", you are not measuring it.
