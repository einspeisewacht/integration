"""Tests for the config flow and reconfiguration, suggestions from Tarifwacht."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, section
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.einspeisewacht.const import (
    CONF_BACKFILL,
    CONF_FEED_IN_TYPE,
    CONF_METER,
    CONF_METER_PREVIOUS,
    CONF_OVERRIDE,
    CONF_OVERRIDE_DATE,
    CONF_POWER,
    CONF_RATE_MODE,
    CONF_RATES,
    DOMAIN,
    FEED_IN_FULL,
    OVERRIDE_FROM_DATE,
    RATE_TIERED,
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
SOURCES = {"meter_entity": METER, "price_entity": PRICE}


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


def fields(result: dict) -> list[str]:
    """Top-level fields and sections of a form."""
    return [str(key) for key in result["data_schema"].schema]


def section_of(result: dict, name: str) -> section:
    return next(
        value for key, value in result["data_schema"].schema.items() if str(key) == name
    )


def unchanged_input(result: dict) -> dict[str, Any]:
    """What the frontend sends for a form submitted unchanged, without
    opening a section (computeInitialHaFormData): each field's suggested
    value, else its default; sections nested, collapsed or not."""

    def values(schema: dict[Any, Any]) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for key, value in schema.items():
            if isinstance(value, section):
                data[str(key)] = values(value.schema.schema)
                continue
            suggested = (key.description or {}).get("suggested_value")
            if suggested is not None:
                data[str(key)] = suggested
            elif key.default is not type(key)("x").default:
                data[str(key)] = key.default()
        return data

    return values(result["data_schema"].schema)


async def to_sources(hass: HomeAssistant, **plant: Any) -> dict:
    """Plant and a single rate: on to the last step."""
    result = await configure(hass, await start(hass), {**PLANT, **plant})
    return await configure(hass, result, {"rate": 7.94})


def add_entry(hass: HomeAssistant, **changes: Any) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=METER, title="Dach", data=entry_data(**changes)
    )
    entry.add_to_hass(hass)
    return entry


async def test_full_flow_single_rate(hass: HomeAssistant) -> None:
    """Three steps; up to 10 kWp the rate step has a single field."""
    result = await start(hass)
    assert result["step_id"] == "user"
    result = await configure(hass, result, PLANT)
    assert result["step_id"] == "rate"
    assert fields(result) == ["rate"]
    result = await configure(hass, result, {"rate": 7.94})
    # Without Tarifwacht: the tip.
    assert result["step_id"] == "sources_tarifwacht_tip"
    assert fields(result) == ["meter_entity", "price_entity", "backfill_smard", "rule"]
    assert section_of(result, "rule").options["collapsed"] is True
    placeholders = result["description_placeholders"]
    assert placeholders["applies_from"] == "2026-01-01"
    assert placeholders["rule"].endswith(", from 2026-01-01")
    assert placeholders["rate"] == "7.94"
    assert placeholders["note"] == ""
    result = await configure(hass, result, SOURCES)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Dach"
    assert result["data"] == entry_data()
    assert result["result"].unique_id == METER


async def test_tiered_rates(hass: HomeAssistant) -> None:
    result = await configure(hass, await start(hass), {**PLANT, "power_kw": 25})
    # Above 10 kWp: the bands in a collapsed section.
    assert fields(result) == ["rate", "tiers"]
    assert section_of(result, "tiers").options["collapsed"] is True
    result = await configure(
        hass, result, {"tiers": {"rate_mode": "tiered", "feed_in_type": "partial"}}
    )
    assert result["step_id"] == "tier_rates"
    assert fields(result) == ["band_0_10", "band_10_40"]
    result = await configure(hass, result, {"band_0_10": 8.51, "band_10_40": 7.43})
    # Without Tarifwacht: the tip.
    assert result["step_id"] == "sources_tarifwacht_tip"
    # (10 * 8.51 + 15 * 7.43) / 25 = 7.862
    assert result["description_placeholders"]["rate"] == "7.862"
    result = await configure(hass, result, SOURCES)
    assert result["data"][CONF_RATES] == [8.51, 7.43]
    assert result["data"][CONF_RATE_MODE] == RATE_TIERED


async def test_single_rate_above_10_kwp(hass: HomeAssistant) -> None:
    """The section left closed: one rate."""
    result = await configure(hass, await start(hass), {**PLANT, "power_kw": 25})
    result = await configure(hass, result, {"rate": 7.5})
    result = await configure(hass, result, SOURCES)
    assert result["data"] == entry_data(**{CONF_POWER: 25.0, CONF_RATES: [7.5]})


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
    result = await to_sources(
        hass, commissioned="2026-03-01", smart_meter_date="2026-03-10"
    )
    assert result["description_placeholders"]["applies_from"] == "2027-01-01"
    assert result["description_placeholders"]["note"].startswith("⚠️")


async def test_rate_required(hass: HomeAssistant) -> None:
    result = await configure(hass, await start(hass), PLANT)
    result = await configure(hass, result, {})
    assert result["errors"] == {"rate": "rate_required"}


async def test_source_errors(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.power", "500", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.no_price", "cheap", {})
    result = await to_sources(hass)
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
    result = await to_sources(hass)
    result = await configure(
        hass, result, {**SOURCES, "rule": {CONF_OVERRIDE: OVERRIDE_FROM_DATE}}
    )
    assert result["errors"] == {"base": "override_date_required"}
    # The section the error is about is open.
    assert section_of(result, "rule").options["collapsed"] is False
    result = await configure(
        hass,
        result,
        {
            **SOURCES,
            "rule": {
                CONF_OVERRIDE: OVERRIDE_FROM_DATE,
                CONF_OVERRIDE_DATE: "2026-05-01",
            },
        },
    )
    assert result["data"][CONF_OVERRIDE] == OVERRIDE_FROM_DATE
    assert result["data"][CONF_OVERRIDE_DATE] == "2026-05-01"


async def test_backfill_opt_in(hass: HomeAssistant) -> None:
    result = await to_sources(hass)
    result = await configure(hass, result, {**SOURCES, CONF_BACKFILL: True})
    assert result["data"][CONF_BACKFILL] is True


async def test_meter_already_in_use(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id=METER, data=entry_data()).add_to_hass(hass)
    result = await configure(hass, await to_sources(hass), SOURCES)
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
    result = await to_sources(hass)
    result = await configure(
        hass,
        result,
        {"meter_entity": energy.entity_id, "price_entity": money.entity_id},
    )
    assert result["errors"] == {
        "meter_entity": "own_entity",
        "price_entity": "own_entity",
    }
    result = await configure(hass, result, SOURCES)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_reconfigure_refuses_the_entrys_own_sensor(hass: HomeAssistant) -> None:
    entry = add_entry(hass)
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
    result = await configure(hass, result, {"rate": 7.94})
    result = await configure(
        hass, result, {"meter_entity": own.entity_id, "price_entity": PRICE}
    )
    assert result["errors"] == {"meter_entity": "own_entity"}


async def test_reconfigure(hass: HomeAssistant) -> None:
    entry = add_entry(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await configure(hass, result, {**PLANT, "name": "Dach Süd"})
    result = await configure(hass, result, {"rate": 8.0})
    assert result["step_id"] == "sources"
    result = await configure(hass, result, SOURCES)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.title == "Dach Süd"
    assert entry.data[CONF_RATES] == [8.0]


@pytest.mark.freeze_time("2026-11-08 12:00:00+00:00")
async def test_reconfigure_starts_with_an_overview(hass: HomeAssistant) -> None:
    hass.states.async_set(
        METER, "1234567.0", {**METER_ATTRIBUTES, "friendly_name": "Smart Meter"}
    )
    entry = add_entry(hass)
    result = await entry.start_reconfigure_flow(hass)
    text = result["description_placeholders"]["overview"]
    assert text.splitlines() == [
        "**Set up**",
        "- **Plant:** 8.5 kWp, commissioned on 2025-06-15",
        "- **Remuneration:** 7.94 ct/kWh",
        "- **Rule today:** quarter-hour rule (§ 51 EEG) since 2026-01-01"
        " (iMSys installed on 2025-06-15)",
        "- **Feed-in meter:** Smart Meter",
        "- **Day-ahead price:** EPEX Spot Data Market Price",
        "- **SMARD.de:** off",
        "",
        "**Missing**",
        # Set up today, commissioned in 2025.
        "- Without SMARD.de the extension (§ 51a EEG) counts negative quarter"
        " hours only from setup, not since commissioning.",
    ]


@pytest.mark.freeze_time("2026-11-08 12:00:00+00:00")
async def test_overview_says_what_is_missing(hass: HomeAssistant) -> None:
    hass.states.async_remove(METER)
    hass.states.async_set(PRICE, "unavailable", {})
    entry = add_entry(hass, **{CONF_BACKFILL: True})
    result = await entry.start_reconfigure_flow(hass)
    text = result["description_placeholders"]["overview"]
    assert "**Missing**" in text
    assert f"Feed-in meter {METER} not found – nothing is booked" in text
    assert "after an hour SMARD.de stands in" in text


async def test_reconfigure_unchanged_keeps_values_in_sections(
    hass: HomeAssistant,
) -> None:
    """Stored values show inside the sections, which open when in use; the
    forms submitted as they are (sections not opened) keep everything."""
    entry = add_entry(
        hass,
        **{
            CONF_POWER: 25.0,
            CONF_RATE_MODE: RATE_TIERED,
            CONF_FEED_IN_TYPE: FEED_IN_FULL,
            CONF_RATES: [12.6, 10.56],
            CONF_OVERRIDE: OVERRIDE_FROM_DATE,
            CONF_OVERRIDE_DATE: "2026-05-01",
            CONF_BACKFILL: True,
        },
    )
    before = dict(entry.data)
    result = await entry.start_reconfigure_flow(hass)
    result = await configure(hass, result, unchanged_input(result))
    assert result["step_id"] == "rate"
    assert section_of(result, "tiers").options["collapsed"] is False
    assert unchanged_input(result)["tiers"] == {
        "rate_mode": "tiered",
        "feed_in_type": "full",
    }
    result = await configure(hass, result, unchanged_input(result))
    assert result["step_id"] == "tier_rates"
    result = await configure(hass, result, unchanged_input(result))
    assert result["step_id"] == "sources"
    assert section_of(result, "rule").options["collapsed"] is False
    assert unchanged_input(result)["rule"] == {
        "override": "from_date",
        "override_date": "2026-05-01",
    }
    result = await configure(hass, result, unchanged_input(result))
    assert result["reason"] == "reconfigure_successful"
    assert dict(entry.data) == before


async def test_reconfigure_without_sections_keeps_them(hass: HomeAssistant) -> None:
    """A section left out of the input keeps what is stored."""
    entry = add_entry(
        hass, **{CONF_OVERRIDE: OVERRIDE_FROM_DATE, CONF_OVERRIDE_DATE: "2026-05-01"}
    )
    result = await entry.start_reconfigure_flow(hass)
    result = await configure(hass, result, PLANT)
    result = await configure(hass, result, {"rate": 7.94})
    result = await configure(hass, result, SOURCES)
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_OVERRIDE] == OVERRIDE_FROM_DATE
    assert entry.data[CONF_OVERRIDE_DATE] == "2026-05-01"


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


async def test_tarifwacht_without_pv_subentry(hass: HomeAssistant) -> None:
    """Only a fixed price: nothing to suggest, the tip stays."""
    add_tarifwacht(hass, FIXED_TARIFF)
    result = await to_sources(hass)
    assert result["step_id"] == "sources_tarifwacht_tip"
    placeholders = result["description_placeholders"]
    assert placeholders["tarifwacht_url"] == "https://github.com/tarifwacht/integration"
    assert "tarifwacht" not in placeholders
    assert not any(suggested(result).values())


async def test_sources_suggested_from_tarifwacht(hass: HomeAssistant) -> None:
    add_tarifwacht(hass, FIXED_TARIFF, MARKET_TARIFF, SOLAR)
    result = await to_sources(hass)
    assert result["step_id"] == "sources_tarifwacht"
    assert result["description_placeholders"]["tarifwacht"] == "Haus"
    assert suggested(result) == {"meter_entity": METER, "price_entity": PRICE}
    result = await configure(hass, result, SOURCES)
    assert result["type"] is FlowResultType.CREATE_ENTRY

    # A second entry: the meter belongs to the first one, the price is kept.
    result = await to_sources(hass)
    assert result["step_id"] == "sources_tarifwacht"
    assert suggested(result) == {"price_entity": PRICE}


async def test_reconfigure_suggests_nothing_from_tarifwacht(
    hass: HomeAssistant,
) -> None:
    add_tarifwacht(hass, MARKET_TARIFF, {**SOLAR, "feed_in_entity": "sensor.other"})
    entry = add_entry(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await configure(hass, result, PLANT)
    result = await configure(hass, result, {"rate": 8.0})
    assert result["step_id"] == "sources"
    assert suggested(result)["meter_entity"] == METER


async def test_note_above_100_kw(hass: HomeAssistant) -> None:
    """No fixed feed-in tariff above 100 kW (§ 21 EEG): say so."""
    result = await to_sources(hass, power_kw=150)
    assert result["description_placeholders"]["note"].startswith("ℹ️")
    # Exactly 100 kW still has the fixed tariff.
    result = await to_sources(hass, power_kw=100)
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
    entry = add_entry(hass, **{CONF_METER_PREVIOUS: ["sensor.old_export"]})
    result = await entry.start_reconfigure_flow(hass)
    result = await configure(hass, result, PLANT)
    result = await configure(hass, result, {"rate": 7.94})
    result = await configure(
        hass, result, {"meter_entity": meter, "price_entity": PRICE}
    )
    assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == meter
    assert entry.data.get(CONF_METER_PREVIOUS) == previous


async def test_reconfigure_keeps_a_rename_made_while_the_flow_was_open(
    hass: HomeAssistant,
) -> None:
    """The form still holds the old meter id; the rename is not undone."""
    entry = add_entry(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await configure(hass, result, PLANT)
    result = await configure(hass, result, {"rate": 7.94})
    assert result["step_id"] == "sources"
    # Renamed now (as __init__.py follows it), while the last form is open.
    hass.states.async_remove(METER)
    hass.states.async_set("sensor.meter_export", "1234567.0", METER_ATTRIBUTES)
    hass.config_entries.async_update_entry(
        entry,
        unique_id="sensor.meter_export",
        data=renamed_data(entry.data, METER, "sensor.meter_export"),
    )
    result = await configure(hass, result, SOURCES)
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_METER] == "sensor.meter_export"
    assert entry.data[CONF_METER_PREVIOUS] == [METER]
    assert entry.unique_id == "sensor.meter_export"


# --- suggestions besides Tarifwacht -----------------------------------------------


def epex_sensor(hass: HomeAssistant, key: str, object_id: str) -> str:
    """A registry entry as EPEX Spot creates it (unique id f"{source} {key}")."""
    return (
        er.async_get(hass)
        .async_get_or_create(
            "sensor",
            "epex_spot",
            f"epex_spot SMARD.de DE-LU {key}",
            suggested_object_id=object_id,
        )
        .entity_id
    )


def energy_prefs(hass: HomeAssistant, prefs: dict):
    """The energy dashboard with these preferences."""
    hass.config.components.add("energy")
    return patch(
        "homeassistant.components.energy.data.async_get_manager",
        AsyncMock(return_value=SimpleNamespace(data=prefs)),
    )


async def test_meter_suggested_from_energy_dashboard(hass: HomeAssistant) -> None:
    prefs = {
        "energy_sources": [
            {
                "type": "grid",
                "stat_energy_from": "sensor.import",
                "stat_energy_to": METER,
            }
        ]
    }
    with energy_prefs(hass, prefs):
        result = await to_sources(hass)
    assert suggested(result)["meter_entity"] == METER
    # Also in the older format with lists.
    legacy = {
        "energy_sources": [
            {
                "type": "grid",
                "flow_from": [{"stat_energy_from": "sensor.import"}],
                "flow_to": [{"stat_energy_to": METER}],
            }
        ]
    }
    with energy_prefs(hass, legacy):
        result = await to_sources(hass)
    assert suggested(result)["meter_entity"] == METER


async def test_energy_meter_not_suggested_when_in_use(hass: HomeAssistant) -> None:
    add_entry(hass)
    prefs = {"energy_sources": [{"type": "grid", "stat_energy_to": METER}]}
    with energy_prefs(hass, prefs):
        result = await to_sources(hass)
    assert "meter_entity" not in suggested(result)


async def test_meter_suggestion_never_blocks(hass: HomeAssistant) -> None:
    hass.config.components.add("energy")
    with patch(
        "homeassistant.components.energy.data.async_get_manager",
        AsyncMock(side_effect=RuntimeError("broken")),
    ):
        result = await to_sources(hass)
    assert result["type"] is FlowResultType.FORM
    assert "meter_entity" not in suggested(result)


async def test_epex_market_price_suggested(hass: HomeAssistant) -> None:
    """The market price, never the total price (surcharges and VAT)."""
    epex_sensor(hass, "Total Price", "epex_spot_data_total_price")
    market = epex_sensor(hass, "MarketPrice", "epex_market")
    result = await to_sources(hass)
    assert suggested(result)["price_entity"] == market


async def test_tarifwacht_first_then_the_others(hass: HomeAssistant) -> None:
    """Tarifwacht gives the meter only: the price comes from EPEX Spot."""
    market = epex_sensor(hass, "MarketPrice", "epex_market")
    add_tarifwacht(hass, FIXED_TARIFF, {**SOLAR, "feed_in_entity": METER})
    prefs = {"energy_sources": [{"type": "grid", "stat_energy_to": "sensor.other"}]}
    hass.states.async_set("sensor.other", "1.0", METER_ATTRIBUTES)
    with energy_prefs(hass, prefs):
        result = await to_sources(hass)
    assert result["step_id"] == "sources_tarifwacht"
    assert suggested(result) == {"meter_entity": METER, "price_entity": market}


async def test_unavailable_price_sensor(hass: HomeAssistant) -> None:
    """A sensor of an integration that is not loaded keeps its attributes
    from the registry; the error says it is unavailable."""
    hass.states.async_set(
        "sensor.epex_down",
        "unavailable",
        {"unit_of_measurement": "€/kWh", "restored": True},
    )
    hass.states.async_set(
        "sensor.epex_starting", "unknown", {"unit_of_measurement": "€/kWh"}
    )
    result = await to_sources(hass)
    for price in ("sensor.epex_down", "sensor.epex_starting"):
        result = await configure(
            hass, result, {"meter_entity": METER, "price_entity": price}
        )
        assert result["errors"] == {"price_entity": "price_unavailable"}
