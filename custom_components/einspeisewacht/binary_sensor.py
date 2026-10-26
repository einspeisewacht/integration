"""Binary sensor: is feed-in remunerated in the current quarter hour?"""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import EinspeisewachtConfigEntry
from .entity import PlantEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EinspeisewachtConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([RemuneratedSensor(entry, "remunerated")])


class RemuneratedSensor(PlantEntity, BinarySensorEntity):
    """On while the current quarter hour is remunerated; unknown without a price."""

    @property
    def is_on(self) -> bool | None:
        return self.runtime.engine.paid_now(dt_util.utcnow())
