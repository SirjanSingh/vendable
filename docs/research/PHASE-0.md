# Phase 0 research checkpoint — 2026-08-30

Narrow re-verification of the load-bearing facts Phase 0 depends on. Strategic research
lives in `D:\projs\hackathon\briefs\`.

---

## A. Razorpay test-mode payment completion paths

**Question:** can a test-mode payment reach `captured` from a server-side script, with no browser?

**Answer: no, not on a default test account.** All four candidate paths were checked:

| Path | Verdict | Detail |
|---|---|---|
| Payment Links API, paid programmatically | ✗ | `POST /v1/payment_links` creates the link, but the API surface is only create / fetch / update / cancel / notify. There is **no endpoint that pays a link**. The customer must open the hosted page. |
| Orders + Server-to-Server (S2S) JSON v2 | ⚠ gated | `POST /v1/payments/create/json` is the only true server-side path. Docs state verbatim it is **"an on-demand feature. Please raise a request with our Support team."** Not enabled on a fresh test account. |
| UPI test VPAs `success@razorpay` / `failure@razorpay` | ✗ headless | These are consumed by **Checkout's** UPI-collect field, not by any bare REST endpoint. |
| A mock / simulate endpoint in test mode | ✗ | None found in the docs. |

**Consequence for the build:** the payment leg needs a browser to cross the last mile. See
`DECISIONS.md` D-004 for the chosen route and the reasoning.

Sources:
- https://razorpay.com/docs/payments/payment-links/apis/
- https://razorpay.com/docs/api/payments/payment-links/create-standard/
- https://razorpay.com/docs/payments/payment-gateway/s2s-integration/json/v2/
- https://razorpay.com/docs/payments/payments/test-upi-details/

---

## B. Webhook signature

- **Literal header: `X-Razorpay-Signature`.** (HTTP headers are case-insensitive in transit;
  match case-insensitively in code.)
- **Construction: HMAC-SHA256, hex digest, over the RAW request body**, keyed with the
  **webhook secret chosen in the Dashboard when the webhook is created** — this is *not* the
  API key secret. Two different secrets; do not conflate them.
- `X-Razorpay-Event-Id` is also sent, unique per event — **use it for webhook de-duplication.**

Sources:
- https://razorpay.com/docs/webhooks/validate-test/
- https://razorpay.com/docs/api/payments/recurring-payments/webhooks/

---

## C. Idempotency

| API | Idempotency | Mechanism |
|---|---|---|
| Orders — create | partial | No header. The **`receipt` field acts as the idempotency key** — a second create reusing the same `receipt` is rejected. Better than expected; earlier notes said "none". |
| Payment Links — create | **none** | Not documented at all. Self-dedupe required. |
| Payouts — create | yes | `X-Payout-Idempotency` |
| Instant Refunds | yes | `X-Refund-Idempotency` (min 10 chars) |
| Direct Transfers (Route) | yes | `X-Transfer-Idempotency` |

Concurrent duplicates while the first is in flight return **409 Conflict**.

**Consequence:** Vendable still self-dedupes on `mandate_jti + cart_hash`, *and* uses that
same digest as the Orders `receipt` so Razorpay enforces it server-side too. Belt and braces.

Sources:
- https://razorpay.com/docs/api/orders/create/
- https://razorpay.com/docs/api/x/payout-idempotency/
- https://razorpay.com/docs/api/refunds/instant-refunds-idempotent/

---

## D. Rate limits

- **HTTP 429**, documented as "429 Throttling Error".
- Error body: code `BAD_REQUEST_ERROR`, description **"Too many requests"** — note it is *not*
  a distinct `RATE_LIMIT_EXCEEDED` code, contrary to earlier assumption.
- **No numeric limit is published.** Docs recommend exponential backoff and webhooks over
  polling. Limit increases are case-by-case via support.

Sources: https://razorpay.com/docs/api/understand/ · https://razorpay.com/docs/errors/common/

---

## E. Test instruments

- **UPI:** `success@razorpay`, `failure@razorpay` (Checkout UPI field).
- **Cards:** Visa `4100 2800 0000 1007`, Mastercard `5500 6700 0000 1002`, RuPay
  `6527 6589 0000 1005`. Any future expiry, random CVV. **OTP of 4–10 digits = success,
  fewer than 4 digits = failure.**
  Note: the commonly cited `4111 1111 1111 1111` is **not** in Razorpay's Indian test list —
  use `4100 2800 0000 1007`.
- Netbanking test credentials: UNVERIFIED, not surfaced.

Sources:
- https://razorpay.com/docs/payments/payments/test-card-details/
- https://razorpay.com/docs/payments/payments/test-upi-details/

---

## F. Razorpay hosted MCP server

- URL **`https://mcp.razorpay.com/mcp`**, Streamable HTTP. The `/sse` endpoint was deprecated
  2025-08-13.
- Auth token is **base64 of `<key_id>:<key_secret>`**, called a "Merchant Token".
- **UNVERIFIED:** the literal header name/format (whether `Authorization: Bearer <token>`).
- **UNVERIFIED:** whether the hosted server accepts `rzp_test_` keys specifically. To be
  settled empirically in Spike C once keys exist.

Sources: https://razorpay.com/docs/mcp-server/ · /remote/ · /faqs/

