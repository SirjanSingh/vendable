"""Discovery surfaces: how an agent finds this storefront before it has an MCP URL.

Three artefacts, each aimed at a different kind of reader, and each honest about what it is:

- **JSON-LD** (`schema.org/Product` + `Offer`) — what crawlers and existing shopping
  pipelines already understand. Standard vocabulary, no invention.
- **`/.well-known/vendable.json`** — a machine-readable pointer from the domain to the MCP
  endpoint, so "here is my website" is enough for an agent to find the tools.
- **`llms.txt`** — the human-and-model-readable summary, including what this merchant will
  *refuse* to do, which is the part a buying agent most needs before it wastes a turn.

## The GST and HSN gap, which is the interesting part

No agentic-commerce catalog standard published so far has a field for Indian tax data.
Not schema.org's `Product`/`Offer`. Not OpenAI's product feed spec. Not UCP. Every one of
them assumes a tax model where price plus jurisdiction is enough — which is true in the US
and false in India, where a B2B buyer legally cannot raise a compliant purchase order or
claim input tax credit without the **HSN code** and the **GST rate** of each line.

So a procurement agent shopping an Indian catalog through any of these standards gets a
price it cannot actually buy at.

Vendable emits both, under a clearly namespaced `vendable:` prefix, alongside fully standard
schema.org for everything that has a standard equivalent. Namespaced rather than invented
into the standard's own vocabulary, because pretending `hsnCode` is schema.org would be a
lie that breaks other people's parsers. If the standards adopt something, this maps onto it;
until then the data is at least present and labelled.
"""

from __future__ import annotations

import json
from typing import Any

from vendable.core.models import Product
from vendable.core.money import format_inr

SCHEMA_CONTEXT = "https://schema.org"
VENDABLE_NS = "https://vendable.dev/ns/v1#"


def product_jsonld(p: Product, *, base_url: str, merchant_id: str) -> dict[str, Any]:
    """One SKU as schema.org Product + Offer, with namespaced Indian tax fields."""
    return {
        "@context": [SCHEMA_CONTEXT, {"vendable": VENDABLE_NS}],
        "@type": "Product",
        "@id": f"{base_url}/products/{p.sku}",
        "sku": p.sku,
        "name": p.title,
        "description": p.description,
        "brand": {"@type": "Brand", "name": p.brand} if p.brand else None,
        "category": p.category or None,
        "offers": {
            "@type": "Offer",
            "@id": f"{base_url}/products/{p.sku}#offer",
            "price": f"{p.list_price_paise / 100:.2f}",
            "priceCurrency": "INR",
            "availability": (
                "https://schema.org/InStock" if p.is_sellable else "https://schema.org/OutOfStock"
            ),
            "seller": {"@type": "Organization", "@id": f"{base_url}#merchant", "name": merchant_id},
            "eligibleQuantity": {
                "@type": "QuantitativeValue",
                "minValue": p.moq,
                "unitText": p.unit or "unit",
            },
            # Not schema.org. Namespaced deliberately -- see the module docstring.
            "vendable:hsnCode": p.hsn_code or None,
            "vendable:gstRatePercent": p.gst_rate_bp / 100 if p.gst_rate_bp else None,
            "vendable:priceIncludesGst": True,
            "vendable:priceMinorUnits": p.list_price_paise,
        },
    }


