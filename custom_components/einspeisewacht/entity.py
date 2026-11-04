"""Base entity: one device per plant (config entry), updated by the runtime."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, VERSION

if TYPE_CHECKING:
    from . import EinspeisewachtConfigEntry
    from .runtime import PlantRuntime


def own_entities(hass: HomeAssistant, entity_ids: Iterable[str]) -> list[str]:
    """Those of Einspeisewacht itself: an entry reading one would read its own
    results or another plant's (seen 2026-11 in Wärmewacht: an entry's own
    sensor mapped as its source). The form refuses them; older entries do not
    read them and show a repair issue."""
    registry = er.async_get(hass)
    return sorted(
        entity_id
        for entity_id in set(entity_ids)
        if (entry := registry.async_get(entity_id)) is not None
        and entry.platform == DOMAIN
    )


class PlantEntity(Entity):
    """An entity of the plant device."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: EinspeisewachtConfigEntry, key: str) -> None:
        self.runtime: PlantRuntime = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Einspeisewacht",
            sw_version=VERSION,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.runtime.add_listener(self.async_write_ha_state))
