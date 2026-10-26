"""Repair issues for missing prices or meter units, and the split storage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.einspeisewacht.const import DOMAIN

from .conftest import METER, METER_ATTRIBUTES, PRICE, entry_data, price_attributes
from .test_init import START, setup, value


def issue(
    hass: HomeAssistant, key: str, entry: MockConfigEntry
) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(DOMAIN, f"{key}_{entry.entry_id}")


@pytest.mark.freeze_time(START)
async def test_price_missing_issue(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup(hass)
    assert issue(hass, "price_missing", entry) is None

    # Two days later the forecast has run out; a meter reading notices it.
    later = datetime(2026, 10, 28, 10, tzinfo=UTC)
    freezer.move_to(later)
    hass.states.async_set(METER, "1100", METER_ATTRIBUTES)
    await hass.async_block_till_done()
    assert issue(hass, "price_missing", entry) is None  # not yet an hour

    freezer.move_to(later + timedelta(minutes=61))
    hass.states.async_set(METER, "1200", METER_ATTRIBUTES)
    await hass.async_block_till_done()
    assert issue(hass, "price_missing", entry).translation_key == "price_missing"

    # A price arrives (a sensor without forecast: its state is the price).
    hass.states.async_set(PRICE, "0.08", {"unit_of_measurement": "€/kWh"})
    await hass.async_block_till_done()
    assert issue(hass, "price_missing", entry) is None


@pytest.mark.freeze_time(START)
async def test_meter_unit_issue(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup(hass)
    freezer.move_to(START + timedelta(minutes=5))
    hass.states.async_set(METER, "5", {**METER_ATTRIBUTES, "unit_of_measurement": "W"})
    await hass.async_block_till_done()
    assert issue(hass, "meter_unit", entry).translation_key == "meter_unit"

    freezer.move_to(START + timedelta(minutes=6))
    hass.states.async_set(METER, "1010", METER_ATTRIBUTES)
    await hass.async_block_till_done()
    assert issue(hass, "meter_unit", entry) is None


@pytest.mark.freeze_time(START)
async def test_storage_split_and_single_file_of_0_1_0b4(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    negative = datetime(2026, 1, 15, 11, tzinfo=UTC).isoformat()
    hass_storage[f"{DOMAIN}.legacy"] = {
        "version": 1,
        "minor_version": 1,
        "key": f"{DOMAIN}.legacy",
        "data": {
            "meter": {"last_value": None, "last_time": None},
            "ledger": {
                "totals": {"energy_paid": 5.0},
                "pending": [],
                "booked_without_price": 0,
            },
            "prices": {},
            "quarters": {
                "next_slot": START.replace(second=0).isoformat(),
                "started": START.replace(second=0).isoformat(),
                "backfill_from": None,
                "backfilled": False,
                "negatives": {negative: -0.01},
                "missing": [],
            },
            "meter_events": {},
        },
    }
    hass.states.async_set(PRICE, "-0.00001", price_attributes())
    hass.states.async_set(METER, "1000", METER_ATTRIBUTES)
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="legacy",
        unique_id=METER,
        title="Dach",
        data=entry_data(),
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert float(value(hass, entry, "energy_paid")) == 5.0
    assert value(hass, entry, "negative_quarter_hours") == "1"

    assert await hass.config_entries.async_unload(entry.entry_id)
    live = hass_storage[f"{DOMAIN}.legacy"]["data"]
    history = hass_storage[f"{DOMAIN}.legacy.history"]["data"]
    assert "prices" not in live and "negatives" not in live["quarters"]
    assert negative in history["negatives"]
    assert history["prices"]
