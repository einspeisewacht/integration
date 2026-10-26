"""Einspeisewacht: PV feed-in remuneration under negative day-ahead prices."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .runtime import PlantRuntime
from .services import async_setup_services

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CALENDAR,
    Platform.SENSOR,
]

type EinspeisewachtConfigEntry = ConfigEntry[PlantRuntime]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions."""
    async_setup_services(hass)
    return True


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
    # Opt-in history from SMARD.de; never delays setup.
    entry.async_create_background_task(
        hass, runtime.async_backfill(), f"einspeisewacht backfill {entry.entry_id}"
    )
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
