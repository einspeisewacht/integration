"""Suggestions for the sources step besides Tarifwacht (no Home Assistant)."""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.einspeisewacht.suggest import (
    epex_market_sensor,
    grid_export_stats,
)


def entity(entity_id: str, unique_id: str, platform: str = "epex_spot", **extra):
    return SimpleNamespace(
        entity_id=entity_id,
        unique_id=unique_id,
        platform=platform,
        domain=entity_id.split(".")[0],
        disabled_by=extra.get("disabled_by"),
    )


def test_epex_market_price_only() -> None:
    entries = [
        entity(
            "sensor.epex_spot_data_total_price", "epex_spot SMARD.de DE-LU Total Price"
        ),
        entity(
            "sensor.epex_spot_data_average_price",
            "epex_spot SMARD.de DE-LU Average Price",
        ),
        entity(
            "sensor.epex_spot_data_market_price", "epex_spot SMARD.de DE-LU MarketPrice"
        ),
    ]
    assert epex_market_sensor(entries) == "sensor.epex_spot_data_market_price"
    assert epex_market_sensor(entries[:2]) is None


def test_epex_only_its_own_enabled_sensors() -> None:
    entries = [
        entity("sensor.other", "x MarketPrice", platform="other"),
        entity("sensor.epex_off", "epex_spot A MarketPrice", disabled_by="user"),
    ]
    assert epex_market_sensor(entries) is None
    two = [
        entity("sensor.epex_b", "epex_spot B MarketPrice"),
        entity("sensor.epex_a", "epex_spot A MarketPrice"),
    ]
    assert epex_market_sensor(two) == "sensor.epex_a"


def test_grid_export_unified_format() -> None:
    prefs = {
        "energy_sources": [
            {"type": "solar", "stat_energy_from": "sensor.pv"},
            {
                "type": "grid",
                "stat_energy_from": "sensor.import",
                "stat_energy_to": "sensor.export_a",
            },
            {
                "type": "grid",
                "stat_energy_from": "sensor.import_b",
                "stat_energy_to": None,
            },
            {"type": "grid", "stat_energy_to": "sensor.export_b"},
        ]
    }
    assert grid_export_stats(prefs) == ["sensor.export_a", "sensor.export_b"]


def test_grid_export_legacy_format() -> None:
    prefs = {
        "energy_sources": [
            {
                "type": "grid",
                "flow_from": [{"stat_energy_from": "sensor.import"}],
                "flow_to": [
                    {"stat_energy_to": "sensor.export"},
                    {"stat_energy_to": "sensor.export"},
                ],
            }
        ]
    }
    assert grid_export_stats(prefs) == ["sensor.export"]


def test_grid_export_without_preferences() -> None:
    assert grid_export_stats(None) == []
    assert (
        grid_export_stats({"energy_sources": [{"type": "grid", "flow_to": None}]}) == []
    )
