"""Loading a merchant's trading rules from disk.

The policy decides what this merchant will and will not sell for, so the loader's job is to
be boring and loud. A pricing policy that silently falls back to a default, or that quietly
ignores a mistyped field, is worse than one that refuses to start: the merchant would never
find out, and the first symptom would be a margin they did not agree to.
"""

from __future__ import annotations

import json

import pytest

from vendable.policy.engine import EnterpriseClass, MerchantPolicy, UdyamActivity
from vendable.policy.loader import load_policy, policy_path

MINIMAL = {
    "merchant_id": "test-merchant",
    "margin_floor_bp": 1800,
    "max_total_discount_bp": 2500,
    "volume_ladder": [{"threshold": 100, "grants_bp": 500, "label": "100+ -> 5%"}],
    "payment_terms_ladder": [{"within_days": 10, "grants_bp": 200, "label": "2/10"}],
    "default_payment_terms_days": 30,
    "max_credit_days": 45,
    "udyam_registered": True,
    "enterprise_class": "small",
    "udyam_activity": "manufacturer",
    "written_agreement": True,
}


def write(tmp_path, data) -> str:
    p = tmp_path / "policy.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


def test_round_trip(tmp_path):
    policy = load_policy(write(tmp_path, MINIMAL))
    assert isinstance(policy, MerchantPolicy)
    assert policy.merchant_id == "test-merchant"
    assert policy.margin_floor_bp == 1800
    assert policy.volume_ladder[0].grants_bp == 500
    assert policy.payment_terms_ladder[0].within_days == 10


def test_enums_come_back_as_enums_not_strings(tmp_path):
    """`statutory_max_credit_days` compares identity on these, so a bare string would make
    the MSMED guard silently never fire."""
    policy = load_policy(write(tmp_path, MINIMAL))
    assert policy.enterprise_class is EnterpriseClass.SMALL
    assert policy.udyam_activity is UdyamActivity.MANUFACTURER
    assert policy.statutory_max_credit_days() == 45


def test_a_mistyped_field_is_refused_not_ignored(tmp_path):
    """`margin_floor_bps` is not `margin_floor_bp`. Ignoring it would leave the floor at its
    default and nobody would know until the money was gone."""
    bad = dict(MINIMAL, margin_floor_bps=9999)
    with pytest.raises(ValueError):
        load_policy(write(tmp_path, bad))


def test_a_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_policy(tmp_path / "nope.json")


def test_malformed_json_raises(tmp_path):
    p = tmp_path / "policy.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        load_policy(p)


def test_policy_path_points_beside_the_catalog(tmp_path):
    assert policy_path("acme-fasteners", tmp_path).parts[-3:] == (
        "merchants",
        "acme-fasteners",
        "policy.json",
    )


# --- the policies actually shipped -------------------------------------------------


@pytest.mark.parametrize("merchant", ["acme-fasteners", "shakti-forgings"])
def test_shipped_policies_load(merchant):
    """The fixtures the demo runs on must parse. This is the test that catches a comma."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    policy = load_policy(policy_path(merchant, root))
    assert policy.merchant_id == merchant
    assert policy.margin_floor_bp > 0


def test_the_two_merchants_differ_on_msmed_exposure():
    """The whole point of having two. One is bound by s.15; the other is not."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    acme = load_policy(policy_path("acme-fasteners", root))
    shakti = load_policy(policy_path("shakti-forgings", root))

    assert acme.statutory_max_credit_days() is None
    assert shakti.statutory_max_credit_days() == 45
