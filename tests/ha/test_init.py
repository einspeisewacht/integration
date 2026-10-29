"""Setup, booking through real state changes, restart and removal."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.einspeisewacht.const import (
    CONF_METER,
    CONF_OVERRIDE,
    CONF_OVERRIDE_DATE,
    CONF_RATES,
    CONF_SMART_METER,
    CONF_SMART_METER_DATE,
    DOMAIN,
    OVERRIDE_FROM_DATE,
    OVERRIDE_NEVER,
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
async def test_reconfigure_removes_stale_sensors(hass: HomeAssistant) -> None:
    """With the smart meter added, the shadow sensors leave the registry."""
    entry = await setup(hass, **{CONF_SMART_METER: False, CONF_SMART_METER_DATE: None})
    assert entity_id(hass, entry, "shadow_energy_unpaid") is not None
    kept = entity_id(hass, entry, "energy_unpaid")

    hass.config_entries.async_update_entry(entry, data=entry_data())
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    for key in (
        "shadow_energy_unpaid",
        "shadow_revenue_lost",
        "shadow_negative_quarter_hours",
    ):
        assert entity_id(hass, entry, key) is None, key
    assert entity_id(hass, entry, "energy_unpaid") == kept
    assert entity_id(hass, entry, "remunerated") is not None


@pytest.mark.freeze_time(START)
async def test_remove_entry(hass: HomeAssistant) -> None:
    entry = await setup(hass)
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.config_entries.async_entries(DOMAIN) == []


async def book_negative_quarter_hour(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """250 Wh at a negative price, then the tick that records the quarter hour."""
    freezer.move_to(datetime(2026, 10, 25, 3, 14, 30, tzinfo=UTC))
    hass.states.async_set(METER, "1250", METER_ATTRIBUTES)
    await hass.async_block_till_done()
    tick = datetime(2026, 10, 25, 3, 15, 1, tzinfo=UTC)
    freezer.move_to(tick)
    async_fire_time_changed(hass, tick)
    await hass.async_block_till_done()


async def reconfigure(hass: HomeAssistant, entry: MockConfigEntry, **changes) -> None:
    hass.config_entries.async_update_entry(entry, data=entry_data(**changes))
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.freeze_time(START)
async def test_reconfigured_rate_applies_since_setup(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup(hass)
    await book_negative_quarter_hour(hass, freezer)
    assert float(value(hass, entry, "revenue_lost")) == pytest.approx(0.25 * 0.0794)

    await reconfigure(hass, entry, **{CONF_RATES: [8.21]})
    assert float(value(hass, entry, "energy_unpaid")) == pytest.approx(0.25)
    assert float(value(hass, entry, "revenue_lost")) == pytest.approx(0.25 * 0.0821)
    assert float(value(hass, entry, "revenue")) == 0


@pytest.mark.freeze_time(START)
async def test_reconfigured_rule_is_reported_not_rebooked(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup(hass)
    await book_negative_quarter_hour(hass, freezer)

    issue_id = f"rule_changed_{entry.entry_id}"
    issues = ir.async_get(hass)

    # A rule that judges the booked quarter hour alike: no issue.
    override = {CONF_OVERRIDE: OVERRIDE_FROM_DATE, CONF_OVERRIDE_DATE: "2026-10-01"}
    await reconfigure(hass, entry, **override)
    assert value(hass, entry, "active_rule") == "manual_from_date"
    assert issues.async_get_issue(DOMAIN, issue_id) is None

    await reconfigure(hass, entry, **{CONF_OVERRIDE: OVERRIDE_NEVER})
    assert value(hass, entry, "active_rule") == "manual_never"
    # No decrease of a TOTAL_INCREASING sensor: the booked split stays.
    assert float(value(hass, entry, "energy_unpaid")) == pytest.approx(0.25)
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["ledger"]["rule_change"]["quarter_hours"] == 1
    issue = issues.async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.translation_placeholders == {
        "name": "Dach",
        "date": "2026-10-25",
        "count": "1",
    }

    # Restart: still there.
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert issues.async_get_issue(DOMAIN, issue_id) is not None

    # Changed back: the totals agree with the rule again.
    await reconfigure(hass, entry)
    assert issues.async_get_issue(DOMAIN, issue_id) is None
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["ledger"]["rule_change"] is None


@pytest.mark.freeze_time(START)
async def test_swapped_meter_books_no_phantom_energy(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup(hass)
    other = "sensor.other_export"
    # Minutes later, a meter 100 Wh above the old one's last reading (1000 Wh):
    # within the plausibility bound, so it would be booked against it.
    freezer.move_to(datetime(2026, 10, 25, 3, 5, tzinfo=UTC))
    hass.states.async_set(other, "1100", METER_ATTRIBUTES)
    hass.config_entries.async_update_entry(entry, unique_id=other)
    await reconfigure(hass, entry, **{CONF_METER: other})
    assert float(value(hass, entry, "energy_unpaid")) == 0
    assert float(value(hass, entry, "energy_paid")) == 0
    # From now on the new meter books.
    freezer.move_to(datetime(2026, 10, 25, 3, 10, tzinfo=UTC))
    hass.states.async_set(other, "1150", METER_ATTRIBUTES)
    await hass.async_block_till_done()
    assert float(value(hass, entry, "energy_unpaid")) == pytest.approx(0.05)
