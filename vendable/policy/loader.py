"""Read a merchant's trading rules off disk.

Deliberately the same shape as `vendable.core.catalog.load_seed`: one function, a `Path`, a
validated model out. The policy lives beside the catalog it prices, so a merchant is one
directory rather than a directory plus a Python literal somewhere in the server.

Everything here fails loudly. There is no default policy, because a merchant whose rules
failed to load and who quietly got someone else's margin floor is the worst outcome this
system has -- worse than not starting, since nobody would find out until the money was gone.
"""

from __future__ import annotations

import json
from pathlib import Path

from vendable.policy.engine import MerchantPolicy


def policy_path(merchant_id: str, root: Path | str) -> Path:
    """Where a merchant's policy lives, given the repository root."""
    return Path(root) / "fixtures" / "merchants" / merchant_id / "policy.json"


def load_policy(path: Path | str) -> MerchantPolicy:
    """Read and validate one merchant policy.

    Raises `FileNotFoundError` if it is missing, and `ValueError` if it does not parse or
    does not validate -- including when it carries a field `MerchantPolicy` does not
    recognise, which is almost always a typo in a field name that would otherwise leave a
    floor or a ceiling silently at its default.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(
            f"No merchant policy at {p}. Every merchant needs a policy.json beside its "
            "catalog.json; there is no default, because guessing a margin floor is worse "
            "than refusing to start."
        )
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{p} is not valid JSON: {exc}") from exc
    return MerchantPolicy.model_validate(data)


__all__ = ["load_policy", "policy_path"]
