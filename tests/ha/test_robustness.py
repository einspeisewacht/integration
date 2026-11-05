"""Repair issues for missing prices or meter units, and the split storage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.einspeisewacht.const import DOMAIN

from .conftest import METER, METER_ATTRIBUTES, PRICE, entry_data, price_attributes
from .test_init import START, entity_id, press_issue_report, setup, value


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
async def test_meter_missing_issue(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A meter entity that is gone (removed, renamed elsewhere) is reported
    after the grace time; a meter that is back clears it."""
    entry = await setup(hass)
    hass.states.async_remove(METER)
    await hass.async_block_till_done()

    first_tick = datetime(2026, 10, 25, 3, 15, 1, tzinfo=UTC)
    freezer.move_to(first_tick)
    async_fire_time_changed(hass, first_tick)
    await hass.async_block_till_done()
    assert issue(hass, "meter_missing", entry) is None  # grace time

    second_tick = datetime(2026, 10, 25, 3, 30, 1, tzinfo=UTC)
    freezer.move_to(second_tick)
    async_fire_time_changed(hass, second_tick)
    await hass.async_block_till_done()
    found = issue(hass, "meter_missing", entry)
    assert found.translation_key == "meter_missing"
    assert found.translation_placeholders["entity"] == METER

    hass.states.async_set(METER, "1100", METER_ATTRIBUTES)
    await hass.async_block_till_done()
    assert issue(hass, "meter_missing", entry) is None


@pytest.mark.freeze_time(START)
async def test_meter_unavailable_is_not_missing(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Unavailable for a while: the next reading books the gap, no issue."""
    entry = await setup(hass)
    hass.states.async_set(METER, "unavailable", METER_ATTRIBUTES)
    for tick in (
        datetime(2026, 10, 25, 3, 15, 1, tzinfo=UTC),
        datetime(2026, 10, 25, 3, 30, 1, tzinfo=UTC),
    ):
        freezer.move_to(tick)
        async_fire_time_changed(hass, tick)
        await hass.async_block_till_done()
    assert issue(hass, "meter_missing", entry) is None


@pytest.mark.freeze_time(START)
async def test_own_sensor_as_source_is_ignored_with_an_issue(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """An entry from before the form refused them reads another plant's
    totals (seen in Wärmewacht, 2026-11): not read, an issue until fixed."""
    first = await setup(hass)
    own_meter = entity_id(hass, first, "energy_paid")
    own_price = entity_id(hass, first, "revenue")
    garage = MockConfigEntry(
        domain=DOMAIN,
        unique_id=own_meter,
        title="Garage",
        data=entry_data(name="Garage", meter_entity=own_meter, price_entity=own_price),
    )
    garage.add_to_hass(hass)
    assert await hass.config_entries.async_setup(garage.entry_id)
    await hass.async_block_till_done()

    found = issue(hass, "own_entity", garage)
    assert found.translation_key == "own_entity"
    assert found.translation_placeholders["entities"] == ", ".join(
        sorted((own_meter, own_price))
    )
    assert issue(hass, "own_entity", first) is None
    # The report names the issue and shows both sources as Einspeisewacht's.
    message = await press_issue_report(hass, garage)
    assert "open: own_entity" in message
    assert (
        "meter: einspeisewacht, kWh, energy, total_increasing, numeric state" in message
    )
    assert "price: einspeisewacht, EUR, monetary, total, state " in message
    for private in (own_meter, own_price, "Garage"):
        assert private not in message, private
    # Neither is read: no meter reading, no price.
    freezer.move_to(START + timedelta(minutes=5))
    hass.states.async_set(own_meter, "12.5", METER_ATTRIBUTES)
    hass.states.async_set(own_price, "0.5", {"unit_of_measurement": "EUR"})
    await hass.async_block_till_done()
    engine = garage.runtime_data.engine
    assert engine.meter.last_time is None
    assert engine.last_parse is None
    assert issue(hass, "price_missing", garage) is None
    # The report would read Einspeisewacht's own statistics.
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "report",
            {"config_entry_id": garage.entry_id, "start": "2026-10-01"},
            blocking=True,
            return_response=True,
        )
    assert err.value.translation_key == "own_meter"

    # Reconfigured with the real sources: the issue is gone.
    hass.states.async_set("sensor.garage_export", "500", METER_ATTRIBUTES)
    hass.config_entries.async_update_entry(
        garage,
        data=entry_data(name="Garage", meter_entity="sensor.garage_export"),
    )
    assert await hass.config_entries.async_reload(garage.entry_id)
    await hass.async_block_till_done()
    assert issue(hass, "own_entity", garage) is None
    assert garage.runtime_data.engine.meter.last_time is not None


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
