# Negotiation invariants

This sweeps the deterministic `PolicyEngine` -- no LLM, no network -- across every SKU in both fixture merchants (acme-fasteners, shakti-forgings), a set of quantities that straddle MOQ, stock, and every volume-ladder threshold, and the payment-terms windows in each merchant's own ladder plus a couple outside it.

**What this proves:** the arithmetic properties a buyer's agent would reasonably assume of the pricing engine -- that haggling never beats simply asking, that paying sooner never costs more, that ordering more never costs more per unit, that every allowed price clears the merchant's margin floor and never exceeds list, that a refusal always says why, and that the engine is a pure function of its inputs.

**What this does not prove:** anything about the LLM that writes the negotiation sentence. The model can still misread a policy, propose a price the engine then rejects, waste a turn, or phrase a refusal badly -- none of that is measured here. This is the floor the model is not allowed to fall through, not a grade on how well it walks the floor.

**5292 line evaluations, 35856 invariant checks, 0 violations.**

## Summary

| invariant | cases checked | violations |
|---|---|---|
| never_worse_than_asking | 5292 | 0 |
| pay_sooner_never_costs_more | 4486 | 0 |
| more_never_costs_more_per_unit | 4910 | 0 |
| clears_margin_floor | 5292 | 0 |
| never_exceeds_list | 5292 | 0 |
| refusal_explains_itself | 5292 | 0 |
| deterministic | 5292 | 0 |

## Violations

None. Every one of the checks above held across every SKU, quantity, and payment-terms window swept.

## Invariants checked

- **never_worse_than_asking**: Negotiating is never worse than just asking (best <= entitled).
- **pay_sooner_never_costs_more**: For payment terms t1 < t2 on the same line, price(t1) <= price(t2).
- **more_never_costs_more_per_unit**: For quantities q1 < q2 on the same SKU/terms, best(q2) <= best(q1).
- **clears_margin_floor**: Every allowed price clears the margin floor for its product/policy.
- **never_exceeds_list**: No price ever exceeds list price.
- **refusal_explains_itself**: A refused line always has a non-empty violation list and explanation.
- **deterministic**: Evaluating the identical case twice returns an identical decision.

