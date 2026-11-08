"""Suggestions from sister integrations (duck-typed config entries)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from custom_components.einspeisewacht.sisters import tarifwacht_sources


def entry(title: str, *subentries: tuple[str, dict[str, Any]]) -> SimpleNamespace:
    return SimpleNamespace(
        title=title,
        subentries={
            str(i): SimpleNamespace(subentry_type=kind, data=data)
            for i, (kind, data) in enumerate(subentries)
        },
    )


FIXED = ("tariff", {"kind": "fixed", "price": 30.0, "current": True})
TOTAL = ("tariff", {"kind": "dynamic_total", "price_entity": "sensor.total_price"})
MARKET = ("tariff", {"kind": "dynamic_market", "price_entity": "sensor.market"})
SOLAR = ("solar", {"feed_in_entity": "sensor.feed_in", "pv_entity": "sensor.pv"})


def test_no_tarifwacht() -> None:
    assert tarifwacht_sources([]) is None


def test_tarifwacht_without_pv_subentry_and_exchange_price() -> None:
    """A total price includes surcharges and VAT: never suggested."""
    assert tarifwacht_sources([entry("Haus", FIXED, TOTAL)]) is None


def test_exchange_price_without_pv_subentry() -> None:
    assert tarifwacht_sources([entry("Haus", FIXED, MARKET)]) == (
        "Haus",
        {"price_entity": "sensor.market"},
    )


def test_found() -> None:
    assert tarifwacht_sources([entry("Haus", FIXED, MARKET, SOLAR)]) == (
        "Haus",
        {"meter_entity": "sensor.feed_in", "price_entity": "sensor.market"},
    )


def test_exchange_price_of_section_51_first() -> None:
    solar = ("solar", {**SOLAR[1], "market_entity": "sensor.section_51"})
    found = tarifwacht_sources([entry("Haus", MARKET, solar)])
    assert found is not None
    assert found[1]["price_entity"] == "sensor.section_51"


def test_current_exchange_price_tariff_first() -> None:
    current = ("tariff", {**MARKET[1], "price_entity": "sensor.b", "current": True})
    found = tarifwacht_sources([entry("Haus", MARKET, current)])
    assert found == ("Haus", {"price_entity": "sensor.b"})


def test_entry_with_most_values() -> None:
    entries = [entry("Wohnung", MARKET), entry("Haus", MARKET, SOLAR)]
    found = tarifwacht_sources(entries)
    assert found is not None
    assert found[0] == "Haus"
