"""Einspeisewacht: PV feed-in remuneration under negative day-ahead prices."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import CALLBACK_TYPE, Event, HassJob, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .rename import renamed_data, renamed_unique_id, sources
from .runtime import PlantRuntime
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Renames come in bursts ("recreate entity IDs" of a device): the entries
# reload once, this long after the last one (as Wärmewacht and Speicherwacht).
RENAME_RELOAD_DELAY = timedelta(seconds=3)
# A reload picks up the renamed sources; a disabled or unloaded entry reads
# them at its next setup.
RELOAD_STATES = (
    ConfigEntryState.LOADED,
    ConfigEntryState.SETUP_IN_PROGRESS,
    ConfigEntryState.SETUP_RETRY,
    ConfigEntryState.SETUP_ERROR,
)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CALENDAR,
    Platform.SENSOR,
]

type EinspeisewachtConfigEntry = ConfigEntry[PlantRuntime]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions and follow renamed sources (once, for all entries)."""
    async_setup_services(hass)
    _async_follow_renames(hass)
    return True


@callback
def _async_follow_renames(hass: HomeAssistant) -> None:
    """Follow meter and price sensor renamed in the entity registry.

    Home Assistant's own helpers listen per entry (helper_integration.py).
    One listener for all entries also sees entries that are reloading or
    failed to set up, and an id renamed again before the reload. The entry
    data changes at once; the reload follows when the burst is over.
    Removed entities are left to the repair issues "meter_missing" and
    "price_missing".
    """
    waiting: set[str] = set()
    cancel: CALLBACK_TYPE | None = None

    @callback
    def _reload(_now: datetime) -> None:
        nonlocal cancel
        cancel = None
        for entry_id in sorted(waiting):
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry is not None and entry.state in RELOAD_STATES:
                hass.config_entries.async_schedule_reload(entry_id)
        waiting.clear()

    @callback
    def _is_rename(data: er.EventEntityRegistryUpdatedData) -> bool:
        return data["action"] == "update" and "old_entity_id" in data

    @callback
    def _on_rename(event: Event[er.EventEntityRegistryUpdatedData]) -> None:
        nonlocal cancel
        old: str = event.data["old_entity_id"]  # type: ignore[typeddict-item]
        new = event.data["entity_id"]
        for entry in hass.config_entries.async_entries(DOMAIN):
            used = sources(entry.data)
            if old not in used:
                continue
            if new in used:
                # Meter and price would become one entity: leave it to the user.
                _LOGGER.warning(
                    "%s: %s was renamed to %s, which is already a source; "
                    "please reconfigure",
                    entry.title,
                    old,
                    new,
                )
                continue
            changes: dict[str, Any] = {"data": renamed_data(entry.data, old, new)}
            unique_id = renamed_unique_id(entry.unique_id, old, new)
            if unique_id and not hass.config_entries.async_entry_for_domain_unique_id(
                DOMAIN, unique_id
            ):
                changes["unique_id"] = unique_id
            waiting.add(entry.entry_id)
            hass.config_entries.async_update_entry(entry, **changes)
            _LOGGER.info("%s: source %s renamed to %s", entry.title, old, new)
        if waiting:
            if cancel is not None:
                cancel()
            cancel = async_call_later(
                hass,
                RENAME_RELOAD_DELAY,
                HassJob(_reload, "einspeisewacht_renamed", cancel_on_shutdown=True),
            )

    hass.bus.async_listen(
        er.EVENT_ENTITY_REGISTRY_UPDATED, _on_rename, event_filter=_is_rename
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: EinspeisewachtConfigEntry
) -> bool:
    """Set up one plant and meter."""
    runtime = PlantRuntime(hass, entry.entry_id, entry.data)
    await runtime.async_start()
    entry.runtime_data = runtime

    async def _async_on_stop(event: Event) -> None:
        await runtime.async_stop()

    # Stop listening and write the bookings when Home Assistant shuts down.
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_on_stop)
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    runtime.start_backfill()
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: EinspeisewachtConfigEntry
) -> bool:
    """Unload; the runtime writes its state for the next setup."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_stop()
    return unloaded


async def async_remove_entry(
    hass: HomeAssistant, entry: EinspeisewachtConfigEntry
) -> None:
    """Delete the stored bookings."""
    await PlantRuntime(hass, entry.entry_id, entry.data).async_remove()
