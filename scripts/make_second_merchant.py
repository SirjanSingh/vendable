"""Generate the second merchant's catalog, derived from the first.

Comparison shopping only means something if the two merchants actually sell the same
physical goods under different SKU codes and different terms. So rather than inventing a
catalog, this derives one: Shakti Forgings *manufactures* the fasteners and anchors that
Acme distributes.

That relationship sets the economics, and they are the interesting part of the demo:

- Shakti is cheaper per unit, because there is no distributor margin in the price
- Shakti's range is narrower -- it makes fasteners and anchors, and does not stock tools,
  plumbing or abrasives, so it cannot fill a mixed basket on its own
- Shakti is a Udyam-registered small manufacturer, so s.15 of the MSMED Act caps its credit
  terms at 45 days, while Acme (a trader, and outside s.43B(h)) will go to 60

A buyer's agent therefore has a real trade-off rather than a ranking: cheaper unit price and
a legal ceiling on terms, against a fuller basket and longer credit.

Run: python scripts/make_second_merchant.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "fixtures" / "merchants" / "acme-fasteners" / "catalog.json"
OUT = ROOT / "fixtures" / "merchants" / "shakti-forgings"

# What a forge actually makes. Tools, plumbing and abrasives are bought in, and this
# merchant does not carry them -- which is the point of having two.
MAKES = {"fasteners", "anchors"}

# Manufacturer economics, applied to the distributor's numbers.
LIST_MULTIPLIER = 0.92
"""Direct from the works: no distributor margin sits in the list price."""
COST_RATIO = 0.62
"""Landed cost as a share of list. Better than a distributor's, because it is made here."""

TERRITORIES = ["IN-RJ", "IN-KA", "IN-MH"]


def main() -> int:
    products = json.loads(SOURCE.read_text(encoding="utf-8"))
    out = []

    for p in products:
        if p["category"] not in MAKES:
            continue

        list_paise = max(1, round(p["list_price_paise"] * LIST_MULTIPLIER))
        cost_paise = max(1, round(list_paise * COST_RATIO))

        out.append(
            {
                **p,
                "sku": "SF-" + p["sku"],
                "list_price_paise": list_paise,
                "cost_price_paise": cost_paise,
                "brand": "Shakti",
                # A works sells its own production in bigger lots than a distributor does.
                "moq": p["moq"] * 2,
                "stock_qty": round(p["stock_qty"] * 0.6),
                "territories": TERRITORIES,
                "source_ref": "shakti-pricelist-2026-q2.pdf",
            }
        )

    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "catalog.json"
    target.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")

    print(f"{len(out)} SKUs -> {target.relative_to(ROOT)}")
    print(f"  categories: {sorted({p['category'] for p in out})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
