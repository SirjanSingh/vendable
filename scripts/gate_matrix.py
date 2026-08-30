"""Mandate-gate confusion matrix.

The red-team suite asks "can I break this?". This asks the quieter and more useful question:
**over a systematic sweep of cases where the right answer is known in advance, how often does
the gate get it wrong, and in which direction?**

The two error directions are not equally bad and are reported separately:

- a **false accept** authorises money that should have been refused. Unrecoverable.
- a **false reject** refuses a legitimate purchase. Annoying, recoverable, and the correct
  way to fail.

Cases are generated deterministically, so the numbers reproduce on any machine.

    .venv/Scripts/python.exe scripts/gate_matrix.py

Writes evidence/gate_matrix.md and evidence/gate_matrix.json.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from vendable.core.money import format_inr, rupees
from vendable.mandate.ap2 import AllowedPayees, AmountRange, Budget, generate_keypair, mint
from vendable.mandate.gate import Cart, CartLine, MandateGate, SpendLedger

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"
MERCHANT = "acme-fasteners"


@dataclass
class Case:
    ident: str
    group: str
    description: str
    should_allow: bool
    build: object
    """Callable(priv) -> (token, cart). Built lazily so each case gets a fresh ledger."""


def c(total: str, merchant: str = MERCHANT, currency: str = "INR", lines: int = 1) -> Cart:
    per = rupees(total) // lines
    remainder = rupees(total) - per * lines
    return Cart(
        merchant_id=merchant,
        currency=currency,
        lines=[
            CartLine(sku=f"SKU-{i}", qty=1, unit_price_paise=per + (remainder if i == 0 else 0))
            for i in range(lines)
        ],
    )


def m(priv: str, **kw) -> str:
    return mint(
        priv,
        issuer=kw.pop("issuer", "https://wallet.test/mandates"),
        subject=kw.pop("subject", "buyer-agent-7"),
        audience=kw.pop("audience", MERCHANT),
        constraints=kw.pop("constraints", [AmountRange(currency="INR", max=rupees("5000"))]),
        ttl_seconds=kw.pop("ttl_seconds", 3600),
        **kw,
    )


def build_cases() -> list[Case]:
    cases: list[Case] = []

    def add(ident, group, desc, should_allow, fn):
        cases.append(Case(ident, group, desc, should_allow, fn))

    # --- the cap boundary, swept in single paise around Rs 5,000 -------------------
    cap = rupees("5000")
    for offset in (-1000, -100, -10, -1, 0, 1, 10, 100, 1000):
        allow = offset <= 0
        add(
            f"CAP{offset:+}",
            "cap boundary",
            f"cart is cap{offset:+d} paise ({format_inr(cap + offset)} against a "
            f"{format_inr(cap)} cap)",
            allow,
            lambda priv, off=offset: (
                m(priv),
                Cart(
                    merchant_id=MERCHANT,
                    lines=[CartLine(sku="X", qty=1, unit_price_paise=cap + off)],
                ),
            ),
        )

    # --- amounts across four orders of magnitude ----------------------------------
    for amount in ("0.01", "1", "99.99", "1000", "4999.99", "5000", "5000.01", "50000"):
        allow = rupees(amount) <= cap
        add(
            f"AMT-{amount}",
            "amount range",
            f"cart of {format_inr(rupees(amount))}",
            allow,
            lambda priv, a=amount: (m(priv), c(a)),
        )

    # --- multi-line carts that sum across the cap ---------------------------------
    for lines in (2, 3, 5, 10):
        for total, allow in (("4999", True), ("5000", True), ("5001", False)):
            add(
                f"MULTI-{lines}-{total}",
                "multi-line totals",
                f"{lines} lines summing to {format_inr(rupees(total))}",
                allow,
                lambda priv, ln=lines, t=total: (m(priv), c(t, lines=ln)),
            )

    # --- expiry -------------------------------------------------------------------
    now = int(time.time())
    for label, issued_offset, ttl, allow in (
        ("fresh", 0, 3600, True),
        # 30 seconds of headroom, not 1. At a 1-second margin this case raced the clock:
        # `now` is sampled once at the top, and a run that took longer than a second to
        # reach the check saw the mandate expire under it. That made an evidence file
        # claiming to reproduce on any machine flicker between 62/62 and 61/62 on the same
        # code. The boundary itself is still tested exactly, by `just-expired` below.
        ("30s-left", -3570, 3600, True),
        ("just-expired", -3601, 3600, False),
        ("long-expired", -86400, 3600, False),
        ("issued-and-expired", -7200, 60, False),
    ):
        add(
            f"EXP-{label}",
            "expiry",
            f"mandate {label.replace('-', ' ')}",
            allow,
            lambda priv, o=issued_offset, t=ttl: (m(priv, now=now + o, ttl_seconds=t), c("100")),
        )

    # --- audience -----------------------------------------------------------------
    for aud, allow in (
        (MERCHANT, True),
        ("acme-fastener", False),
        ("ACME-FASTENERS", False),
        ("some-other-shop", False),
        ("", False),
    ):
        add(
            f"AUD-{aud or 'empty'}",
            "audience",
            f"mandate issued for '{aud or '(empty)'}'",
            allow,
            lambda priv, a=aud: (m(priv, audience=a or "none"), c("100")),
        )

    # --- currency -----------------------------------------------------------------
    for mandate_ccy, cart_ccy, allow in (
        ("INR", "INR", True),
        ("USD", "INR", False),
        ("INR", "USD", False),
        ("EUR", "EUR", False),  # the cart is priced in EUR; the merchant sells in INR
    ):
        add(
            f"CCY-{mandate_ccy}-{cart_ccy}",
            "currency",
            f"{mandate_ccy} mandate against a {cart_ccy} cart",
            allow,
            lambda priv, mc=mandate_ccy, cc=cart_ccy: (
                m(priv, constraints=[AmountRange(currency=mc, max=rupees("5000"))]),
                c("100", currency=cc),
            ),
        )

    # --- payee allowlist ----------------------------------------------------------
    for payees, allow in (
        ([MERCHANT], True),
        ([MERCHANT, "another-shop"], True),
        (["another-shop"], False),
        ([], False),
    ):
        add(
            f"PAYEE-{len(payees)}-{'in' if MERCHANT in payees else 'out'}",
            "payee allowlist",
            f"allowed_payees = {payees or '[]'}",
            allow,
            lambda priv, p=payees: (
                m(priv, constraints=[AmountRange(max=rupees("5000")), AllowedPayees(payees=p)]),
                c("100"),
            ),
        )

    # --- minimum bound ------------------------------------------------------------
    for amount, allow in (("99.99", False), ("100", True), ("100.01", True)):
        add(
            f"MIN-{amount}",
            "minimum bound",
            f"cart of {format_inr(rupees(amount))} against a {format_inr(rupees('100'))} minimum",
            allow,
            lambda priv, a=amount: (
                m(priv, constraints=[AmountRange(min=rupees("100"), max=rupees("5000"))]),
                c(a),
            ),
        )

    # --- structurally invalid mandates, all of which must be refused --------------
    add(
        "MAL-nocap",
        "malformed",
        "no amount_range constraint at all",
        False,
        lambda priv: (m(priv, constraints=[AllowedPayees(payees=[MERCHANT])]), c("100")),
    )
    add(
        "MAL-empty",
        "malformed",
        "no constraints at all",
        False,
        lambda priv: (m(priv, constraints=[]), c("100")),
    )
    add(
        "MAL-garbage",
        "malformed",
        "not a token at all",
        False,
        lambda _priv: ("not-a-jwt", c("100")),
    )
    add(
        "MAL-blank", "malformed", "empty string as the mandate", False, lambda _priv: ("", c("100"))
    )
    add(
        "MAL-truncated",
        "malformed",
        "a valid token with its signature chopped off",
        False,
        lambda priv: (".".join(m(priv).split(".")[:2]) + ".", c("100")),
    )
    add(
        "MAL-otherkey",
        "malformed",
        "signed with a key the merchant does not trust",
        False,
        lambda _priv: (m(generate_keypair()[0]), c("100")),
    )
    add(
        "MAL-emptycart",
        "malformed",
        "a valid mandate against an empty cart",
        False,
        lambda priv: (m(priv), Cart(merchant_id=MERCHANT, lines=[])),
    )

    # --- budget -------------------------------------------------------------------
    for spent, amount, budget, allow in (
        ("0", "1000", "1500", True),
        ("1000", "500", "1500", True),
        ("1000", "501", "1500", False),
        ("1500", "1", "1500", False),
        ("1499", "1", "1500", True),
    ):
        add(
            f"BUD-{spent}-{amount}",
            "cumulative budget",
            f"{format_inr(rupees(spent))} already spent, {format_inr(rupees(amount))} "
            f"requested, {format_inr(rupees(budget))} budget",
            allow,
            lambda priv, s=spent, a=amount, b=budget: (
                m(priv, constraints=[AmountRange(max=rupees("2000")), Budget(max_total=rupees(b))]),
                c(a),
                rupees(s),
            ),
        )

    return cases


def main() -> int:
    priv, pub = generate_keypair()
    cases = build_cases()

    results = []
    tp = tn = fp = fn = 0

    for case in cases:
        ledger = SpendLedger(":memory:")
        gate = MandateGate(pub, merchant_id=MERCHANT, ledger=ledger)
        built = case.build(priv)
        token, cart = built[0], built[1]
        if len(built) > 2 and built[2]:
            # Pre-load prior spend for the budget cases.
            claims_jti = gate.evaluate(token, cart).mandate_jti
            ledger.record(claims_jti, "prior-cart", built[2], 0, "prior")

        decision = gate.evaluate(token, cart)
        allowed = decision.allowed
        correct = allowed == case.should_allow

        if allowed and case.should_allow:
            tp += 1
        elif not allowed and not case.should_allow:
            tn += 1
        elif allowed and not case.should_allow:
            fp += 1
        else:
            fn += 1

        results.append(
            {
                "id": case.ident,
                "group": case.group,
                "case": case.description,
                "expected": "allow" if case.should_allow else "refuse",
                "actual": "allow" if allowed else "refuse",
                "correct": correct,
                "refusal_code": decision.first_refusal.code.value if decision.first_refusal else "",
                "explanation": decision.explanation,
            }
        )

    total = len(results)
    accuracy = 100.0 * (tp + tn) / total if total else 0.0

    groups: dict[str, list[dict]] = {}
    for r in results:
        groups.setdefault(r["group"], []).append(r)

    lines = [
        "# Mandate gate — confusion matrix",
        "",
        f"**{total} cases, {tp + tn} correct ({accuracy:.1f}%). "
        f"{fp} false accepts, {fn} false rejects.**",
        "",
        "Generated deterministically, so these numbers reproduce on any machine.",
        "",
        "The two error directions are not equally bad, and conflating them into one accuracy",
        "figure would hide the only thing that matters:",
        "",
        "- a **false accept** authorises money that should have been refused. Unrecoverable.",
        "- a **false reject** refuses a legitimate purchase. Annoying, recoverable, and the",
        "  correct way for this system to fail.",
        "",
        "|  | gate allowed | gate refused |",
        "|---|---|---|",
        f"| **should allow** | {tp} (correct) | {fn} (false reject) |",
        f"| **should refuse** | **{fp} (false accept)** | {tn} (correct) |",
        "",
        "## By group",
        "",
        "| group | cases | correct | false accepts | false rejects |",
        "|---|---|---|---|---|",
    ]
    for group, items in groups.items():
        ok = sum(1 for r in items if r["correct"])
        gfp = sum(1 for r in items if r["actual"] == "allow" and r["expected"] == "refuse")
        gfn = sum(1 for r in items if r["actual"] == "refuse" and r["expected"] == "allow")
        lines.append(f"| {group} | {len(items)} | {ok}/{len(items)} | {gfp} | {gfn} |")

    wrong = [r for r in results if not r["correct"]]
    lines += ["", "## Disagreements", ""]
    if wrong:
        lines += ["| id | case | expected | actual | why |", "|---|---|---|---|---|"]
        for r in wrong:
            lines.append(
                f"| {r['id']} | {r['case']} | {r['expected']} | {r['actual']} | "
                f"{r['explanation'][:160]} |"
            )
    else:
        lines.append(
            "None. Every case landed where the answer key said it should — including the nine"
            " single-paisa steps across the cap boundary, which is the arithmetic this whole"
            " project claims to get right."
        )

    lines += [
        "",
        "## Every case",
        "",
        "| id | group | case | expected | actual | code |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        mark = "" if r["correct"] else " ⚠"
        lines.append(
            f"| {r['id']} | {r['group']} | {r['case']} | {r['expected']} | "
            f"{r['actual']}{mark} | {r['refusal_code']} |"
        )

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "gate_matrix.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (EVIDENCE / "gate_matrix.json").write_text(
        json.dumps(
            {
                "total": total,
                "correct": tp + tn,
                "accuracy_pct": round(accuracy, 2),
                "true_allow": tp,
                "true_refuse": tn,
                "false_accept": fp,
                "false_reject": fn,
                "cases": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"{total} cases, {tp + tn} correct ({accuracy:.1f}%)")
    print(f"  false accepts (money authorised wrongly): {fp}")
    print(f"  false rejects (legitimate purchase blocked): {fn}")
    for group, items in groups.items():
        ok = sum(1 for r in items if r["correct"])
        print(f"    {group:<22} {ok}/{len(items)}")
    for r in wrong:
        print(f"\n  WRONG {r['id']}: {r['case']}\n    expected {r['expected']}, got {r['actual']}")
        print(f"    {r['explanation'][:170]}")
    print(f"\nwrote {EVIDENCE / 'gate_matrix.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
