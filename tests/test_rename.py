"""Following renamed source entities: entry data and unique id."""

from __future__ import annotations

from custom_components.einspeisewacht.const import (
    CONF_METER,
    CONF_METER_PREVIOUS,
    CONF_NAME,
    CONF_PRICE,
)
from custom_components.einspeisewacht.rename import (
    PREVIOUS_KEPT,
    renamed_data,
    renamed_unique_id,
    sources,
)

DATA = {
    CONF_NAME: "Dach",
    CONF_METER: "sensor.grid_export",
    CONF_PRICE: "sensor.epex_price",
}


def test_sources() -> None:
    assert sources(DATA) == {"sensor.grid_export", "sensor.epex_price"}
    assert sources({}) == set()


def test_renamed_price() -> None:
    data = renamed_data(DATA, "sensor.epex_price", "sensor.tibber_price")
    assert data == {**DATA, CONF_PRICE: "sensor.tibber_price"}
    # The original stays as it was (entry data is read-only).
    assert DATA[CONF_PRICE] == "sensor.epex_price"


def test_renamed_meter_keeps_the_earlier_ids() -> None:
    once = renamed_data(DATA, "sensor.grid_export", "sensor.meter_export")
    assert once[CONF_METER] == "sensor.meter_export"
    assert once[CONF_METER_PREVIOUS] == ["sensor.grid_export"]
    # Renamed again before the reload (A -> B -> C): both earlier ids count.
    twice = renamed_data(once, "sensor.meter_export", "sensor.export")
    assert twice[CONF_METER_PREVIOUS] == ["sensor.grid_export", "sensor.meter_export"]
    # Back to an earlier id: it is the meter again, not one of its aliases.
    back = renamed_data(twice, "sensor.export", "sensor.grid_export")
    assert back[CONF_METER] == "sensor.grid_export"
    assert back[CONF_METER_PREVIOUS] == ["sensor.meter_export", "sensor.export"]


def test_earlier_ids_are_bounded() -> None:
    data = dict(DATA)
    for n in range(10):
        data = renamed_data(data, data[CONF_METER], f"sensor.export_{n}")
    assert len(data[CONF_METER_PREVIOUS]) == PREVIOUS_KEPT
    assert data[CONF_METER_PREVIOUS][-1] == "sensor.export_8"


def test_unique_id_is_the_meter() -> None:
    assert renamed_unique_id("sensor.a", "sensor.a", "sensor.b") == "sensor.b"
    assert renamed_unique_id("sensor.c", "sensor.a", "sensor.b") is None
    assert renamed_unique_id(None, "sensor.a", "sensor.b") is None
