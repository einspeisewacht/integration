"""Calendar: time windows with negative prices, merged from quarter hours.

Shows today and tomorrow once the day-ahead forecast is out, and the stored
past (about two weeks). Windows the rule does not (yet) apply to are titled
as still remunerated.
"""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import EinspeisewachtConfigEntry
from .entity import PlantEntity
from .windows import Window, negative_windows

# Event texts are not part of the entity translations; German or English by
# the instance language.
TEXTS = {
    "de": {
        "unpaid": "Keine Einspeisevergütung",
        "paid": "Negativer Preis (noch vergütet)",
        "lowest": "Niedrigster Day-Ahead-Preis: {price} ct/kWh",
    },
    "en": {
        "unpaid": "No feed-in remuneration",
        "paid": "Negative price (still remunerated)",
        "lowest": "Lowest day-ahead price: {price} ct/kWh",
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EinspeisewachtConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([NegativePriceCalendar(entry, "unpaid_windows")])


class NegativePriceCalendar(PlantEntity, CalendarEntity):
    """Windows without remuneration (or with negative prices not yet costing any)."""

    def _windows(self) -> list[Window]:
        engine = self.runtime.engine
        return negative_windows(engine.prices.prices, engine.rule)

    def _event(self, window: Window) -> CalendarEvent:
        language = "de" if self.hass.config.language.startswith("de") else "en"
        texts = TEXTS[language]
        price = f"{window.lowest_price * 100:.3f}".rstrip("0").rstrip(".")
        if language == "de":
            price = price.replace(".", ",")
        return CalendarEvent(
            start=dt_util.as_local(window.start),
            end=dt_util.as_local(window.end),
            summary=texts["paid" if window.paid else "unpaid"],
            description=texts["lowest"].format(price=price),
        )

    @property
    def event(self) -> CalendarEvent | None:
        """The running or next window."""
        now = dt_util.utcnow()
        for window in self._windows():
            if window.end > now:
                return self._event(window)
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [
            self._event(w)
            for w in self._windows()
            if w.end > start_date and w.start < end_date
        ]
