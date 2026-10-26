"""A price sensor without forecast: its value holds until it changes."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.einspeisewacht.const import DOMAIN

from .conftest import METER, METER_ATTRIBUTES, PRICE, entry_data
from .test_init import START, value


@pytest.mark.freeze_time(START)  # 25.10.2026 04:00:30 CET
async def test_held_value_covers_the_next_quarter_hour(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    hass.states.async_set(PRICE, "-0.05", {"unit_of_measurement": "€/kWh"})
    hass.states.async_set(METER, "1000", METER_ATTRIBUTES)
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=METER, title="Dach", data=entry_data()
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert value(hass, entry, "remunerated") == "off"

    # Next quarter hour: the sensor still shows -0.05 and does not change.
    boundary = datetime(2026, 10, 25, 3, 15, 1, tzinfo=UTC)
    freezer.move_to(boundary)
    async_fire_time_changed(hass, boundary)
    await hass.async_block_till_done()
    assert value(hass, entry, "remunerated") == "off"  # not "unknown"

    # A reading spanning both quarter hours: all of it at the negative price.
    freezer.move_to(datetime(2026, 10, 25, 3, 20, tzinfo=UTC))
    hass.states.async_set(METER, "1200", METER_ATTRIBUTES)
    await hass.async_block_till_done()
    assert float(value(hass, entry, "energy_unpaid")) == pytest.approx(0.2)
    assert float(value(hass, entry, "energy_paid")) == 0
