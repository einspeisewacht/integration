"""Blended remuneration rate for plants spanning several capacity bands.

§ 23c EEG: payment "anteilig nach der installierten Leistung der Anlage im
Verhältnis zu dem jeweils anzuwendenden Schwellenwert". Band limits from
§ 48 Abs. 2 (partial feed-in) and Abs. 2a (full feed-in surcharge). The rates
themselves depend on the commissioning month (degression, § 49) and the
deduction of § 53; the user takes them from the grid operator's statement.
"""

from __future__ import annotations

# Upper band limits in kW, "bis einschließlich".
PARTIAL_BANDS: tuple[float, ...] = (10, 40, 1000)
FULL_BANDS: tuple[float, ...] = (10, 40, 100, 400, 1000)


def bands(power_kw: float, full_feed_in: bool) -> list[tuple[float, float]]:
    """The (lower, upper) bands a plant of `power_kw` reaches, in order.

    The last band extends to the plant size if it is larger than 1 MW.
    """
    limits = FULL_BANDS if full_feed_in else PARTIAL_BANDS
    result: list[tuple[float, float]] = []
    lower = 0.0
    for upper in limits:
        result.append((lower, upper))
        if power_kw <= upper:
            break
        lower = upper
    return result


def blended_rate(power_kw: float, rates: list[float], full_feed_in: bool) -> float:
    """Capacity-weighted rate; `rates` holds one rate per reached band."""
    reached = bands(power_kw, full_feed_in)
    if len(rates) != len(reached):
        raise ValueError(f"expected {len(reached)} rates, got {len(rates)}")
    if power_kw <= 0:
        raise ValueError("power must be positive")
    *full_bands, (last_lower, _) = reached
    weighted = sum(
        (upper - lower) * rate
        for (lower, upper), rate in zip(full_bands, rates, strict=False)
    )
    weighted += (power_kw - last_lower) * rates[-1]
    return weighted / power_kw
