"""AP2-shaped payment mandates.

A mandate is a signed statement by a human that says, in effect: *this agent may spend up to
this much, with these merchants, until this time.* Vendable's whole safety story rests on it,
so it is worth being precise about what is and is not being claimed.

**What this is.** The constraint vocabulary is modelled on Google's published Agent Payments
Protocol `open_payment_mandate.json` schema -- `payment.amount_range` with integer `min`/`max`
in minor units, `payment.allowed_payees`, `payment.budget` -- carried in a compact JWS signed
with Ed25519, with standard `iss`/`aud`/`sub`/`iat`/`exp`/`jti` registered claims.

**What this is not.** It is not AP2 compliance. Real AP2 uses SD-JWT VC with selective
disclosure and RFC 7800 key binding; this is a plain JWS. It is emphatically **not** NPCI's
UAP, which is unlaunched, pending RBI approval, and has no public specification -- no part of
this system implements or claims it.

The reason to borrow the shape rather than invent one: the constraint semantics have been
argued over by people who do this for a living, and `amount_range` with integer minor units
is a better primitive than the float `max_amount` field that would otherwise have been
written here without thinking.
"""

from __future__ import annotations

import enum
import time
import uuid
from typing import Any, Literal

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import BaseModel, Field

ALGORITHM = "EdDSA"
MANDATE_TYPE = "vendable.open_payment_mandate+jwt"


class ConstraintType(str, enum.Enum):
    AMOUNT_RANGE = "payment.amount_range"
    ALLOWED_PAYEES = "payment.allowed_payees"
    BUDGET = "payment.budget"


class AmountRange(BaseModel):
    """`payment.amount_range` -- the per-transaction cap. The primitive that matters.

    `min` and `max` are integer **minor units** (paise for INR), exactly as AP2 specifies.
    Both bounds are **inclusive**; see DECISIONS.md D-007 for why `amount == max` passes.
    """

    type: Literal[ConstraintType.AMOUNT_RANGE] = ConstraintType.AMOUNT_RANGE
    currency: str = "INR"
    min: int = 0
    max: int


class AllowedPayees(BaseModel):
    """`payment.allowed_payees` -- an allowlist of merchants this mandate may pay."""

    type: Literal[ConstraintType.ALLOWED_PAYEES] = ConstraintType.ALLOWED_PAYEES
    payees: list[str]


class Budget(BaseModel):
    """`payment.budget` -- cumulative ceiling across every transaction under this mandate.

    Distinct from `amount_range.max`, and the distinction is the whole point: a cap of
    ₹5,000 with no budget authorises unlimited ₹5,000 purchases. Enforcing this one requires
    the gate to know what has already been spent, which is why the gate takes a ledger.
    """

    type: Literal[ConstraintType.BUDGET] = ConstraintType.BUDGET
    currency: str = "INR"
    max_total: int


Constraint = AmountRange | AllowedPayees | Budget


class MandateClaims(BaseModel):
    """The decoded, verified contents of a mandate."""

    iss: str
    sub: str
    """The agent this mandate empowers."""
    aud: str
    """The merchant it may be presented to."""
    iat: int
    exp: int
    jti: str
    typ: str = MANDATE_TYPE
    constraints: list[Constraint] = Field(default_factory=list)

    def amount_range(self) -> AmountRange | None:
        return next((c for c in self.constraints if isinstance(c, AmountRange)), None)

    def allowed_payees(self) -> AllowedPayees | None:
        return next((c for c in self.constraints if isinstance(c, AllowedPayees)), None)

    def budget(self) -> Budget | None:
        return next((c for c in self.constraints if isinstance(c, Budget)), None)


# -- keys ---------------------------------------------------------------------------


def generate_keypair() -> tuple[str, str]:
    """A fresh Ed25519 keypair as (private PEM, public PEM).

    Ed25519 rather than RSA because the mandate is a tool argument that travels through
    prompts and logs -- a 64-byte signature keeps the token short enough to read on screen
    during a demo, which matters more than it sounds like it should.
    """
    private = Ed25519PrivateKey.generate()
    priv_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    pub_pem = (
        private.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return priv_pem, pub_pem


def public_pem_from_private(private_pem: str) -> str:
    key = serialization.load_pem_private_key(private_pem.encode(), password=None)
    assert isinstance(key, Ed25519PrivateKey)
    return (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )


# -- minting ------------------------------------------------------------------------


def mint(
    private_pem: str,
    *,
    issuer: str,
    subject: str,
    audience: str,
    constraints: list[Constraint],
    ttl_seconds: int = 3600,
    now: int | None = None,
) -> str:
    """Sign a mandate. Returns a compact JWS.

    Minting lives on the *buyer's* side of the world in reality -- a wallet or an issuer signs
    it, not the merchant. It exists here so the demo can produce one, and because the red-team
    suite needs to forge near-misses (expired, wrong audience, tampered cap) to prove the gate
    catches them.
    """
    issued = now if now is not None else int(time.time())
    payload: dict[str, Any] = {
        "iss": issuer,
        "sub": subject,
        "aud": audience,
        "iat": issued,
        "exp": issued + ttl_seconds,
        "jti": uuid.uuid4().hex,
        "typ": MANDATE_TYPE,
        "constraints": [c.model_dump(mode="json") for c in constraints],
    }
    return jwt.encode(payload, private_pem, algorithm=ALGORITHM)


class MandateError(Exception):
    """The mandate is not trustworthy. Carries a buyer-actionable reason."""


def verify(token: str, public_pem: str, *, audience: str, leeway: int = 0) -> MandateClaims:
    """Verify signature, expiry and audience. Raises `MandateError` with a usable message.

    `algorithms` is pinned to EdDSA explicitly. Accepting whatever the token's own header
    asks for is the classic JWT algorithm-confusion hole -- a forged token claiming
    `"alg": "none"` must not even be parsed, let alone trusted.
    """
    try:
        raw = jwt.decode(
            token,
            public_pem,
            algorithms=[ALGORITHM],
            audience=audience,
            leeway=leeway,
            options={"require": ["exp", "iat", "jti", "iss", "sub", "aud"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise MandateError("This mandate has expired. Ask the buyer to issue a fresh one.") from exc
    except jwt.InvalidAudienceError as exc:
        raise MandateError(
            f"This mandate was not issued for '{audience}'. It cannot be used here."
        ) from exc
    except jwt.MissingRequiredClaimError as exc:
        raise MandateError(f"Mandate is missing a required claim: {exc.claim}.") from exc
    except jwt.InvalidSignatureError as exc:
        raise MandateError(
            "Mandate signature does not verify. It was altered after signing, or signed "
            "with a key this merchant does not trust."
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise MandateError(f"Mandate is not a valid token: {exc}") from exc

    if raw.get("typ") != MANDATE_TYPE:
        raise MandateError(
            f"Expected a {MANDATE_TYPE} mandate, got '{raw.get('typ')}'. "
            "A token for something else cannot authorise a payment."
        )

    try:
        return MandateClaims.model_validate(raw)
    except Exception as exc:  # pydantic validation of the constraint union
        raise MandateError(f"Mandate constraints are malformed: {exc}") from exc


__all__ = [
    "ALGORITHM",
    "MANDATE_TYPE",
    "AllowedPayees",
    "AmountRange",
    "Budget",
    "Constraint",
    "ConstraintType",
    "Ed25519PublicKey",
    "MandateClaims",
    "MandateError",
    "generate_keypair",
    "mint",
    "public_pem_from_private",
    "verify",
]
