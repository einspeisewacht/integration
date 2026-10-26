"""Home Assistant side of one plant: listens to meter and price, stores state."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta
from typing import Any

import aiohttp
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfEnergy,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
    async_track_utc_time_change,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    BERLIN,
    CONF_BACKFILL,
    CONF_COMMISSIONED,
    CONF_FEED_IN_TYPE,
    CONF_METER,
    CONF_NAME,
    CONF_OVERRIDE,
    CONF_OVERRIDE_DATE,
    CONF_POWER,
    CONF_PRICE,
    CONF_RATE_MODE,
    CONF_RATES,
    CONF_SMART_METER,
    CONF_SMART_METER_DATE,
    DOMAIN,
    FEED_IN_FULL,
    OVERRIDE_FROM_DATE,
    OVERRIDE_NEVER,
    RATE_TIERED,
    USER_AGENT,
)
from .engine import Engine
from .ledger import FeedInValuation
from .meter import MeterTracker, to_kwh
from .prices import ParsedPrices, parse_interval_prices
from .regime import Derived, Plant, derive, local_midnight, manual, rule_for
from .report import build_report
from .rules import NegativeQuarterHour
from .smard import INDEX_URL, parse_index, parse_week, week_url, weeks_covering
from .solar import daylight_weight
from .tariff import blended_rate
from .timeslots import slot_start

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
# The live state (meter, bookings) is small and written at most this often, and
# on unload. After a crash the next meter reading books what is missing.
LIVE_SAVE_INTERVAL = timedelta(minutes=10)
# Newly recorded negative quarter hours are written soon (they are rare).
NEGATIVES_SAVE_DELAY = 10
# A failed SMARD.de download is tried again this often (and at every start).
SMARD_RETRY_INTERVAL = timedelta(hours=24)
# Raise a repair issue once the running quarter hour has had no price this long.
PRICE_MISSING_ISSUE_AFTER = timedelta(hours=1)

# Price sensors without a forecast attribute: the state is the current price.
# Only its sign matters for the rule, so the unit is not converted.
FORECAST_ATTRIBUTE = "data"

# SMARD.de: one request per week of history; be gentle with the website.
SMARD_PAUSE = 0.5
SMARD_TIMEOUT = aiohttp.ClientTimeout(total=30)


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
    """Remuneration in ct/kWh: the single rate, or blended over capacity bands."""
    rates = [float(r) for r in config[CONF_RATES]]
    if config.get(CONF_RATE_MODE) != RATE_TIERED:
        return rates[0]
    return blended_rate(
        float(config[CONF_POWER]),
        rates,
        config.get(CONF_FEED_IN_TYPE) == FEED_IN_FULL,
    )


def parse_price_state(state: State, now: datetime | None = None) -> ParsedPrices | None:
    """Prices from a price sensor: forecast attribute, else the current state.

    Without a forecast the state is the price of the running quarter hour
    (`now`, else the moment it last changed). It is read again at every
    quarter hour, so a value held for an hour covers all four of them.
    """
    forecast = state.attributes.get(FORECAST_ATTRIBUTE)
    if isinstance(forecast, list) and forecast:
        return parse_interval_prices(forecast)
    try:
        price = float(state.state)
    except ValueError:
        return None
    return ParsedPrices(prices={slot_start(now or state.last_updated): price})


class PlantRuntime:
    """Feeds the engine and notifies entities."""

    def __init__(
        self, hass: HomeAssistant, entry_id: str, config: Mapping[str, Any]
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.name: str = config[CONF_NAME]
        self.meter_entity: str = config[CONF_METER]
        self.price_entity: str = config[CONF_PRICE]
        self.commissioned = date.fromisoformat(config[CONF_COMMISSIONED])
        self.backfill_enabled = bool(config.get(CONF_BACKFILL))
        self.derived = derived_from_config(config)
        self.rate_ct = rate_from_config(config)
        self.engine = Engine(
            meter=MeterTracker(max_power_kw=float(config[CONF_POWER])),
            valuation=FeedInValuation(
                rate=self.rate_ct / 100,
                rule=rule_for(self.derived),
                shadow_rule=NegativeQuarterHour(),
            ),
            since=local_midnight(self.commissioned),
            weight=daylight_weight(hass.config.latitude, hass.config.longitude),
        )
        self.unknown_unit: str | None = None
        self.backfill_error: str | None = None
        self.backfill_missing: int | None = None
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}"
        )
        self._history: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.history"
        )
        self._live_dirty = False
        self._saved_history = 0
        self._saved_negatives = 0
        self._price_missing_since: datetime | None = None
        self._backfill_running = False
        self._listeners: list[Callable[[], None]] = []
        self._unsubscribe: list[CALLBACK_TYPE] = []

    async def async_start(self) -> None:
        """Restore the stored state, read current values, start listening."""
        if live := await self._store.async_load():
            self.engine.restore(live, await self._history.async_load())
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
            async_track_time_interval(self.hass, self._async_save, LIVE_SAVE_INTERVAL),
            async_track_time_interval(
                self.hass, self._async_retry_backfill, SMARD_RETRY_INTERVAL
            ),
        ]

    async def async_stop(self) -> None:
        """Stop listening and write the state."""
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        self._unsubscribe = []
        await self._store.async_save(self.engine.as_live_dict())
        await self._history.async_save(self.engine.as_history_dict())

    async def async_remove(self) -> None:
        await self._store.async_remove()
        await self._history.async_remove()
        for issue in (
            self.issue_id,
            self._issue("price_missing"),
            self._issue("meter_unit"),
        ):
            ir.async_delete_issue(self.hass, DOMAIN, issue)

    def _issue(self, key: str) -> str:
        return f"{key}_{self.entry_id}"

    async def _async_save(self, now: datetime | None = None) -> None:
        """Write what changed: the live state, and the history if it changed."""
        if self._live_dirty:
            self._live_dirty = False
            await self._store.async_save(self.engine.as_live_dict())
        if self.engine.history_version != self._saved_history:
            self._saved_history = self.engine.history_version
            await self._history.async_save(self.engine.as_history_dict())

    async def _async_retry_backfill(self, now: datetime | None = None) -> None:
        await self.async_backfill()

    @property
    def issue_id(self) -> str:
        return f"smard_failed_{self.entry_id}"

    async def async_backfill(self) -> None:
        """Count quarter hours from commissioning until live counting began.

        Opt-in, once per commissioning date. Failures are reported as a repair issue and
        retried on the next start; they never affect live booking.
        """
        quarters = self.engine.quarters
        start = local_midnight(self.commissioned)
        if (
            not self.backfill_enabled
            or quarters.started is None
            or self._backfill_running
        ):
            return
        if quarters.backfilled and quarters.backfill_from == start:
            return  # done, for this commissioning date
        end = quarters.started
        self._backfill_running = True
        try:
            prices = await self._async_fetch_smard(start, end) if start < end else {}
        except (
            aiohttp.ClientError,
            TimeoutError,
            KeyError,
            TypeError,
            ValueError,
        ) as err:
            self._backfill_running = False
            self.backfill_error = f"{type(err).__name__}: {err}"
            _LOGGER.warning(
                "%s: SMARD.de backfill failed: %s", self.name, self.backfill_error
            )
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self.issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="smard_failed",
                translation_placeholders={
                    "name": self.name,
                    "error": self.backfill_error,
                },
            )
            return
        self._backfill_running = False
        self.backfill_error = None
        self.backfill_missing = self.engine.add_backfill(prices, start, end)
        ir.async_delete_issue(self.hass, DOMAIN, self.issue_id)
        self._changed()

    async def async_report(self, first_day: date, last_day: date) -> dict[str, Any]:
        """Sums for the local days `first_day` to `last_day` (inclusive).

        Raises ValueError if the period holds no complete hour since commissioning.
        """
        now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
        start = max(local_midnight(first_day), self.engine.since)
        end = min(local_midnight(last_day + timedelta(days=1)), now)
        if end <= start:
            raise ValueError("empty period")
        hourly = await self.async_hourly_energy(start, end)
        result = build_report(
            hourly,
            start,
            end,
            self.engine.quarters,
            self.engine.rule,
            self.rate_ct / 100,
            BERLIN,
        )
        return {
            "plant": self.name,
            "start": start.astimezone(BERLIN).isoformat(),
            "end": end.astimezone(BERLIN).isoformat(),
            "rule": self.derived.regime.value,
            "rate_ct_per_kwh": round(self.rate_ct, 4),
            **result,
        }

    async def async_hourly_energy(
        self, start: datetime, end: datetime
    ) -> list[tuple[datetime, float]]:
        """Energy per hour (kWh) of the meter from Home Assistant's long-term statistics."""
        rows = await get_instance(self.hass).async_add_executor_job(
            statistics_during_period,
            self.hass,
            start,
            end,
            {self.meter_entity},
            "hour",
            {"energy": UnitOfEnergy.KILO_WATT_HOUR},
            {"change"},
        )
        return [
            (dt_util.utc_from_timestamp(row["start"]), row["change"])
            for row in rows.get(self.meter_entity, [])
            if row.get("change") is not None
        ]

    async def _async_fetch_smard(
        self, start: datetime, end: datetime
    ) -> dict[datetime, float]:
        session = async_get_clientsession(self.hass)
        index = parse_index(await self._async_get_json(session, INDEX_URL))
        prices: dict[datetime, float] = {}
        for week in weeks_covering(index, start, end):
            prices.update(
                parse_week(await self._async_get_json(session, week_url(week)))
            )
            await asyncio.sleep(SMARD_PAUSE)
        return prices

    @staticmethod
    async def _async_get_json(session: aiohttp.ClientSession, url: str) -> Any:
        async with session.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=SMARD_TIMEOUT
        ) as response:
            response.raise_for_status()
            return await response.json(content_type=None)

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
        # A price sensor without forecast keeps its value into the new quarter hour.
        if state := self.hass.states.get(self.price_entity):
            self._handle_price(state, now)
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
        if (parsed := parse_price_state(state, now)) is not None:
            self.engine.on_prices(parsed, now)

    def _changed(self) -> None:
        self._live_dirty = True
        if self.engine.negatives_version != self._saved_negatives:
            self._saved_negatives = self.engine.negatives_version
            self._saved_history = self.engine.history_version
            self._history.async_delay_save(
                self.engine.as_history_dict, NEGATIVES_SAVE_DELAY
            )
        self._update_issues(dt_util.utcnow())
        for listener in list(self._listeners):
            listener()

    def _update_issues(self, now: datetime) -> None:
        """Never book wrongly in silence: say when prices or the meter unit are missing."""
        if self.engine.prices.get(slot_start(now)) is None:
            self._price_missing_since = self._price_missing_since or now
            if now - self._price_missing_since >= PRICE_MISSING_ISSUE_AFTER:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    self._issue("price_missing"),
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="price_missing",
                    translation_placeholders={
                        "name": self.name,
                        "entity": self.price_entity,
                    },
                )
        else:
            self._price_missing_since = None
            ir.async_delete_issue(self.hass, DOMAIN, self._issue("price_missing"))
        if self.unknown_unit is not None:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self._issue("meter_unit"),
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key="meter_unit",
                translation_placeholders={
                    "name": self.name,
                    "entity": self.meter_entity,
                    "unit": str(self.unknown_unit),
                },
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, self._issue("meter_unit"))
