"""Fixtures for Home Assistant tests.

pytest-homeassistant-custom-component needs Linux (fcntl). Without it (local
Windows development) these tests are not collected; CI runs them.
"""

from __future__ import annotations

import importlib.util
from typing import Any

import pytest

from custom_components.einspeisewacht.const import (
    CONF_BACKFILL,
    CONF_COMMISSIONED,
    CONF_FEED_IN_TYPE,
    CONF_METER,
    CONF_NAME,
    CONF_OVERRIDE,
    CONF_OVERRIDE_DATE,
    CONF_POWER,
    CONF_PRICE,
    CONF_RATE_MODE,
    CONF_RATES,
    CONF_SMART_METER,
    CONF_SMART_METER_DATE,
    FEED_IN_PARTIAL,
    OVERRIDE_AUTO,
    RATE_SINGLE,
)
from tests.conftest import load_fixture

METER = "sensor.grid_export"
PRICE = "sensor.epex_spot_data_market_price"

METER_ATTRIBUTES = {
    "unit_of_measurement": "Wh",
    "state_class": "total_increasing",
    "device_class": "energy",
}


def price_attributes() -> dict[str, Any]:
    fixture = load_fixture("epex_spot_2026-10-25.json")
    return {
        **fixture["attributes"],
        "data": fixture["history_supplement"] + fixture["attributes"]["data"],
    }


def entry_data(**changes: Any) -> dict[str, Any]:
    """An 8.5 kWp plant from 15.06.2025 with iMSys: rule applies from 2026."""
    return {
        CONF_NAME: "Dach",
        CONF_COMMISSIONED: "2025-06-15",
        CONF_POWER: 8.5,
        CONF_SMART_METER: True,
        CONF_SMART_METER_DATE: "2025-06-15",
        CONF_RATE_MODE: RATE_SINGLE,
        CONF_FEED_IN_TYPE: FEED_IN_PARTIAL,
        CONF_RATES: [7.94],
        CONF_METER: METER,
        CONF_PRICE: PRICE,
        CONF_OVERRIDE: OVERRIDE_AUTO,
        CONF_OVERRIDE_DATE: None,
        CONF_BACKFILL: False,
        **changes,
    }


if importlib.util.find_spec("pytest_homeassistant_custom_component") is None:
    collect_ignore_glob = ["test_*.py"]
else:

    @pytest.fixture(autouse=True)
    def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
        """Allow loading custom_components/einspeisewacht in every test."""