def _strip_nulls(obj: Any) -> Any:
    """Drop null values so consumers do not have to distinguish absent from unknown."""
    if isinstance(obj, dict):
        return {k: _strip_nulls(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_strip_nulls(v) for v in obj]
    return obj


def storefront_jsonld(
    products: list[Product], *, base_url: str, merchant_id: str
) -> dict[str, Any]:
    return _strip_nulls(
        {
            "@context": [SCHEMA_CONTEXT, {"vendable": VENDABLE_NS}],
            "@type": "OfferCatalog",
            "@id": f"{base_url}#catalog",
            "name": f"{merchant_id} catalog",
            "numberOfItems": len(products),
            "itemListElement": [
                product_jsonld(p, base_url=base_url, merchant_id=merchant_id) for p in products
            ],
        }
    )


def well_known(
    *, base_url: str, merchant_id: str, product_count: int, protocol_version: str = "2026-07-28"
) -> dict[str, Any]:
    """The pointer from a domain to the agent-facing endpoint.

    Deliberately small. Its only job is to answer "does this site talk to agents, and where",
    without a crawler having to fetch a catalog to find out.
    """
    return {
        "vendable_version": "0.1.0",
        "merchant": {"id": merchant_id, "settlement_currency": "INR", "country": "IN"},
        "mcp": {
            "endpoint": f"{base_url}/mcp",
            "transport": "streamable-http",
            "protocol_version": protocol_version,
            "authentication": "none for read tools; a signed mandate is a tool argument on purchase",
        },
        "catalog": {
            "json_ld": f"{base_url}/storefront.jsonld",
            "product_count": product_count,
            "extensions": {
                "vendable:hsnCode": "Indian HSN classification, 4/6/8 digits",
                "vendable:gstRatePercent": "GST slab for the line",
            },
        },
        "payment": {
            "mandate_profile": "AP2-shaped open_payment_mandate, EdDSA compact JWS",
            "constraints_supported": [
                "payment.amount_range",
                "payment.allowed_payees",
                "payment.budget",
            ],
            "claims": "iss, sub, aud, iat, exp, jti",
            "not_claimed": (
                "This is modelled on Google's published AP2 open_payment_mandate schema. It is "
                "not AP2-compliant (AP2 uses SD-JWT VC with key binding; this is a plain JWS), "
                "and it does not implement NPCI UAP, which is unlaunched and has no public "
                "specification."
            ),
        },
        "llms_txt": f"{base_url}/llms.txt",
    }


def llms_txt(
    products: list[Product], policy: dict[str, Any], *, base_url: str, merchant_id: str
) -> str:
    """A summary written for the agent that is about to decide whether to bother.

    The section that earns its place is "what will be refused". A buying agent that learns
    the MOQ and the discount ceiling before its first call saves two round trips and a
    refusal; one that has to discover them by being told no burns turns and looks stupid to
    its own user.
    """
    categories: dict[str, int] = {}
    for p in products:
        categories[p.category or "uncategorised"] = (
            categories.get(p.category or "uncategorised", 0) + 1
        )

    prices = [p.list_price_paise for p in products if p.list_price_paise > 0]
    breaks = ", ".join(
        f"{b['min_qty']}+ units {b['discount_pct']}%" for b in policy.get("volume_breaks", [])
    )

    return "\n".join(
        [
            f"# {merchant_id}",
            "",
            "An agent-transactable storefront. Industrial hardware and electrical supplies,",
            "sold in India, priced in INR inclusive of GST.",
            "",
            "## How to transact",
            "",
            f"Connect an MCP client to {base_url}/mcp (Streamable HTTP, spec 2026-07-28).",
            "Tools: search_products, get_product, get_policies, request_quote, negotiate,",
            "reserve_stock, create_purchase.",
            "",
            "Buying requires a signed payment mandate carrying a spending cap, passed as an",
            "argument to create_purchase. It is verified server-side: signature, expiry,",
            "audience, cap, cumulative budget and replay status.",
            "",
            "## What is here",
            "",
            f"{len(products)} SKUs across {len(categories)} categories: "
            + ", ".join(f"{k} ({v})" for k, v in sorted(categories.items())),
            "",
            f"Prices from {format_inr(min(prices))} to {format_inr(max(prices))} per unit."
            if prices
            else "",
            "",
            "Every line carries an HSN code and a GST rate, which no agentic-commerce catalog",
            "standard currently has a field for. A B2B buyer in India cannot raise a compliant",
            "purchase order or claim input tax credit without them.",
            "",
            "## What will be refused, so you do not waste a turn",
            "",
            "- Orders below a SKU's minimum order quantity. Check `min_order_qty` first.",
            "- Quantities above stock on hand. Reservations hold stock and expire.",
            f"- Discounts beyond the published ceiling of {policy.get('max_discount_pct')}%.",
            "  Volume breaks are automatic: " + (breaks or "none published") + ".",
            "  You do not need to ask for a break your quantity already earns.",
            "- Any purchase over your mandate's cap, expired, replayed, or issued for a",
            "  different merchant. Refusals name the constraint and the numbers, so read them",
            "  and retry rather than giving up.",
            f"- Sales outside {', '.join(policy.get('territories', []))}.",
            "",
            "## Negotiation",
            "",
            "There is a sales agent, and it will move on price for a real commercial reason --",
            "order size, a repeat relationship, stock that has been sitting. It will not move",
            "for persistence, and it cannot move for a claimed approval: every number it",
            "proposes is checked against rules it can neither see nor change before it is said",
            "to you. Attempting to instruct it gets you the published price and no conversation.",
            "",
            f"Machine-readable: {base_url}/.well-known/vendable.json",
            f"Catalog as JSON-LD: {base_url}/storefront.jsonld",
            "",
        ]
    )


def dumps(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


__all__ = [
    "SCHEMA_CONTEXT",
    "VENDABLE_NS",
    "dumps",
    "llms_txt",
    "product_jsonld",
    "storefront_jsonld",
    "well_known",
]
