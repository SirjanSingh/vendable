"""Deterministic invariants of the negotiation floor.

Everything else in `evidence/` measures *safety* -- can the system be robbed. This measures
whether the negotiator is any good at its job, restricted to the half of that question that
needs no model call at all: properties the `PolicyEngine` must hold for every SKU, quantity,
and payment term, regardless of what any LLM ever says.

Invariant #1 exists because of a real bug. From a comment in `vendable/negotiate/agent.py`:

    a second live run produced Rs 12.00 from a polite negotiation against Rs 11.25 from
    request_quote, which would have made talking to the sales agent a mistake

The fix that shipped -- `min(proposed_price, baseline.entitled_unit_price_paise)` -- lives at
the negotiation-agent layer and is guarded only by that prose comment. This script does not
re-test the agent; it sweeps the engine property the fix depends on
(`best_unit_price_paise <= entitled_unit_price_paise`) across hundreds of cases, so the
guarantee the comment describes is measured rather than asserted.

    .venv/Scripts/python.exe scripts/negotiation_invariants.py

Writes evidence/negotiation_invariants.md and evidence/negotiation_invariants.json.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from pathlib import Path

from vendable.core.catalog import load_seed
from vendable.core.models import Product
from vendable.core.money import margin_bp
from vendable.policy.engine import LineRequest, MerchantPolicy, PolicyDecision, PolicyEngine
from vendable.policy.loader import load_policy, policy_path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"
MERCHANTS = ("acme-fasteners", "shakti-forgings")


@dataclass
class Violation:
    invariant: str
    merchant: str
    detail: str


@dataclass
class InvariantResult:
    name: str
    description: str
    cases_checked: int = 0
    violations: list[Violation] = field(default_factory=list)


def quantities_for(product: Product, policy: MerchantPolicy) -> list[int]:
    """Quantities that straddle every threshold this product/policy pair can trip.

    MOQ, stock, and every volume-ladder rung, each probed one below, on, and one above --
    plus a value comfortably inside the ladder's lowest rung so "ordinary" quantities are
    covered too, not just the edges.
    """
    cands: set[int] = set()
    for base in (product.moq, product.stock_qty):
        for delta in (-1, 0, 1):
            v = base + delta
            if v >= 1:
                cands.add(v)
    for rung in policy.volume_ladder:
        for delta in (-1, 0, 1):
            v = rung.threshold + delta
            if v >= 1:
                cands.add(v)
    cands.add(max(1, product.moq))
    return sorted(cands)


def terms_windows_for(policy: MerchantPolicy) -> list[int]:
    """Payment-terms windows that straddle the ladder plus a couple outside it entirely."""
    cands: set[int] = set()
    for rung in policy.payment_terms_ladder:
        cands.add(rung.within_days)
    cands.add(policy.default_payment_terms_days)
    cands.add(policy.max_credit_days)
    cands.add(policy.max_credit_days + 15)  # outside the merchant's own commercial ceiling
    cands.add(1)  # near-immediate, inside every window a ladder could declare
    statutory = policy.statutory_max_credit_days()
    if statutory is not None:
        cands.add(statutory)
        cands.add(statutory + 1)  # just past the MSMED s.15 limit
    return sorted(c for c in cands if c >= 0)


@dataclass
class Case:
    merchant: str
    product: Product
    qty: int
    terms_days: int
    decision: PolicyDecision


def build_cases() -> list[Case]:
    cases: list[Case] = []
    for merchant in MERCHANTS:
        policy = load_policy(policy_path(merchant, ROOT))
        engine = PolicyEngine(policy)
        products = sorted(
            load_seed(ROOT / "fixtures" / "merchants" / merchant / "catalog.json"),
            key=lambda p: p.sku,
        )
        for product in products:
            qtys = quantities_for(product, policy)
            terms = terms_windows_for(policy)
            for qty in qtys:
                for terms_days in terms:
                    req = LineRequest(sku=product.sku, qty=qty, payment_terms_days=terms_days)
                    decision = engine.evaluate(product, req)
                    cases.append(Case(merchant, product, qty, terms_days, decision))
    return cases


# -- the invariants ------------------------------------------------------------------


def check_never_worse_than_asking(cases: list[Case], out: InvariantResult) -> None:
    """1. Negotiating is never worse than just asking: best <= entitled."""
    for case in cases:
        out.cases_checked += 1
        d = case.decision
        if d.best_unit_price_paise > d.entitled_unit_price_paise:
            out.violations.append(
                Violation(
                    out.name,
                    case.merchant,
                    f"{d.sku} qty={case.qty} terms={case.terms_days}: "
                    f"best={d.best_unit_price_paise} > entitled={d.entitled_unit_price_paise}",
                )
            )


def check_pay_sooner_never_costs_more(cases: list[Case], out: InvariantResult) -> None:
    """2. Paying sooner never costs more: for t1 < t2 on the same line, price(t1) <= price(t2)."""
    by_line: dict[tuple[str, str, int], list[Case]] = {}
    for case in cases:
        by_line.setdefault((case.merchant, case.product.sku, case.qty), []).append(case)

    for key, line_cases in sorted(by_line.items()):
        ordered = sorted(line_cases, key=lambda c: c.terms_days)
        for earlier, later in itertools.pairwise(ordered):
            if earlier.terms_days == later.terms_days:
                continue
            out.cases_checked += 1
            p1 = earlier.decision.best_unit_price_paise
            p2 = later.decision.best_unit_price_paise
            if p1 > p2:
                merchant, sku, qty = key
                out.violations.append(
                    Violation(
                        out.name,
                        merchant,
                        f"{sku} qty={qty}: terms={earlier.terms_days}d -> {p1} paise, "
                        f"terms={later.terms_days}d -> {p2} paise (later is cheaper)",
                    )
                )


def check_more_never_costs_more_per_unit(cases: list[Case], out: InvariantResult) -> None:
    """3. Ordering more never costs more per unit: for q1 < q2 on the same SKU, best(q2)<=best(q1)."""
    by_line: dict[tuple[str, str, int], list[Case]] = {}
    for case in cases:
        by_line.setdefault((case.merchant, case.product.sku, case.terms_days), []).append(case)

    for key, line_cases in sorted(by_line.items()):
        ordered = sorted(line_cases, key=lambda c: c.qty)
        for smaller, larger in itertools.pairwise(ordered):
            if smaller.qty == larger.qty:
                continue
            out.cases_checked += 1
            p1 = smaller.decision.best_unit_price_paise
            p2 = larger.decision.best_unit_price_paise
            if p2 > p1:
                merchant, sku, terms_days = key
                out.violations.append(
                    Violation(
                        out.name,
                        merchant,
                        f"{sku} terms={terms_days}d: qty={smaller.qty} -> {p1} paise, "
                        f"qty={larger.qty} -> {p2} paise (more is dearer)",
                    )
                )


def check_clears_margin_floor(
    cases: list[Case], policies: dict[str, MerchantPolicy], out: InvariantResult
) -> None:
    """4. Every allowed price clears the margin floor for its product/category."""
    for case in cases:
        out.cases_checked += 1
        d = case.decision
        if not d.allowed:
            continue
        policy = policies[case.merchant]
        floor_bp = policy.floor_for(case.product)
        actual_bp = margin_bp(d.best_unit_price_paise, case.product.cost_price_paise)
        if actual_bp < floor_bp:
            out.violations.append(
                Violation(
                    out.name,
                    case.merchant,
                    f"{d.sku} qty={case.qty} terms={case.terms_days}: "
                    f"margin={actual_bp}bp < floor={floor_bp}bp at "
                    f"best={d.best_unit_price_paise} (cost={case.product.cost_price_paise})",
                )
            )


def check_never_exceeds_list(cases: list[Case], out: InvariantResult) -> None:
    """5. No price ever exceeds list."""
    for case in cases:
        out.cases_checked += 1
        d = case.decision
        if d.list_unit_price_paise > 0 and d.best_unit_price_paise > d.list_unit_price_paise:
            out.violations.append(
                Violation(
                    out.name,
                    case.merchant,
                    f"{d.sku} qty={case.qty} terms={case.terms_days}: "
                    f"best={d.best_unit_price_paise} > list={d.list_unit_price_paise}",
                )
            )


def check_refusal_explains_itself(cases: list[Case], out: InvariantResult) -> None:
    """6. A refused line always says why."""
    for case in cases:
        out.cases_checked += 1
        d = case.decision
        if d.allowed:
            continue
        if not d.violations or not d.explanation.strip():
            out.violations.append(
                Violation(
                    out.name,
                    case.merchant,
                    f"{d.sku} qty={case.qty} terms={case.terms_days}: refused with "
                    f"violations={len(d.violations)} explanation={d.explanation!r}",
                )
            )


def check_deterministic(
    cases: list[Case], engines: dict[str, PolicyEngine], out: InvariantResult
) -> None:
    """7. Evaluating the identical case twice returns an identical decision."""
    for case in cases:
        out.cases_checked += 1
        engine = engines[case.merchant]
        req = LineRequest(sku=case.product.sku, qty=case.qty, payment_terms_days=case.terms_days)
        again = engine.evaluate(case.product, req)
        if again.model_dump() != case.decision.model_dump():
            out.violations.append(
                Violation(
                    out.name,
                    case.merchant,
                    f"{case.product.sku} qty={case.qty} terms={case.terms_days}: "
                    "two evaluations of the identical case disagreed",
                )
            )


def main() -> int:
    all_cases = build_cases()

    policies: dict[str, MerchantPolicy] = {
        merchant: load_policy(policy_path(merchant, ROOT)) for merchant in MERCHANTS
    }
    engines: dict[str, PolicyEngine] = {
        merchant: PolicyEngine(policy) for merchant, policy in policies.items()
    }

    results: list[InvariantResult] = [
        InvariantResult(
            "never_worse_than_asking",
            "Negotiating is never worse than just asking (best <= entitled).",
        ),
        InvariantResult(
            "pay_sooner_never_costs_more",
            "For payment terms t1 < t2 on the same line, price(t1) <= price(t2).",
        ),
        InvariantResult(
            "more_never_costs_more_per_unit",
            "For quantities q1 < q2 on the same SKU/terms, best(q2) <= best(q1).",
        ),
        InvariantResult(
            "clears_margin_floor",
            "Every allowed price clears the margin floor for its product/policy.",
        ),
        InvariantResult(
            "never_exceeds_list",
            "No price ever exceeds list price.",
        ),
        InvariantResult(
            "refusal_explains_itself",
            "A refused line always has a non-empty violation list and explanation.",
        ),
        InvariantResult(
            "deterministic",
            "Evaluating the identical case twice returns an identical decision.",
        ),
    ]
    by_name = {r.name: r for r in results}

    check_never_worse_than_asking(all_cases, by_name["never_worse_than_asking"])
    check_pay_sooner_never_costs_more(all_cases, by_name["pay_sooner_never_costs_more"])
    check_more_never_costs_more_per_unit(all_cases, by_name["more_never_costs_more_per_unit"])
    check_clears_margin_floor(all_cases, policies, by_name["clears_margin_floor"])
    check_never_exceeds_list(all_cases, by_name["never_exceeds_list"])
    check_refusal_explains_itself(all_cases, by_name["refusal_explains_itself"])
    check_deterministic(all_cases, engines, by_name["deterministic"])

    total_violations = sum(len(r.violations) for r in results)

    # -- render ----------------------------------------------------------------

    lines = [
        "# Negotiation invariants",
        "",
        (
            "This sweeps the deterministic `PolicyEngine` -- no LLM, no network -- across every "
            f"SKU in both fixture merchants ({', '.join(MERCHANTS)}), a set of quantities that "
            "straddle MOQ, stock, and every volume-ladder threshold, and the payment-terms "
            "windows in each merchant's own ladder plus a couple outside it."
        ),
        "",
        (
            "**What this proves:** the arithmetic properties a buyer's agent would reasonably "
            "assume of the pricing engine -- that haggling never beats simply asking, that "
            "paying sooner never costs more, that ordering more never costs more per unit, that "
            "every allowed price clears the merchant's margin floor and never exceeds list, that "
            "a refusal always says why, and that the engine is a pure function of its inputs."
        ),
        "",
        (
            "**What this does not prove:** anything about the LLM that writes the negotiation "
            "sentence. The model can still misread a policy, propose a price the engine then "
            "rejects, waste a turn, or phrase a refusal badly -- none of that is measured here. "
            "This is the floor the model is not allowed to fall through, not a grade on how well "
            "it walks the floor."
        ),
        "",
        (
            f"**{len(all_cases)} line evaluations, {sum(r.cases_checked for r in results)} "
            f"invariant checks, {total_violations} violations.**"
        ),
        "",
        "## Summary",
        "",
        "| invariant | cases checked | violations |",
        "|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r.name} | {r.cases_checked} | {len(r.violations)} |")

    lines += ["", "## Violations", ""]
    if total_violations:
        lines += ["| invariant | merchant | detail |", "|---|---|---|"]
        for r in results:
            for v in r.violations:
                lines.append(f"| {v.invariant} | {v.merchant} | {v.detail} |")
    else:
        lines.append(
            "None. Every one of the checks above held across every SKU, quantity, and "
            "payment-terms window swept."
        )

    lines += ["", "## Invariants checked", ""]
    for r in results:
        lines.append(f"- **{r.name}**: {r.description}")
    lines.append("")

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "negotiation_invariants.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (EVIDENCE / "negotiation_invariants.json").write_text(
        json.dumps(
            {
                "merchants": list(MERCHANTS),
                "line_evaluations": len(all_cases),
                "total_cases_checked": sum(r.cases_checked for r in results),
                "total_violations": total_violations,
                "invariants": [
                    {
                        "name": r.name,
                        "description": r.description,
                        "cases_checked": r.cases_checked,
                        "violation_count": len(r.violations),
                        "violations": [
                            {"merchant": v.merchant, "detail": v.detail} for v in r.violations
                        ],
                    }
                    for r in results
                ],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    print(f"{len(all_cases)} line evaluations, {total_violations} violations")
    for r in results:
        print(f"  {r.name:<32} {r.cases_checked:>6} checked  {len(r.violations):>4} violations")
    for r in results:
        for v in r.violations:
            print(f"\n  VIOLATION [{r.name}] {v.merchant}: {v.detail}")
    print(f"\nwrote {EVIDENCE / 'negotiation_invariants.md'}")
    return 1 if total_violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
