"""Home Assistant side of one plant: listens to meter and price, stores state."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from datetime import date, datetime
from typing import Any

from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_utc_time_change,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_COMMISSIONED,
    CONF_FEED_IN_TYPE,
    CONF_METER,
    CONF_OVERRIDE,
    CONF_OVERRIDE_DATE,
    CONF_POWER,
    CONF_PRICE,
    CONF_RATES,
    CONF_SMART_METER,
    CONF_SMART_METER_DATE,
    DOMAIN,
    FEED_IN_FULL,
    OVERRIDE_FROM_DATE,
    OVERRIDE_NEVER,
)
from .engine import Engine
from .ledger import FeedInValuation
from .meter import MeterTracker, to_kwh
from .prices import ParsedPrices, parse_interval_prices
from .regime import Derived, Plant, derive, manual, rule_for
from .rules import NegativeQuarterHour
from .tariff import blended_rate
from .timeslots import slot_start

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
# Bookings are written at most this often (and on unload).
SAVE_DELAY = 60

# Price sensors without a forecast attribute: the state is the current price.
# Only its sign matters for the rule, so the unit is not converted.
FORECAST_ATTRIBUTE = "data"


def plant_from_config(config: Mapping[str, Any]) -> Plant:
    smart_meter = config.get(CONF_SMART_METER) and config.get(CONF_SMART_METER_DATE)
    return Plant(
        commissioned=date.fromisoformat(config[CONF_COMMISSIONED]),
        power_kw=float(config[CONF_POWER]),
        smart_meter_installed=date.fromisoformat(smart_meter) if smart_meter else None,
    )


def derived_from_config(config: Mapping[str, Any]) -> Derived:
    """The derived regime, or the manual override."""
    override = config.get(CONF_OVERRIDE)
    if override == OVERRIDE_NEVER:
        return manual(None)
    if override == OVERRIDE_FROM_DATE and config.get(CONF_OVERRIDE_DATE):
        return manual(date.fromisoformat(config[CONF_OVERRIDE_DATE]))
    return derive(plant_from_config(config))


def rate_from_config(config: Mapping[str, Any]) -> float:
    """Remuneration in ct/kWh (blended over capacity bands)."""
    return blended_rate(
        float(config[CONF_POWER]),
        [float(r) for r in config[CONF_RATES]],
        config.get(CONF_FEED_IN_TYPE) == FEED_IN_FULL,
    )


def parse_price_state(state: State) -> ParsedPrices | None:
    """Prices from a price sensor: forecast attribute, else the current state."""
    forecast = state.attributes.get(FORECAST_ATTRIBUTE)
    if isinstance(forecast, list) and forecast:
        return parse_interval_prices(forecast)
    try:
        price = float(state.state)
    except ValueError:
        return None
    return ParsedPrices(prices={slot_start(state.last_updated): price})


class PlantRuntime:
    """Feeds the engine and notifies entities."""

    def __init__(
        self, hass: HomeAssistant, entry_id: str, config: Mapping[str, Any]
    ) -> None:
        self.hass = hass
        self.meter_entity: str = config[CONF_METER]
        self.price_entity: str = config[CONF_PRICE]
        self.derived = derived_from_config(config)
        self.rate_ct = rate_from_config(config)
        self.engine = Engine(
            meter=MeterTracker(max_power_kw=float(config[CONF_POWER])),
            valuation=FeedInValuation(
                rate=self.rate_ct / 100,
                rule=rule_for(self.derived),
                shadow_rule=NegativeQuarterHour(),
            ),
        )
        self.unknown_unit: str | None = None
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}"
        )
        self._listeners: list[Callable[[], None]] = []
        self._unsubscribe: list[CALLBACK_TYPE] = []

    async def async_start(self) -> None:
        """Restore the stored state, read current values, start listening."""
        if data := await self._store.async_load():
            self.engine.restore(data)
        now = dt_util.utcnow()
        if state := self.hass.states.get(self.price_entity):
            self._handle_price(state, now)
        if state := self.hass.states.get(self.meter_entity):
            self._handle_meter(state, now)
        self.engine.tick(now)
        self._unsubscribe = [
            async_track_state_change_event(
                self.hass, [self.meter_entity, self.price_entity], self._on_state_change
            ),
            async_track_utc_time_change(
                self.hass, self._on_tick, minute=[0, 15, 30, 45], second=1
            ),
        ]

    async def async_stop(self) -> None:
        """Stop listening and write the state."""
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        self._unsubscribe = []
        await self._store.async_save(self.engine.as_dict())

    async def async_remove(self) -> None:
        await self._store.async_remove()

    @callback
    def add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    @callback
    def _on_state_change(self, event: Event[EventStateChangedData]) -> None:
        state = event.data["new_state"]
        if state is None:
            return
        now = dt_util.utcnow()
        if state.entity_id == self.meter_entity:
            self._handle_meter(state, now)
        else:
            self._handle_price(state, now)
        self._changed()

    @callback
    def _on_tick(self, now: datetime) -> None:
        self.engine.tick(now)
        self._changed()

    def _handle_meter(self, state: State, now: datetime) -> None:
        if state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        try:
            value = to_kwh(float(state.state), unit)
        except KeyError:
            if self.unknown_unit != unit:
                _LOGGER.warning("%s: unsupported unit %s", self.meter_entity, unit)
            self.unknown_unit = unit
            return
        except ValueError:
            return
        self.unknown_unit = None
        update = self.engine.on_meter(value, state.last_updated, now)
        if update.event is not None:
            _LOGGER.debug(
                "%s: %s (delta %s kWh)", self.meter_entity, update.event, update.delta
            )

    def _handle_price(self, state: State, now: datetime) -> None:
        if state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return
        if (parsed := parse_price_state(state)) is not None:
            self.engine.on_prices(parsed, now)

    def _changed(self) -> None:
        self._store.async_delay_save(self.engine.as_dict, SAVE_DELAY)
        for listener in list(self._listeners):
            listener()
