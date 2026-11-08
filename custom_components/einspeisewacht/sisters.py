"""Suggestions from sister integrations, so that a sensor is entered once.

Read from their config entries when a form is shown and copied once as a
suggested value; no dependency at runtime. Pure Python, no Home Assistant
imports: the entries are duck-typed (title, subentries with subentry_type
and data).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .const import CONF_METER, CONF_PRICE

TARIFWACHT = "tarifwacht"
# Link of the tip (hassfest refuses URLs in translations).
TARIFWACHT_URL = "https://github.com/tarifwacht/integration"
# Tarifwacht's data (tarifwacht/const.py): the subentry "PV and battery"
# with the feed-in meter and the exchange price for § 51, and the tariffs;
# a tariff "exchange price plus surcharges" reads the raw day-ahead price
# (EUR/kWh), a dynamic total price would include surcharges and VAT.
_SOLAR = "solar"
_FEED_IN = "feed_in_entity"
_MARKET = "market_entity"
_TARIFF = "tariff"
_KIND = "kind"
_KIND_MARKET = "dynamic_market"
_PRICE = "price_entity"
_CURRENT = "current"


def _entity(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    return value if isinstance(value, str) and value else None


def _sources(entry: Any) -> dict[str, str]:
    """Feed-in meter and exchange price sensor of one Tarifwacht entry."""
    subentries = list(entry.subentries.values())
    solar = next((s.data for s in subentries if s.subentry_type == _SOLAR), {})
    found: dict[str, str] = {}
    if meter := _entity(solar, _FEED_IN):
        found[CONF_METER] = meter
    # The exchange price of § 51 in "PV and battery", else that of a tariff
    # built from the exchange price, the current tariff first.
    markets = sorted(
        (
            s.data
            for s in subentries
            if s.subentry_type == _TARIFF and s.data.get(_KIND) == _KIND_MARKET
        ),
        key=lambda data: not data.get(_CURRENT),
    )
    prices = [_entity(solar, _MARKET), *(_entity(d, _PRICE) for d in markets)]
    if price := next((p for p in prices if p), None):
        found[CONF_PRICE] = price
    return found


def tarifwacht_sources(entries: Iterable[Any]) -> tuple[str, dict[str, str]] | None:
    """(entry title, {CONF_METER/CONF_PRICE: entity}) of the Tarifwacht entry
    that offers the most of the two, the first on a tie; None without any."""
    best: tuple[str, dict[str, str]] | None = None
    for entry in entries:
        found = _sources(entry)
        if found and (best is None or len(found) > len(best[1])):
            best = (entry.title, found)
    return best
