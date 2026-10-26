"""Rule derivation (§§ 51, 100 EEG) and blended rate (§ 23c EEG)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from custom_components.einspeisewacht.regime import (
    Derived,
    Plant,
    Regime,
    derive,
    manual,
    rule_for,
    shadow_needed,
)
from custom_components.einspeisewacht.rules import AlwaysPaid, NegativeQuarterHour
from custom_components.einspeisewacht.tariff import bands, blended_rate


@pytest.mark.parametrize(
    ("plant", "expected"),
    [
        # Smart meter in 2025: rule from 1 January 2026 (§ 51 Abs. 2 Satz 1 Nr. 1).
        (
            Plant(date(2025, 6, 15), 8.5, date(2025, 6, 15)),
            Derived(Regime.QUARTER_HOUR, date(2026, 1, 1)),
        ),
        (
            Plant(date(2025, 3, 1), 30, date(2026, 3, 10)),
            Derived(Regime.QUARTER_HOUR, date(2027, 1, 1)),
        ),
        # Smart meter before commissioning: from commissioning.
        (
            Plant(date(2025, 3, 1), 9, date(2024, 6, 1)),
            Derived(Regime.QUARTER_HOUR, date(2025, 3, 1)),
        ),
        (Plant(date(2025, 6, 15), 8.5), Derived(Regime.WAITING_SMART_METER)),
        # "weniger als 100 Kilowatt": exactly 100 kW is affected right away.
        (Plant(date(2025, 3, 1), 100), Derived(Regime.QUARTER_HOUR, date(2025, 3, 1))),
        (Plant(date(2025, 3, 1), 99.9), Derived(Regime.WAITING_SMART_METER)),
        (Plant(date(2025, 2, 25), 1.99), Derived(Regime.BELOW_2_KW)),
        (Plant(date(2025, 2, 25), 2.0), Derived(Regime.WAITING_SMART_METER)),
        # Old regimes.
        (Plant(date(2025, 2, 24), 400), Derived(Regime.BLOCK_2023)),
        (Plant(date(2025, 2, 24), 399.9), Derived(Regime.NOT_AFFECTED)),
        (Plant(date(2023, 1, 1), 400), Derived(Regime.BLOCK_2023)),
        (Plant(date(2022, 12, 31), 500), Derived(Regime.BLOCK_2021)),
        (Plant(date(2021, 1, 1), 499), Derived(Regime.NOT_AFFECTED)),
        (Plant(date(2020, 12, 31), 500), Derived(Regime.BLOCK_2016)),
        (Plant(date(2016, 1, 1), 600), Derived(Regime.BLOCK_2016)),
        (Plant(date(2015, 12, 31), 5000), Derived(Regime.NOT_AFFECTED)),
    ],
)
def test_derive(plant: Plant, expected: Derived) -> None:
    assert derive(plant) == expected


def test_rule_starts_at_local_midnight() -> None:
    rule = rule_for(Derived(Regime.QUARTER_HOUR, date(2026, 1, 1)))
    assert rule == NegativeQuarterHour(
        applies_from=datetime(2025, 12, 31, 23, tzinfo=UTC)
    )
    assert rule.is_paid(datetime(2025, 12, 31, 22, 45, tzinfo=UTC), -1)
    assert not rule.is_paid(datetime(2025, 12, 31, 23, tzinfo=UTC), -1)


@pytest.mark.parametrize(
    "regime",
    [
        Regime.WAITING_SMART_METER,
        Regime.BELOW_2_KW,
        Regime.BLOCK_2023,
        Regime.NOT_AFFECTED,
        Regime.MANUAL_NEVER,
    ],
)
def test_rule_for_unaffected_regimes(regime: Regime) -> None:
    assert rule_for(Derived(regime)) == AlwaysPaid()


def test_manual() -> None:
    assert manual(None) == Derived(Regime.MANUAL_NEVER)
    assert manual(date(2026, 5, 1)) == Derived(
        Regime.MANUAL_FROM_DATE, date(2026, 5, 1)
    )
    assert rule_for(manual(date(2026, 5, 1))) == NegativeQuarterHour(
        applies_from=datetime(2026, 4, 30, 22, tzinfo=UTC)
    )


def test_shadow_needed() -> None:
    today = date(2026, 10, 26)
    assert not shadow_needed(Derived(Regime.QUARTER_HOUR, date(2026, 1, 1)), today)
    assert shadow_needed(Derived(Regime.QUARTER_HOUR, date(2027, 1, 1)), today)
    assert shadow_needed(Derived(Regime.WAITING_SMART_METER), today)
    assert shadow_needed(Derived(Regime.MANUAL_NEVER), today)
    assert not shadow_needed(Derived(Regime.NOT_AFFECTED), today)
    assert not shadow_needed(Derived(Regime.BELOW_2_KW), today)
    assert not shadow_needed(Derived(Regime.BLOCK_2023), today)


def test_bands() -> None:
    assert bands(9, full_feed_in=False) == [(0, 10)]
    assert bands(10, full_feed_in=False) == [(0, 10)]
    assert bands(25, full_feed_in=False) == [(0, 10), (10, 40)]
    assert bands(150, full_feed_in=False) == [(0, 10), (10, 40), (40, 1000)]
    assert bands(150, full_feed_in=True) == [(0, 10), (10, 40), (40, 100), (100, 400)]


def test_blended_rate() -> None:
    assert blended_rate(9, [7.94], full_feed_in=False) == pytest.approx(7.94)
    # 25 kW: 10 kW at the first rate, 15 kW at the second (§ 23c).
    assert blended_rate(25, [8.51, 7.43], full_feed_in=False) == pytest.approx(
        (10 * 8.51 + 15 * 7.43) / 25
    )
    assert blended_rate(1500, [1, 2, 3], full_feed_in=False) == pytest.approx(
        (10 * 1 + 30 * 2 + 1460 * 3) / 1500
    )
    with pytest.raises(ValueError):
        blended_rate(25, [8.51], full_feed_in=False)
