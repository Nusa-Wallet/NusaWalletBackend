"""FX rate lookup. Uses the free Frankfurter API (no key) with a static
fallback so demos work offline. This is the *spot* rate used for settlement;
the timing recommendation ("convert now?") lives in the separate AI service."""

from decimal import Decimal

import httpx

# Fallback rates expressed as 1 unit of currency -> IDR. Used when offline.
_FALLBACK_TO_IDR: dict[str, Decimal] = {
    "IDR": Decimal("1"),
    "USD": Decimal("16250"),
    "SGD": Decimal("12050"),
    "EUR": Decimal("17600"),
    "MYR": Decimal("3450"),
}


def _fallback_rate(base: str, quote: str) -> Decimal:
    return _FALLBACK_TO_IDR[base] / _FALLBACK_TO_IDR[quote]


def get_rate(base: str, quote: str) -> Decimal:
    base, quote = base.upper(), quote.upper()
    if base == quote:
        return Decimal("1")
    try:
        resp = httpx.get(
            "https://api.frankfurter.app/latest",
            params={"from": base, "to": quote},
            timeout=5.0,
        )
        resp.raise_for_status()
        rate = resp.json()["rates"][quote]
        return Decimal(str(rate))
    except Exception:
        return _fallback_rate(base, quote)
