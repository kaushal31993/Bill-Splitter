"""Integer-cent money helpers.

Every amount in this application is an ``int`` number of cents. The only place
a decimal appears is at the presentation edge (JSON out, Excel cells, the UI).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Hashable, Mapping, TypeVar

K = TypeVar("K", bound=Hashable)


def to_cents(amount: Decimal | float | int | str) -> int:
    """Convert a dollar amount to integer cents, rounding half up.

    Accepts str/Decimal for exactness; floats are tolerated for convenience but
    are converted via ``str`` so that 19.99 does not become 19.989999999999998.
    """
    if isinstance(amount, int):
        return amount * 100
    try:
        d = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"not a valid money amount: {amount!r}") from exc
    return int((d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def to_dollars(cents: int) -> Decimal:
    """Convert integer cents to a Decimal dollar amount, for display only."""
    return (Decimal(cents) / Decimal(100)).quantize(Decimal("0.01"))


def format_usd(cents: int) -> str:
    d = to_dollars(cents)
    sign = "-" if d < 0 else ""
    return f"{sign}${abs(d):,.2f}"


def allocate(amount_cents: int, weights: Mapping[K, int]) -> dict[K, int]:
    """Split ``amount_cents`` across ``weights`` using the largest-remainder method.

    Guarantees, for any input:

    * ``sum(result.values()) == amount_cents`` exactly — no cent is lost or invented.
    * The same input always produces the same output. Leftover cents go to the
      largest fractional remainders, ties broken by key order, so the result
      does not depend on dict iteration order.

    Falls back to an equal split when every weight is zero, which is what makes
    a tip on an all-zero-priced bill still divide sensibly rather than vanish.
    """
    keys = sorted(weights)
    if not keys:
        return {}

    total_weight = sum(weights[k] for k in keys)
    if total_weight <= 0:
        effective = {k: 1 for k in keys}
        total_weight = len(keys)
    else:
        effective = {k: max(weights[k], 0) for k in keys}
        total_weight = sum(effective.values())
        if total_weight <= 0:  # every weight was negative
            effective = {k: 1 for k in keys}
            total_weight = len(keys)

    if amount_cents == 0:
        return {k: 0 for k in keys}

    sign = -1 if amount_cents < 0 else 1
    magnitude = abs(amount_cents)

    shares: dict[K, int] = {}
    remainders: list[tuple[int, int]] = []  # (remainder, index into keys)
    allocated = 0
    for idx, k in enumerate(keys):
        exact = magnitude * effective[k]
        base = exact // total_weight
        shares[k] = base
        allocated += base
        remainders.append((exact - base * total_weight, idx))

    leftover = magnitude - allocated
    # Largest remainder first; ties resolved by key order for determinism.
    remainders.sort(key=lambda pair: (-pair[0], pair[1]))
    for i in range(leftover):
        shares[keys[remainders[i][1]]] += 1

    return {k: sign * v for k, v in shares.items()}
