"""Turning a config entry's data into rule and rate."""

from __future__ import annotations

from datetime import date

import pytest

from custom_components.einspeisewacht.regime import Regime
from custom_components.einspeisewacht.runtime import (
    derived_from_config,
    rate_from_config,
)

BASE = {
    "commissioned": "2025-06-15",
    "power_kw": 25.0,
    "smart_meter": True,
    "smart_meter_date": "2025-06-15",
    "feed_in_type": "partial",
    "override": "auto",
    "override_date": None,
}


def test_single_rate_is_taken_as_is_above_10_kw() -> None:
    # A single rate must not be blended, whatever the plant size.
    assert rate_from_config({**BASE, "rate_mode": "single", "rates": [7.94]}) == 7.94
    assert (
        rate_from_config(
            {**BASE, "power_kw": 150, "rate_mode": "single", "rates": [7.0]}
        )
        == 7.0
    )


def test_tiered_rate_is_blended() -> None:
    config = {**BASE, "rate_mode": "tiered", "rates": [8.51, 7.43]}
    assert rate_from_config(config) == pytest.approx((10 * 8.51 + 15 * 7.43) / 25)


def test_override_and_derivation() -> None:
    assert derived_from_config(BASE).applies_from == date(2026, 1, 1)
    assert (
        derived_from_config({**BASE, "override": "never"}).regime is Regime.MANUAL_NEVER
    )
    manual = derived_from_config(
        {**BASE, "override": "from_date", "override_date": "2026-05-01"}
    )
    assert manual.applies_from == date(2026, 5, 1)
    # "from_date" without a date falls back to the derived rule.
    assert (
        derived_from_config({**BASE, "override": "from_date"}).regime
        is Regime.QUARTER_HOUR
    )


def test_price_without_forecast_counts_for_the_running_quarter_hour() -> None:
    from datetime import UTC, datetime

    from homeassistant.core import State

    from custom_components.einspeisewacht.runtime import parse_price_state

    changed = datetime(2026, 10, 25, 3, 2, tzinfo=UTC)
    state = State(
        "sensor.price", "-0.05", {}, last_changed=changed, last_updated=changed
    )
    assert parse_price_state(state).prices == {
        datetime(2026, 10, 25, 3, 0, tzinfo=UTC): -0.05
    }
    later = datetime(2026, 10, 25, 3, 15, 1, tzinfo=UTC)
    assert parse_price_state(state, later).prices == {
        datetime(2026, 10, 25, 3, 15, tzinfo=UTC): -0.05
    }
