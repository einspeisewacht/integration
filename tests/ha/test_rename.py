"""Renamed meter or price sensor: the entry follows without reconfiguring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.einspeisewacht.const import (
    CONF_METER,
    CONF_METER_PREVIOUS,
    CONF_PRICE,
    DOMAIN,
)

from .conftest import METER, METER_ATTRIBUTES, PRICE
from .test_init import START, value
from .test_init import setup as setup_entry


async def wait(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float
) -> None:
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def setup(hass: HomeAssistant) -> MockConfigEntry:
    registry = er.async_get(hass)
    for entity_id in (METER, PRICE):
        domain, object_id = entity_id.split(".")
        registry.async_get_or_create(
            domain, "test", object_id, suggested_object_id=object_id
        )
    return await setup_entry(hass)


def rename(hass: HomeAssistant, old: str, new: str) -> None:
    """As Home Assistant does it: the entity comes back under the new id."""
    state = hass.states.get(old)
    er.async_get(hass).async_update_entity(old, new_entity_id=new)
    hass.states.async_remove(old)
    if state is not None:
        hass.states.async_set(new, state.state, state.attributes)


@pytest.mark.freeze_time(START)
async def test_meter_renamed(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Energy fed in between the rename and the reload is booked: the stored
    reading of the old id stays the baseline (no swapped meter)."""
    entry = await setup(hass)
    freezer.move_to(datetime(2026, 10, 25, 3, 5, tzinfo=UTC))
    hass.states.async_set(METER, "1100", METER_ATTRIBUTES)
    await hass.async_block_till_done()
    assert float(value(hass, entry, "energy_unpaid")) == pytest.approx(0.1)
    before = entry.runtime_data

    rename(hass, METER, "sensor.meter_export")
    await hass.async_block_till_done()
    # The data follows at once, the reload waits for the end of the burst.
    assert entry.data[CONF_METER] == "sensor.meter_export"
    assert entry.data[CONF_METER_PREVIOUS] == [METER]
    assert entry.unique_id == "sensor.meter_export"
    assert entry.runtime_data is before
    freezer.move_to(datetime(2026, 10, 25, 3, 7, tzinfo=UTC))
    hass.states.async_set("sensor.meter_export", "1200", METER_ATTRIBUTES)

    await wait(hass, freezer, 5)
    assert entry.state is ConfigEntryState.LOADED
    runtime = entry.runtime_data
    assert runtime is not before
    assert runtime.meter_entity == "sensor.meter_export"
    assert float(value(hass, entry, "energy_unpaid")) == pytest.approx(0.2)
    assert runtime.engine.meter_events["first"] == 1

    # Readings of the new id are booked; no repair issue.
    freezer.move_to(datetime(2026, 10, 25, 3, 10, tzinfo=UTC))
    hass.states.async_set("sensor.meter_export", "1300", METER_ATTRIBUTES)
    await hass.async_block_till_done()
    assert float(value(hass, entry, "energy_unpaid")) == pytest.approx(0.3)


@pytest.mark.freeze_time(START)
async def test_renamed_twice_before_the_reload(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A -> B -> C within the burst; another entry already has C as unique id."""
    entry = await setup(hass)
    MockConfigEntry(domain=DOMAIN, unique_id="sensor.c", data={}).add_to_hass(hass)
    rename(hass, METER, "sensor.b")
    await wait(hass, freezer, 1)
    rename(hass, "sensor.b", "sensor.c")
    await wait(hass, freezer, 5)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.data[CONF_METER] == "sensor.c"
    assert entry.data[CONF_METER_PREVIOUS] == [METER, "sensor.b"]
    assert entry.unique_id == "sensor.b"
    assert entry.runtime_data.meter_entity == "sensor.c"
    assert entry.runtime_data.engine.meter.last_value == pytest.approx(1.0)


@pytest.mark.freeze_time(START)
async def test_price_renamed(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup(hass)
    rename(hass, PRICE, "sensor.day_ahead_price")
    await wait(hass, freezer, 5)
    assert entry.data[CONF_PRICE] == "sensor.day_ahead_price"
    assert CONF_METER_PREVIOUS not in entry.data
    assert entry.unique_id == METER
    assert entry.runtime_data.price_entity == "sensor.day_ahead_price"


@pytest.mark.freeze_time(START)
async def test_rename_onto_the_other_source(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """The new id is already a source of the entry: nothing changes."""
    entry = await setup(hass)
    before = entry.runtime_data
    er.async_get(hass).async_remove(PRICE)
    hass.states.async_remove(PRICE)

    rename(hass, METER, PRICE)
    await wait(hass, freezer, 5)
    assert entry.data[CONF_METER] == METER
    assert entry.data[CONF_PRICE] == PRICE
    assert entry.unique_id == METER
    assert entry.runtime_data is before


@pytest.mark.freeze_time(START)
async def test_other_changes_ignored(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A new name or a removed entity is not a rename."""
    entry = await setup(hass)
    before = entry.runtime_data
    er.async_get(hass).async_update_entity(METER, name="Einspeisung")
    er.async_get(hass).async_remove(PRICE)
    await wait(hass, freezer, 5)
    assert entry.data[CONF_METER] == METER
    assert entry.data[CONF_PRICE] == PRICE
    assert entry.runtime_data is before
