"""The MCP surface, tested through the tool dispatcher rather than around it.

Why this file exists. Every other test in this suite calls `Storefront` directly, where a
refusal is a `StorefrontError` carrying a full sentence. The tools re-raise those for the
buyer, and for most of the build they re-raised them as `ValueError` -- which the MCP SDK
classifies as a *crash*, not an anticipated failure, and whose text it deliberately withholds.
So the buyer received `Error executing tool request_quote` and nothing else: no MSMED citation,
no margin-floor reason, no hint about a malformed argument. 216 tests stayed green throughout,
because none of them was on the far side of the dispatcher.

The lesson generalises past this bug: a refusal message is only worth what survives the
transport, so it has to be asserted where the buyer reads it. `mcp.call_tool` is that place --
it runs the same `ToolError`/`UnexpectedToolError` classification the HTTP transport runs,
without needing a socket.
"""

from __future__ import annotations

import json

import pytest
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

from vendable.core.storefront import build_storefront
from vendable.mandate.ap2 import generate_keypair
from vendable.mcp.server import build_server
from vendable.policy.engine import (
    EnterpriseClass,
    LadderRung,
    MerchantPolicy,
    TermsRung,
    UdyamActivity,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _policy(**over) -> MerchantPolicy:
    base = {
        "merchant_id": "test-merchant",
        "margin_floor_bp": 1500,
        "max_total_discount_bp": 2000,
        "volume_ladder": [LadderRung(threshold=500, grants_bp=1000, label="500+ -> 10%")],
        "age_ladder": [],
        "payment_terms_ladder": [
            TermsRung(within_days=10, grants_bp=200, label="2/10"),
            TermsRung(within_days=30, grants_bp=0, label="net 30"),
        ],
        "default_payment_terms_days": 30,
        "max_credit_days": 90,
        "allowed_territories": ["IN-KA"],
    }
    base.update(over)
    return MerchantPolicy(**base)


@pytest.fixture
def server(tmp_path, bolt):
    """A one-merchant server on a throwaway database, with one sellable SKU."""

    def _build(policy: MerchantPolicy):
        _private, public = generate_keypair()
        sf = build_storefront(
            merchant_id=policy.merchant_id,
            db_path=tmp_path / "t.db",
            policy=policy,
            public_pem=public,
        )
        sf.catalog.put_many([bolt], merchant_id=policy.merchant_id)
        return build_server(sf)

    return _build


async def call(mcp, name: str, **arguments):
    """Call a tool the way the transport does, and return its structured content."""
    result = await mcp.call_tool(name, arguments)
    return result.structured_content


# -- refusals must arrive with their reason intact -----------------------------------


async def test_msmed_refusal_carries_the_statute_to_the_buyer(server, bolt):
    """The whole India-shaped claim is worthless if the buyer gets a bare error string."""
    mcp = server(
        _policy(
            merchant_id="shakti-like",
            udyam_registered=True,
            enterprise_class=EnterpriseClass.SMALL,
            udyam_activity=UdyamActivity.MANUFACTURER,
            written_agreement=True,
        )
    )

    with pytest.raises(ToolError) as excinfo:
        await call(
            mcp,
            "request_quote",
            items=[{"sku": bolt.sku, "qty": 600}],
            payment_terms_days=60,
        )

    message = str(excinfo.value)
    # Not UnexpectedToolError: that subclass is how the SDK signals a crash, and its message
    # is the generic one. Catching the parent above would pass either way, so assert the type.
    assert not isinstance(excinfo.value, UnexpectedToolError)
    assert "MSMED" in message
    assert "45 days" in message
    assert "s.16" in message
    assert "Net 45 or shorter" in message


async def test_a_trader_is_not_capped_and_the_quote_succeeds(server, bolt):
    """The exclusions matter as much as the rule -- guard against over-firing."""
    mcp = server(
        _policy(
            udyam_registered=True,
            enterprise_class=EnterpriseClass.SMALL,
            udyam_activity=UdyamActivity.TRADER,
            written_agreement=True,
        )
    )
    out = await call(
        mcp, "request_quote", items=[{"sku": bolt.sku, "qty": 600}], payment_terms_days=60
    )
    assert out["payment_terms_days"] == 60
    assert out["total_paise"] > 0


async def test_malformed_qty_explains_the_shape_it_wanted(server):
    mcp = server(_policy())
    with pytest.raises(ToolError) as excinfo:
        await call(mcp, "request_quote", items=[{"sku": "BOLT-M8", "qty": "six hundred"}])
    assert not isinstance(excinfo.value, UnexpectedToolError)
    assert "whole number" in str(excinfo.value)


async def test_unknown_sku_names_the_sku(server):
    mcp = server(_policy())
    with pytest.raises(ToolError) as excinfo:
        await call(mcp, "get_product", sku="NOT-A-SKU")
    assert not isinstance(excinfo.value, UnexpectedToolError)
    assert "NOT-A-SKU" in str(excinfo.value)


async def test_no_tool_body_raises_a_bare_ValueError():
    """A structural guard, because the failure mode is invisible at runtime.

    A `ValueError` here does not error loudly; it silently strips the sentence off a refusal.
    Re-introducing one would pass every behavioural test that does not happen to cover that
    exact path, so the file itself is checked.
    """
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "vendable" / "mcp" / "server.py"
    text = source.read_text(encoding="utf-8")
    assert "raise ValueError" not in text, (
        "vendable/mcp/server.py raises ValueError from a tool body. The MCP SDK treats that "
        "as a crash and withholds the message from the buyer. Raise ToolError instead."
    )


# -- the published surface a buyer reads before transacting ---------------------------


async def test_get_policies_publishes_the_statutory_cap_before_it_is_hit(server):
    """A cap a buyer only discovers by being refused is a trap, not a policy."""
    mcp = server(
        _policy(
            udyam_registered=True,
            enterprise_class=EnterpriseClass.SMALL,
            udyam_activity=UdyamActivity.MANUFACTURER,
            written_agreement=False,
        )
    )
    out = await call(mcp, "get_policies")
    terms = out["payment_terms"]
    assert terms["statutory_max_credit_days"] == 15  # no written agreement -> s.15's short leg
    assert "MSMED" in terms["statutory_basis"]


async def test_medium_enterprise_publishes_no_statutory_cap(server):
    """s.15 protects micro and small suppliers. A medium one must not be capped."""
    mcp = server(
        _policy(
            udyam_registered=True,
            enterprise_class=EnterpriseClass.MEDIUM,
            udyam_activity=UdyamActivity.MANUFACTURER,
            written_agreement=True,
        )
    )
    out = await call(mcp, "get_policies")
    assert "statutory_max_credit_days" not in out["payment_terms"]


async def test_every_tool_is_discoverable_with_a_description(server):
    """A tool an agent cannot understand from its schema alone is not agent-native."""
    mcp = server(_policy())
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert names == {
        "search_products",
        "get_product",
        "get_policies",
        "request_quote",
        "negotiate",
        "reserve_stock",
        "create_purchase",
    }
    for tool in tools:
        # A floor, not a target. It catches a tool shipped with a bare one-liner or none
        # at all, which is the realistic regression -- an agent picks tools by reading
        # these, and there is no other documentation it gets to see.
        assert tool.description and len(tool.description) > 60, tool.name
        assert tool.input_schema["type"] == "object"


# -- terms are bound to the cart ------------------------------------------------------


async def test_changing_the_terms_changes_the_cart_hash(server, bolt):
    """Otherwise the early-payment discount is free money for anyone who pays late."""
    mcp = server(_policy())
    hashes = set()
    for days in (0, 10, 30):
        out = await call(
            mcp,
            "request_quote",
            items=[{"sku": bolt.sku, "qty": 600}],
            payment_terms_days=days,
        )
        hashes.add(out["cart_hash"])
    assert len(hashes) == 3


async def test_quote_output_is_json_serialisable(server, bolt):
    """Structured content crosses the wire as JSON; a stray Decimal or Paise breaks it."""
    mcp = server(_policy())
    out = await call(mcp, "request_quote", items=[{"sku": bolt.sku, "qty": 600}])
    json.dumps(out)
