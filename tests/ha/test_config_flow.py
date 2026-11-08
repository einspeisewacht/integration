"""Tests for the config flow and reconfiguration, suggestions from Tarifwacht."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.einspeisewacht.const import (
    CONF_METER,
    CONF_METER_PREVIOUS,
    CONF_OVERRIDE,
    CONF_OVERRIDE_DATE,
    CONF_RATES,
    DOMAIN,
    OVERRIDE_AUTO,
    OVERRIDE_FROM_DATE,
)
from custom_components.einspeisewacht.rename import renamed_data

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
    # Without Tarifwacht: the tip.
    assert result["step_id"] == "sources_tarifwacht_tip"
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
    # Without Tarifwacht: the tip.
    assert result["step_id"] == "sources_tarifwacht_tip"
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


async def test_own_sensors_as_sources_are_refused(hass: HomeAssistant) -> None:
    """A sensor of Einspeisewacht itself (seen in Wärmewacht, 2026-11): the
    energy total passes the meter checks, the money total the price check."""
    registry = er.async_get(hass)
    energy = registry.async_get_or_create(
        "sensor", DOMAIN, "01JZ_energy_paid", suggested_object_id="dach_energy_paid"
    )
    hass.states.async_set(energy.entity_id, "12.5", METER_ATTRIBUTES)
    money = registry.async_get_or_create(
        "sensor", DOMAIN, "01JZ_revenue", suggested_object_id="dach_revenue"
    )
    hass.states.async_set(money.entity_id, "3.21", {"unit_of_measurement": "EUR"})
    result = await configure(hass, await start(hass), PLANT)
    result = await configure(
        hass, result, {"rate_mode": "single", "feed_in_type": "partial", "rate": 7.94}
    )
    result = await configure(
        hass,
        result,
        {"meter_entity": energy.entity_id, "price_entity": money.entity_id},
    )
    assert result["errors"] == {
        "meter_entity": "own_entity",
        "price_entity": "own_entity",
    }
    result = await configure(
        hass, result, {"meter_entity": METER, "price_entity": PRICE}
    )
    assert result["step_id"] == "summary"


async def test_reconfigure_refuses_the_entrys_own_sensor(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=METER, title="Dach", data=entry_data()
    )
    entry.add_to_hass(hass)
    own = er.async_get(hass).async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_energy_paid",
        config_entry=entry,
        suggested_object_id="dach_energy_paid",
    )
    hass.states.async_set(own.entity_id, "12.5", METER_ATTRIBUTES)
    result = await entry.start_reconfigure_flow(hass)
    result = await configure(hass, result, PLANT)
    result = await configure(
        hass, result, {"rate_mode": "single", "feed_in_type": "partial", "rate": 7.94}
    )
    result = await configure(
        hass, result, {"meter_entity": own.entity_id, "price_entity": PRICE}
    )
    assert result["errors"] == {"meter_entity": "own_entity"}


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


def suggested(result: dict) -> dict[str, Any]:
    """Prefilled values of a form."""
    return {
        str(key): key.description["suggested_value"]
        for key in result["data_schema"].schema
        if "suggested_value" in (key.description or {})
    }


def add_tarifwacht(hass: HomeAssistant, *subentries: dict[str, Any]) -> None:
    """A Tarifwacht entry (not set up; only its data is read)."""
    MockConfigEntry(
        domain="tarifwacht",
        title="Haus",
        data={"name": "Haus", "meter_entity": "sensor.grid_import"},
        version=2,
        subentries_data=[
            {
                "data": {k: v for k, v in data.items() if k != "type"},
                "subentry_id": f"sub{i}",
                "subentry_type": data["type"],
                "title": data["type"],
                "unique_id": None,
            }
            for i, data in enumerate(subentries)
        ],
    ).add_to_hass(hass)


FIXED_TARIFF = {"type": "tariff", "kind": "fixed", "price": 30.0, "current": True}
MARKET_TARIFF = {
    "type": "tariff",
    "kind": "dynamic_market",
    "price_entity": PRICE,
    "current": False,
}
SOLAR = {
    "type": "solar",
    "feed_in_entity": METER,
    "pv_entity": "sensor.pv",
    "feed_in_rate": 7.94,
    "negative_unpaid": True,
    "same_inverter": False,
}


async def to_sources(hass: HomeAssistant) -> dict:
    result = await configure(hass, await start(hass), PLANT)
    return await configure(
        hass, result, {"rate_mode": "single", "feed_in_type": "partial", "rate": 7.94}
    )


async def test_tarifwacht_without_pv_subentry(hass: HomeAssistant) -> None:
    """Only a fixed price: nothing to suggest, the tip stays."""
    add_tarifwacht(hass, FIXED_TARIFF)
    result = await to_sources(hass)
    assert result["step_id"] == "sources_tarifwacht_tip"
    assert result["description_placeholders"] == {
        "tarifwacht_url": "https://github.com/tarifwacht/integration"
    }
    assert not any(suggested(result).values())


async def test_sources_suggested_from_tarifwacht(hass: HomeAssistant) -> None:
    add_tarifwacht(hass, FIXED_TARIFF, MARKET_TARIFF, SOLAR)
    result = await to_sources(hass)
    assert result["step_id"] == "sources_tarifwacht"
    assert result["description_placeholders"] == {"tarifwacht": "Haus"}
    assert suggested(result) == {"meter_entity": METER, "price_entity": PRICE}
    result = await configure(
        hass, result, {"meter_entity": METER, "price_entity": PRICE}
    )
    assert result["step_id"] == "summary"
    result = await configure(hass, result, {CONF_OVERRIDE: OVERRIDE_AUTO})
    assert result["type"] is FlowResultType.CREATE_ENTRY

    # A second entry: the meter belongs to the first one, the price is kept.
    result = await to_sources(hass)
    assert result["step_id"] == "sources_tarifwacht"
    assert suggested(result) == {"price_entity": PRICE}


async def test_reconfigure_suggests_nothing_from_tarifwacht(
    hass: HomeAssistant,
) -> None:
    add_tarifwacht(hass, MARKET_TARIFF, {**SOLAR, "feed_in_entity": "sensor.other"})
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=METER, title="Dach", data=entry_data()
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await configure(hass, result, PLANT)
    result = await configure(
        hass, result, {"rate_mode": "single", "feed_in_type": "partial", "rate": 8.0}
    )
    assert result["step_id"] == "sources"
    assert suggested(result)["meter_entity"] == METER


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


@pytest.mark.parametrize(
    ("meter", "previous"),
    [(METER, ["sensor.old_export"]), ("sensor.other_export", None)],
)
async def test_reconfigure_keeps_earlier_meter_ids_only_for_the_same_meter(
    hass: HomeAssistant, meter: str, previous: list[str] | None
) -> None:
    """Earlier ids of a renamed meter mean nothing for another meter."""
    hass.states.async_set("sensor.other_export", "5.0", METER_ATTRIBUTES)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=METER,
        title="Dach",
        data=entry_data(**{CONF_METER_PREVIOUS: ["sensor.old_export"]}),
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await configure(hass, result, PLANT)
    result = await configure(
        hass, result, {"rate_mode": "single", "feed_in_type": "partial", "rate": 7.94}
    )
    result = await configure(
        hass, result, {"meter_entity": meter, "price_entity": PRICE}
    )
    result = await configure(hass, result, {CONF_OVERRIDE: OVERRIDE_AUTO})
    assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == meter
    assert entry.data.get(CONF_METER_PREVIOUS) == previous


async def test_reconfigure_keeps_a_rename_made_while_the_flow_was_open(
    hass: HomeAssistant,
) -> None:
    """The form still holds the old meter id; the rename is not undone."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=METER, title="Dach", data=entry_data()
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await configure(hass, result, PLANT)
    result = await configure(
        hass, result, {"rate_mode": "single", "feed_in_type": "partial", "rate": 7.94}
    )
    result = await configure(
        hass, result, {"meter_entity": METER, "price_entity": PRICE}
    )
    # Renamed now (as __init__.py follows it), before the last step.
    hass.config_entries.async_update_entry(
        entry,
        unique_id="sensor.meter_export",
        data=renamed_data(entry.data, METER, "sensor.meter_export"),
    )
    result = await configure(hass, result, {CONF_OVERRIDE: OVERRIDE_AUTO})
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_METER] == "sensor.meter_export"
    assert entry.data[CONF_METER_PREVIOUS] == [METER]
    assert entry.unique_id == "sensor.meter_export"