---

## Open items carried out of this checkpoint

1. Confirm empirically that `rzp_test_` keys authenticate against `mcp.razorpay.com/mcp`,
   and capture the literal auth header. *(needs keys)*
2. Confirm the S2S enablement turnaround with Razorpay support — **not** on the critical
   path, because D-004 routes around it, but worth an email in case it lands in time.

---

## G. MCP Streamable HTTP — spec 2026-07-28 and SDK v2

Checked live 2026-08-30. **Several prior assumptions were wrong; corrected here.**

### Spec 2026-07-28 (current; previous revision was 2025-11-25)

- **`initialize` handshake: REMOVED.** Every request is self-contained and carries its
  protocol version and client capabilities in `_meta`.
- **`Mcp-Session-Id`: REMOVED** from Streamable HTTP (SEP-2567). No sessions, so **no sticky
  routing is needed on Cloud Run for modern clients** — this kills the classic
  MCP-on-Cloud-Run affinity problem outright.
- **`Mcp-Method` / `Mcp-Name`: REQUIRED headers** on every POST (SEP-2243) so gateways route
  without parsing the body. `MCP-Protocol-Version` is also required.
- **`server/discover`: a new MANDATORY server RPC** advertising supported versions,
  capabilities, identity.
- `subscriptions/listen` replaces the GET stream + `resources/subscribe`. `ping`,
  `logging/setLevel`, `roots/list_changed` removed. Server→client requests are replaced by
  the Multi-Round-Trip Request (MRTR) pattern returning `InputRequiredResult`.
- Legacy HTTP+SSE and pre-2026-07-28 Streamable HTTP still work via documented fallback.
- **Warning:** the revision landed ~1 month ago. Any example found outside the official docs
  almost certainly describes the old `initialize` + session model.

### Python SDK — the class was renamed

`mcp` on PyPI is **v2.1.1**. **`FastMCP` is gone; the class is `MCPServer`.**

```python
import os
from mcp.server import MCPServer
from mcp.server.streamable_http import TransportSecuritySettings

mcp = MCPServer("vendable")

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

app = mcp.streamable_http_app()   # Starlette ASGI app, MCP endpoint at /mcp
```
Run with `uvicorn server:app --host 0.0.0.0 --port $PORT`. The SDK does **not** read Cloud
Run's `PORT` itself.

### The 421 trap — the single most likely way Spike B fails

`streamable_http_app()` defaults to a **localhost-only DNS-rebinding allowlist**. Behind a
real Cloud Run hostname every request returns **`421 Misdirected Request`** until:

```python
app = mcp.streamable_http_app(
    transport_security=TransportSecuritySettings(
        allowed_hosts=["<svc>.a.run.app", "<svc>.a.run.app:*"],
        allowed_origins=["https://<svc>.a.run.app"],
    )
)
```
Chicken-and-egg: the hostname is not known until after the first deploy. Deploy once, read
the URL, set it as an env var, redeploy.

### Auth — the finding that changes the design

- `claude mcp add --transport http <name> <url> --header "Authorization: Bearer <tok>"` —
  `--header` / `-H` is supported and repeatable. **Claude Code can send a header.**
- **Claude Desktop CANNOT.** The "Add custom connector" dialog has exactly two inputs: the
  URL, and (under Advanced) OAuth Client ID / Secret. **There is no custom-header field.**
- The SDK's `auth=AuthSettings(...)` path requires `issuer_url` and publishes an RFC 9728
  discovery document — too much machinery for a static token. For a plain bearer check, use
  Starlette middleware or read the header in the handler instead.

**Consequence: the mandate travels as a TOOL ARGUMENT, not an HTTP header.** See D-005.

### Cloud Run

- `stateless_http=True` is a **legacy-only knob** now; on the 2026-07-28 path it is never
  consulted, because there is no session.
- If MRTR confirmation is used, `requestState` is sealed with a per-process random key —
  a retry hitting a different instance fails `-32602`. Needs `RequestStateSecurity(keys=[...])`
  with a shared secret and an identical server `name` across instances. **Avoid MRTR.**
- No resumable SSE (`Last-Event-ID` removed) — a dropped stream is retried as a fresh POST.
- python-sdk#1053 reported Streamable HTTP hanging against Cloud Run, but predates SDK v2 and
  the stateless spec. UNVERIFIED whether it still bites. Smoke-test in Spike B.
- `min-instances=1` to avoid cold-start on the first tool call.

### Tool metadata

- `readOnlyHint` / `destructiveHint` / `idempotentHint` / `openWorldHint` all current; SDK
  takes them as snake_case decorator kwargs. Spec is explicit they are **hints, not security** —
  never rely on a client honouring them. The mandate gate is the real control.
- `outputSchema` / `structuredContent` fully supported; the SDK derives the output schema from
  the return type annotation. Return a Pydantic model and both channels are filled.

Sources:
- https://modelcontextprotocol.io/specification/versioning
- https://modelcontextprotocol.io/specification/2026-07-28/changelog
- https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http
- https://py.sdk.modelcontextprotocol.io/run/asgi/
- https://github.com/modelcontextprotocol/python-sdk (README, docs/run/*, docs/servers/*)
- https://code.claude.com/docs/en/mcp
- https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp
