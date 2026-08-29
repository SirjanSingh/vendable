"""End to end: a buyer agent shops, is refused, corrects itself, buys, and pays.

Everything here goes over MCP against a running server, using a hand-rolled wire client.
The buyer side shares **no code, no types and no schema** with the merchant side -- it knows
a URL and the tool names it discovered. That separation is the whole point: a refusal only
proves something if the thing being refused is genuinely external.

    # terminal 1
    .venv/Scripts/python.exe -m vendable.mcp.server
    # terminal 2
    .venv/Scripts/python.exe scripts/demo_buy.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp_probe import McpClient, ToolRefused

MERCHANT = "acme-fasteners"


def rule(title: str) -> None:
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


def mint_mandate(cap_rupees: str, *, ttl: int = 3600, audience: str = MERCHANT) -> str:
    """The buyer's wallet signs a mandate.

    In a real deployment this happens in the buyer's wallet, not here, and the merchant only
    ever sees the token. It is done in-process for the demo because there is no wallet to
    run -- but the merchant still verifies it as though it came from a stranger, which is
    the property that matters.
    """
    from vendable.core.money import rupees
    from vendable.core.settings import settings
    from vendable.mandate.ap2 import AllowedPayees, AmountRange, mint

    return mint(
        settings.mandate_private_key(),
        issuer="https://wallet.demo/mandates",
        subject="buyer-agent-7",
        audience=audience,
        constraints=[
            AmountRange(currency="INR", max=rupees(cap_rupees)),
            AllowedPayees(payees=[MERCHANT]),
        ],
        ttl_seconds=ttl,
    )


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080/mcp"
    c = McpClient(url)

    info = c.discover()
    meta = info.get("_meta", {}).get("io.modelcontextprotocol/serverInfo", {})
    rule("1. A stock client connects, knowing only a URL")
    print(f"   {meta.get('title')} v{meta.get('version')}")
    print(f"   tools discovered: {', '.join(t['name'] for t in c.list_tools())}")

    rule("2. The buyer shops")
    found = c.call("search_products", query="hex bolt M8", limit=3)
    for p in found["products"]:
        print(
            f"   {p['sku']:<14} {p['list_price']:>10}/{p['unit']:<8} "
            f"HSN {p['hsn_code']}  GST {p['gst_rate_pct']}%  stock {p['stock_qty']}"
        )

    rule("3. It reads the published policy before asking for a discount")
    pol = c.call("get_policies")
    for vb in pol["volume_breaks"]:
        print(f"   {vb['min_qty']}+ units -> {vb['discount_pct']}%")
    print(f"   ceiling: {pol['max_discount_pct']}%")

    rule("4. It requests a quote for 600 units")
    quote = c.call("request_quote", items=[{"sku": "BOLT-M8-40", "qty": 600}], territory="IN-KA")
    line = quote["lines"][0]
    print(f"   {line['qty']} x {line['sku']}")
    print(f"   list {line['list_price']} -> {line['unit_price']} ({line['discount_pct']}% off)")
    print(f"   total {quote['total']}   cart {quote['cart_hash'][:16]}...")
    print("   the volume break was applied without being asked for")
    quote_id = quote["quote_id"]

    rule("5. Stock is reserved")
    res = c.call("reserve_stock", quote_id=quote_id)
    print(f"   {res['state']}, held until epoch {res['reserved_until_epoch_s']}")

    rule("6. It presents a mandate that is too small. This must be refused.")
    small = mint_mandate("50")
    try:
        out = c.call("create_purchase", quote_id=quote_id, mandate=small)
        print(f"   authorised={out['authorised']}  code={out['refusal_code']}")
        print(f"   {out['explanation']}")
        print(f"   -> {out['next_step']}")
        if out["authorised"]:
            print("\n   FAIL: an over-cap purchase was authorised.")
            return 1
    except ToolRefused as exc:
        print(f"   refused: {exc}")

    rule("7. A mandate for another merchant. Also refused, on a different ground.")
    wrong = mint_mandate("100000", audience="some-other-shop")
    out = c.call("create_purchase", quote_id=quote_id, mandate=wrong)
    print(f"   authorised={out['authorised']}  code={out['refusal_code']}")
    print(f"   {out['explanation']}")

    rule("8. An expired mandate. Refused before any pricing is considered.")
    stale = mint_mandate("100000", ttl=1)
    time.sleep(2)
    out = c.call("create_purchase", quote_id=quote_id, mandate=stale)
    print(f"   authorised={out['authorised']}  code={out['refusal_code']}")
    print(f"   {out['explanation']}")

    rule("9. A correct mandate. This one is authorised.")
    good = mint_mandate("10000")
    out = c.call("create_purchase", quote_id=quote_id, mandate=good)
    print(f"   authorised={out['authorised']}")
    print(f"   amount {out['amount']} against cap {out['mandate_cap']}")
    print(f"   {out['explanation']}")
    if not out["authorised"]:
        print("\n   FAIL: a within-cap purchase was refused.")
        return 1

    pay_url = out.get("payment_url", "")
    if not pay_url:
        print("\n   No payment provider configured; stopping before the money leg.")
        return 0

    rule("10. Replaying the identical purchase. Must not charge twice.")
    again = c.call("create_purchase", quote_id=quote_id, mandate=good)
    print(f"   authorised={again['authorised']}")
    print(f"   {again['explanation']}")

    rule("11. The money leg")
    print(f"   {pay_url}")
    print("   Razorpay exposes no agent-facing way to complete this, so a headless browser")
    print("   crosses the last mile. That gap is the finding, not a workaround.")
    from vendable.razorpay.checkout import HostedCheckoutDriver, Outcome

    result = HostedCheckoutDriver().pay(pay_url, Outcome.SUCCESS)
    print(f"   completed={result.completed}")
    print(f"   {' -> '.join(result.steps)}")
    if result.reason:
        print(f"   reason: {result.reason}")

    from vendable.core.money import format_inr
    from vendable.razorpay.client import RazorpayClient

    rz = RazorpayClient()
    time.sleep(4)
    rule("12. Confirmed against Razorpay, on this specific link")
    link_id = out.get("payment_link_id") or ""
    detail = rz._request("GET", f"/payment_links/{link_id}") if link_id else {}
    print(
        f"   link {link_id}: status={detail.get('status')}, "
        f"amount_paid={format_inr(detail.get('amount_paid', 0))}"
    )
    captured = None
    for entry in detail.get("payments", []):
        pid = entry.get("payment_id")
        payment = rz.fetch_payment(pid)
        captured = payment if payment.is_captured else captured
        print(
            f"   {pid}  {payment.status:<10} {format_inr(payment.amount_paise):>12}  "
            f"{payment.method}"
        )
    if captured is None:
        print("   no captured payment on this link yet")

    rule("Audit trail")
    from vendable.audit.chain import AuditChain
    from vendable.core.settings import settings

    chain = AuditChain(settings.vendable_db_path)
    for rec in chain.for_subject(quote_id):
        print(f"   {rec.seq:>3} {rec.actor:<9} {rec.action.value}")
    breaks = chain.verify()
    print(
        f"\n   chain: {len(chain)} records, verify -> "
        f"{'INTACT' if not breaks else f'{len(breaks)} BREAKS'}"
    )

    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
