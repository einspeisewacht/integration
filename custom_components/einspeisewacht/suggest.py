"""Suggested sources for the setup form, besides those from Tarifwacht.

Nothing new to fill in: the feed-in meter comes from the grid export of the
energy dashboard, the price sensor from EPEX Spot's market price (never its
total price: § 51 EEG looks at the exchange price alone). A suggestion is
only a preset: the fields still take any sensor, and the usual checks run
when the form is sent.

Derived from tarifwacht/custom_components/tarifwacht/suggest.py (as of
4e94166), adapted: grid export (`stat_energy_to`) instead of the import, only
EPEX Spot's market price, no price of another tariff or of the Einspeisewacht.
A bug there may be here too; tools/check_shared.py in the parent folder
reports changes to the original.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

_LOGGER = logging.getLogger(__name__)

EPEX_SPOT = "epex_spot"
# EPEX Spot's unique ids are f"{source} {key}" (mampfes/ha_epex_spot 4.1.0,
# commit 2aad1eb: __init__.py L275; key in sensor.py L54).
EPEX_MARKET_KEY = "MarketPrice"


def grid_export_stats(prefs: Mapping[str, Any] | None) -> list[str]:
    """Statistic ids of the grid export in the energy dashboard's preferences.

    One grid source per connection with `stat_energy_to`; the older format
    with a `flow_to` list is migrated by Home Assistant when it loads the
    preferences (2026.3 and later) and only read to be safe.
    """
    found: list[str] = []
    for source in (prefs or {}).get("energy_sources") or []:
        if source.get("type") != "grid":
            continue
        if "flow_to" in source:
            stats = [flow.get("stat_energy_to") for flow in source["flow_to"] or []]
        else:
            stats = [source.get("stat_energy_to")]
        for stat in stats:
            if stat and stat not in found:
                found.append(stat)
    return found


def epex_market_sensor(entries: Iterable[er.RegistryEntry]) -> str | None:
    """EPEX Spot's market price sensor; with several EPEX Spot entries the
    first by entity id."""
    matches = sorted(
        entry.entity_id
        for entry in entries
        if entry.platform == EPEX_SPOT
        and entry.domain == "sensor"
        and entry.disabled_by is None
        and entry.unique_id.endswith(f" {EPEX_MARKET_KEY}")
    )
    return matches[0] if matches else None


def suggested_price(hass: HomeAssistant) -> str | None:
    """EPEX Spot's market price sensor, if it is set up."""
    return epex_market_sensor(er.async_get(hass).entities.values())


async def async_suggested_meter(hass: HomeAssistant, in_use: set[str]) -> str | None:
    """The grid export meter of the energy dashboard, if it is a sensor that
    no Einspeisewacht entry reads yet."""
    if "energy" not in hass.config.components:
        return None
    try:
        # Imported here: without the energy dashboard nothing is suggested,
        # and a change to its internals only loses the suggestion.
        from homeassistant.components.energy.data import async_get_manager

        manager = await async_get_manager(hass)
        stats = grid_export_stats(manager.data)
    except Exception as err:  # a suggestion must never block the setup
        _LOGGER.debug("No meter suggestion from the energy dashboard: %s", err)
        return None
    for stat in stats:
        if (
            stat.startswith("sensor.")
            and stat not in in_use
            and hass.states.get(stat) is not None
        ):
            return stat
    return None
