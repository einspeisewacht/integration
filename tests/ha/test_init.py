"""Setup, booking through real state changes, restart and removal."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.einspeisewacht.const import (
    CONF_SMART_METER,
    CONF_SMART_METER_DATE,
    DOMAIN,
)
from custom_components.einspeisewacht.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import METER, METER_ATTRIBUTES, PRICE, entry_data, price_attributes

# 25.10.2026 04:00 CET: price -0.00001 (04:00-04:15), then 0 (04:15-04:30).
START = datetime(2026, 10, 25, 3, 0, 30, tzinfo=UTC)


def entity_id(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> str | None:
    registry = er.async_get(hass)
    for platform in ("sensor", "binary_sensor", "calendar"):
        if found := registry.async_get_entity_id(
            platform, DOMAIN, f"{entry.entry_id}_{key}"
        ):
            return found
    return None


def value(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> str:
    state = hass.states.get(entity_id(hass, entry, key) or "")
    assert state is not None, key
    return state.state


async def setup(hass: HomeAssistant, **changes) -> MockConfigEntry:
    hass.states.async_set(PRICE, "-0.00001", price_attributes())
    hass.states.async_set(METER, "1000", METER_ATTRIBUTES)
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=METER, title="Dach", data=entry_data(**changes)
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.freeze_time(START)
async def test_booking_and_restart(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    assert value(hass, entry, "active_rule") == "quarter_hour"
    assert value(hass, entry, "remunerated") == "off"
    # Rule applies already: no shadow sensors.
    assert entity_id(hass, entry, "shadow_energy_unpaid") is None

    # 04:00:30-04:14:30 CET: 250 Wh at a negative price.
    freezer.move_to(datetime(2026, 10, 25, 3, 14, 30, tzinfo=UTC))
    hass.states.async_set(METER, "1250", METER_ATTRIBUTES)
    await hass.async_block_till_done()
    assert float(value(hass, entry, "energy_unpaid")) == pytest.approx(0.25)
    assert float(value(hass, entry, "revenue_lost")) == pytest.approx(0.25 * 0.0794)
    assert float(value(hass, entry, "energy_paid")) == 0

    # 04:14:30-04:29:30: 30 s still negative, the rest at price 0 (paid).
    freezer.move_to(datetime(2026, 10, 25, 3, 29, 30, tzinfo=UTC))
    hass.states.async_set(METER, "1550", METER_ATTRIBUTES)
    await hass.async_block_till_done()
    assert float(value(hass, entry, "energy_unpaid")) == pytest.approx(0.26)
    assert float(value(hass, entry, "energy_paid")) == pytest.approx(0.29)
    assert value(hass, entry, "remunerated") == "on"

    # Restart: totals come back from storage.
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert float(value(hass, entry, "energy_unpaid")) == pytest.approx(0.26)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert "name" not in diagnostics["config"]
    assert diagnostics["prices"]["resolution_minutes"] == 15


@pytest.mark.freeze_time(START)
async def test_meter_reset_is_not_booked(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup(hass)
    freezer.move_to(datetime(2026, 10, 25, 3, 5, tzinfo=UTC))
    hass.states.async_set(METER, "0", METER_ATTRIBUTES)
    await hass.async_block_till_done()
    freezer.move_to(datetime(2026, 10, 25, 3, 6, tzinfo=UTC))
    hass.states.async_set(METER, "1010", METER_ATTRIBUTES)
    await hass.async_block_till_done()
    assert float(value(hass, entry, "energy_unpaid")) == 0


@pytest.mark.freeze_time(START)
async def test_shadow_sensors_without_smart_meter(hass: HomeAssistant) -> None:
    entry = await setup(hass, **{CONF_SMART_METER: False, CONF_SMART_METER_DATE: None})
    assert value(hass, entry, "active_rule") == "waiting_smart_meter"
    assert value(hass, entry, "remunerated") == "on"
    assert entity_id(hass, entry, "shadow_energy_unpaid") is not None
    assert entity_id(hass, entry, "shadow_negative_quarter_hours") is not None


@pytest.mark.freeze_time(START)
async def test_remove_entry(hass: HomeAssistant) -> None:
    entry = await setup(hass)
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.config_entries.async_entries(DOMAIN) == []
