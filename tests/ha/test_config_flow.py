"""Tests for the config flow and reconfiguration."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.einspeisewacht.const import (
    CONF_OVERRIDE,
    CONF_OVERRIDE_DATE,
    CONF_RATES,
    DOMAIN,
    OVERRIDE_AUTO,
    OVERRIDE_FROM_DATE,
)

from .conftest import METER, METER_ATTRIBUTES, PRICE, entry_data, price_attributes

PLANT = {
    "name": "Dach",
    "commissioned": "2025-06-15",
    "power_kw": 8.5,
    "smart_meter": True,
    "smart_meter_date": "2025-06-15",
}


@pytest.fixture(autouse=True)
def no_setup() -> Iterator[AsyncMock]:
    """Flows are tested without actually setting up the entry."""
    with patch(
        "custom_components.einspeisewacht.async_setup_entry", return_value=True
    ) as mock:
        yield mock


@pytest.fixture(autouse=True)
def sources(hass: HomeAssistant) -> None:
    hass.states.async_set(METER, "1234567.0", METER_ATTRIBUTES)
    hass.states.async_set(PRICE, "0.10574", price_attributes())


async def start(hass: HomeAssistant) -> dict:
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )


async def configure(hass: HomeAssistant, result: dict, user_input: dict) -> dict:
    return await hass.config_entries.flow.async_configure(result["flow_id"], user_input)


async def test_full_flow_single_rate(hass: HomeAssistant) -> None:
    result = await start(hass)
    assert result["step_id"] == "user"
    result = await configure(hass, result, PLANT)
    assert result["step_id"] == "rate"
    result = await configure(
        hass, result, {"rate_mode": "single", "feed_in_type": "partial", "rate": 7.94}
    )
    assert result["step_id"] == "sources"
    result = await configure(
        hass, result, {"meter_entity": METER, "price_entity": PRICE}
    )
    assert result["step_id"] == "summary"
    assert result["description_placeholders"]["applies_from"] == "2026-01-01"
    assert result["description_placeholders"]["rate"] == "7.94"
    assert result["description_placeholders"]["note"] == ""
    result = await configure(hass, result, {CONF_OVERRIDE: OVERRIDE_AUTO})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Dach"
    assert result["data"] == entry_data()
    assert result["result"].unique_id == METER


async def test_tiered_rates(hass: HomeAssistant) -> None:
    result = await configure(hass, await start(hass), {**PLANT, "power_kw": 25})
    result = await configure(
        hass, result, {"rate_mode": "tiered", "feed_in_type": "partial"}
    )
    assert result["step_id"] == "tier_rates"
    assert [str(k) for k in result["data_schema"].schema] == ["band_0_10", "band_10_40"]
    result = await configure(hass, result, {"band_0_10": 8.51, "band_10_40": 7.43})
    assert result["step_id"] == "sources"
    result = await configure(
        hass, result, {"meter_entity": METER, "price_entity": PRICE}
    )
    # (10 * 8.51 + 15 * 7.43) / 25 = 7.862
    assert result["description_placeholders"]["rate"] == "7.862"
    result = await configure(hass, result, {CONF_OVERRIDE: OVERRIDE_AUTO})
    assert result["data"][CONF_RATES] == [8.51, 7.43]


async def test_plant_errors(hass: HomeAssistant) -> None:
    result = await configure(
        hass,
        await start(hass),
        {k: v for k, v in PLANT.items() if k != "smart_meter_date"},
    )
    assert result["errors"] == {"smart_meter_date": "smart_meter_date_required"}
    result = await configure(hass, result, {**PLANT, "name": "  "})
    assert result["errors"] == {"name": "name_required"}


@pytest.mark.freeze_time("2026-10-26 12:00:00+00:00")
async def test_dates_in_future(hass: HomeAssistant) -> None:
    result = await configure(
        hass, await start(hass), {**PLANT, "commissioned": "2026-10-27"}
    )
    assert result["errors"] == {"commissioned": "date_in_future"}
    result = await configure(hass, result, {**PLANT, "smart_meter_date": "2026-10-27"})
    assert result["errors"] == {"smart_meter_date": "date_in_future"}


@pytest.mark.freeze_time("2026-10-26 12:00:00+00:00")
async def test_note_when_rule_starts_in_future_year(hass: HomeAssistant) -> None:
    """iMSys this year: the rule starts next year, which is worth a second look."""
    plant = {**PLANT, "commissioned": "2026-03-01", "smart_meter_date": "2026-03-10"}
    result = await configure(hass, await start(hass), plant)
    result = await configure(
        hass, result, {"rate_mode": "single", "feed_in_type": "partial", "rate": 7.94}
    )
    result = await configure(
        hass, result, {"meter_entity": METER, "price_entity": PRICE}
    )
    assert result["description_placeholders"]["applies_from"] == "2027-01-01"
    assert result["description_placeholders"]["note"].startswith("⚠️")


async def test_rate_required(hass: HomeAssistant) -> None:
    result = await configure(hass, await start(hass), PLANT)
    result = await configure(
        hass, result, {"rate_mode": "single", "feed_in_type": "partial"}
    )
    assert result["errors"] == {"rate": "rate_required"}


async def test_source_errors(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.power", "500", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.no_price", "unknown", {})
    result = await configure(hass, await start(hass), PLANT)
    result = await configure(
        hass, result, {"rate_mode": "single", "feed_in_type": "partial", "rate": 7.94}
    )
    result = await configure(
        hass,
        result,
        {"meter_entity": "sensor.power", "price_entity": "sensor.no_price"},
    )
    assert result["errors"] == {
        "meter_entity": "meter_unit",
        "price_entity": "price_invalid",
    }


async def test_override_needs_date(hass: HomeAssistant) -> None:
    result = await configure(hass, await start(hass), PLANT)
    result = await configure(
        hass, result, {"rate_mode": "single", "feed_in_type": "partial", "rate": 7.94}
    )
    result = await configure(
        hass, result, {"meter_entity": METER, "price_entity": PRICE}
    )
    result = await configure(hass, result, {CONF_OVERRIDE: OVERRIDE_FROM_DATE})
    assert result["errors"] == {CONF_OVERRIDE_DATE: "override_date_required"}
    result = await configure(
        hass,
        result,
        {CONF_OVERRIDE: OVERRIDE_FROM_DATE, CONF_OVERRIDE_DATE: "2026-05-01"},
    )
    assert result["data"][CONF_OVERRIDE_DATE] == "2026-05-01"


async def test_meter_already_in_use(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id=METER, data=entry_data()).add_to_hass(hass)
    result = await configure(hass, await start(hass), PLANT)
    result = await configure(
        hass, result, {"rate_mode": "single", "feed_in_type": "partial", "rate": 7.94}
    )
    result = await configure(
        hass, result, {"meter_entity": METER, "price_entity": PRICE}
    )
    assert result["errors"] == {"meter_entity": "meter_in_use"}


async def test_reconfigure(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=METER, title="Dach", data=entry_data()
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await configure(hass, result, {**PLANT, "name": "Dach Süd"})
    result = await configure(
        hass, result, {"rate_mode": "single", "feed_in_type": "partial", "rate": 8.0}
    )
    result = await configure(
        hass, result, {"meter_entity": METER, "price_entity": PRICE}
    )
    result = await configure(hass, result, {CONF_OVERRIDE: OVERRIDE_AUTO})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.title == "Dach Süd"
    assert entry.data[CONF_RATES] == [8.0]


async def test_note_above_100_kw(hass: HomeAssistant) -> None:
    """No fixed feed-in tariff above 100 kW (§ 21 EEG): say so."""
    result = await configure(hass, await start(hass), {**PLANT, "power_kw": 150})
    result = await configure(
        hass, result, {"rate_mode": "single", "feed_in_type": "partial", "rate": 7.94}
    )
    result = await configure(
        hass, result, {"meter_entity": METER, "price_entity": PRICE}
    )
    assert result["description_placeholders"]["note"].startswith("ℹ️")
    # Exactly 100 kW still has the fixed tariff.
    result = await configure(hass, await start(hass), {**PLANT, "power_kw": 100})
    result = await configure(
        hass, result, {"rate_mode": "single", "feed_in_type": "partial", "rate": 7.94}
    )
    result = await configure(
        hass, result, {"meter_entity": METER, "price_entity": PRICE}
    )
    assert result["description_placeholders"]["note"] == ""
