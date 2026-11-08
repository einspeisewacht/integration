"""Statistics of the total sensors: the history before setup, and the money
sensors recalculated with the current rate.

Import (action einspeisewacht.import_statistics): the four total sensors only
have long-term statistics since the integration was set up. This fills the
hours before that, computed like the report (hourly meter statistics against
the known negative quarter hours, implausible hours left out), and shifts the
existing sums by the imported total so the series stays continuous - the same
adjustment Home Assistant's own "fix statistics" uses. Only hours before each
sensor's first existing statistic are written, so a second call finds nothing
left to do and is refused.

Recalculation (button "Recalculate statistics", the action with `replace`):
revenue, lost revenue and the shadow value are energy times the current
rate. After a corrected rate their statistics of past hours still hold the
old one; this rewrites them from the energy sensors' statistics
(recalculate.py, docs/ENTWICKLUNG.md "Statistik neu berechnen").
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.db_schema import StatisticsShortTerm
from homeassistant.components.recorder.models import StatisticData
from homeassistant.components.recorder.statistics import (
    async_import_statistics,
    get_metadata,
    statistics_during_period,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from homeassistant.util.hass_dict import HassKey

from .const import BERLIN, DOMAIN
from .ledger import MONEY_TOTALS
from .recalculate import EnergyRowsMissing, MoneyPlan, Row, plan_money
from .regime import local_midnight
from .report import HOUR, implausible_summary, split_hour, unknown_slots

if TYPE_CHECKING:
    from . import EinspeisewachtConfigEntry

TOTAL_KEYS = ("energy_paid", "energy_unpaid", "revenue", "revenue_lost")

# One import or recalculation per entry at a time (kept across reloads).
LOCKS: HassKey[dict[str, asyncio.Lock]] = HassKey(f"{DOMAIN}_statistics_locks")
# Long-term statistics are read from here (before any sensor existed).
EPOCH = datetime(2000, 1, 1, tzinfo=UTC)
# Short-term rows are recalculated this far back: Home Assistant keeps them
# for 10 days by default. Older ones (with a longer `purge_keep_days`) stay
# as they are; only 5-minute graphs of that time show them.
SHORT_TERM_PERIOD = timedelta(days=10)


class StatisticsImportError(Exception):
    """Refused; `key` names the translated reason."""

    def __init__(self, key: str, placeholders: dict[str, str] | None = None) -> None:
        super().__init__(key)
        self.key = key
        self.placeholders = placeholders or {}


def _lock(hass: HomeAssistant, entry: EinspeisewachtConfigEntry) -> asyncio.Lock:
    return hass.data.setdefault(LOCKS, {}).setdefault(entry.entry_id, asyncio.Lock())


async def async_import_history(
    hass: HomeAssistant, entry: EinspeisewachtConfigEntry, first_day: date
) -> dict[str, Any]:
    """Import hourly statistics from `first_day` until each sensor's first one."""
    lock = _lock(hass, entry)
    if lock.locked():
        raise StatisticsImportError("busy")
    async with lock:
        return await _async_import_history(hass, entry, first_day)


async def _async_import_history(
    hass: HomeAssistant, entry: EinspeisewachtConfigEntry, first_day: date
) -> dict[str, Any]:
    runtime = entry.runtime_data
    registry = er.async_get(hass)
    entity_ids: dict[str, str] = {}
    for key in TOTAL_KEYS:
        entity_id = registry.async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_{key}"
        )
        if entity_id is None:
            raise StatisticsImportError("entities_missing")
        entity_ids[key] = entity_id

    started = runtime.engine.quarters.started
    if started is None:
        raise StatisticsImportError("no_statistics_yet")
    start = max(local_midnight(first_day), runtime.engine.since)
    # Before the setup the sensors have no statistics, so the imported sums can
    # start at 0; a later start could fall into a gap after existing rows.
    if start >= started:
        raise StatisticsImportError("start_after_setup")

    instance = get_instance(hass)
    existing = await instance.async_add_executor_job(
        statistics_during_period,
        hass,
        start,
        None,
        set(entity_ids.values()),
        "hour",
        None,
        {"sum"},
    )
    firsts: dict[str, datetime] = {}
    first_sums: dict[str, float] = {}
    for entity_id in entity_ids.values():
        rows = existing.get(entity_id)
        if not rows:
            raise StatisticsImportError("no_statistics_yet")
        firsts[entity_id] = dt_util.utc_from_timestamp(rows[0]["start"])
        first_sums[entity_id] = rows[0].get("sum") or 0.0
    end = max(firsts.values())
    if end <= start:
        raise StatisticsImportError("nothing_to_import")
    # The setup hour's quarter hours before the setup are checked too (see below).
    if unknown := unknown_slots(start, max(end, started), runtime.engine.quarters):
        raise StatisticsImportError("prices_missing", {"count": str(len(unknown))})

    metadata = await instance.async_add_executor_job(
        lambda: get_metadata(hass, statistic_ids=set(entity_ids.values()))
    )
    rate = runtime.rate_ct / 100
    quarters, rule = runtime.engine.quarters, runtime.engine.rule
    meter_hours, implausible = await runtime.async_hourly_energy(start, end + HOUR)
    meter = dict(meter_hours)
    hourly = [
        (hour, *split_hour(hour, energy, quarters, rule))
        for hour, energy in meter.items()
    ]
    values = {
        "energy_paid": lambda paid, unpaid: paid,
        "energy_unpaid": lambda paid, unpaid: unpaid,
        "revenue": lambda paid, unpaid: paid * rate,
        "revenue_lost": lambda paid, unpaid: unpaid * rate,
    }

    # The sensors' first statistics hour is the setup hour; its part before the
    # setup is in the meter's change of that hour but in no sensor: add it to
    # the shift (the meter's hour minus what the sensors booked in it).
    setup_hour = started.replace(minute=0)
    paid_id, unpaid_id = entity_ids["energy_paid"], entity_ids["energy_unpaid"]
    extra = (0.0, 0.0)
    if firsts[paid_id] == firsts[unpaid_id] == setup_hour < started:
        before = (
            meter.get(setup_hour, 0.0) - first_sums[paid_id] - first_sums[unpaid_id]
        )
        if before > 0:
            extra = split_hour(setup_hour, before, quarters, rule, until=started)

    result: dict[str, Any] = {"start": start.isoformat(), "sensors": {}}
    for key, entity_id in entity_ids.items():
        first = firsts[entity_id]
        rows: list[StatisticData] = []
        total = 0.0
        for hour, paid, unpaid in sorted(hourly):
            if not start <= hour < first:
                continue
            total += values[key](paid, unpaid)
            rows.append(StatisticData(start=hour, state=total, sum=total))
        if not rows:
            continue
        meta = metadata[entity_id][1]
        async_import_statistics(hass, meta, rows)
        shift = total + (values[key](*extra) if first == setup_hour else 0.0)
        # Shift every later sum (short- and long-term) by what was added before.
        instance.async_adjust_statistics(
            entity_id, first, shift, meta["unit_of_measurement"] or ""
        )
        result["sensors"][entity_id] = {
            "hours": len(rows),
            "added": round(shift, 3),
            "until": (first - HOUR).isoformat(),
        }
    # Left out of the meter's statistics (report.plausible_hours).
    if summary := implausible_summary(implausible, BERLIN):
        result["hours_implausible"] = summary
    return result


# Recalculation


def _money_targets(
    hass: HomeAssistant, entry: EinspeisewachtConfigEntry
) -> dict[str, str]:
    """Money sensor -> its energy sensor (entity ids), for those that exist."""
    registry = er.async_get(hass)
    targets: dict[str, str] = {}
    for money, energy in MONEY_TOTALS.items():
        money_id = registry.async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_{money}"
        )
        energy_id = registry.async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_{energy}"
        )
        if money_id and energy_id:
            targets[money_id] = energy_id
    return targets


def _read_rows(
    hass: HomeAssistant, ids: set[str], now: datetime
) -> tuple[dict[str, list[Row]], dict[str, list[Row]]]:
    """All hourly rows and the short-term rows of the last days."""

    def read(start: datetime, period: str) -> dict[str, list[Row]]:
        found = statistics_during_period(
            hass,
            start,
            None,
            ids,
            period,  # type: ignore[arg-type]
            {"energy": UnitOfEnergy.KILO_WATT_HOUR},
            {"state", "sum"},
        )
        return {
            statistic_id: [
                (dt_util.utc_from_timestamp(r["start"]), r.get("state"), r["sum"])
                for r in rows
                if r.get("sum") is not None
            ]
            for statistic_id, rows in found.items()
        }

    return read(EPOCH, "hour"), read(now - SHORT_TERM_PERIOD, "5minute")


async def async_recalculate(
    hass: HomeAssistant,
    entry: EinspeisewachtConfigEntry,
    first_day: date | None = None,
) -> dict[str, Any]:
    """Recalculate the statistics of the money sensors with the current rate,
    from each one's first row (or from `first_day`, filling the time before
    the setup first like the import) up to the latest compiled row."""
    lock = _lock(hass, entry)
    if lock.locked():
        raise StatisticsImportError("busy")
    async with lock:
        imported: dict[str, Any] | None = None
        runtime = entry.runtime_data
        started = runtime.engine.quarters.started
        if (
            first_day is not None
            and started is not None
            and max(local_midnight(first_day), runtime.engine.since) < started
        ):
            try:
                imported = await _async_import_history(hass, entry, first_day)
            except StatisticsImportError as err:
                if err.key != "nothing_to_import":
                    raise
        result = await _async_recalculate(hass, entry, first_day)
    if imported is not None:
        result["imported"] = imported
    return result


async def _async_recalculate(
    hass: HomeAssistant, entry: EinspeisewachtConfigEntry, first_day: date | None
) -> dict[str, Any]:
    runtime = entry.runtime_data
    targets = _money_targets(hass, entry)
    if not targets:
        raise StatisticsImportError("entities_missing")
    rate = runtime.rate_ct / 100
    start = None if first_day is None else local_midnight(first_day)
    instance = get_instance(hass)
    # Rows still in the recorder's queue or session are written first.
    await instance.async_block_till_done()
    ids = set(targets) | set(targets.values())
    hours, short = await instance.async_add_executor_job(
        _read_rows, hass, ids, dt_util.utcnow()
    )

    plans: dict[str, MoneyPlan] = {}
    skipped: list[str] = []
    with_rows = False
    for money_id, energy_id in sorted(targets.items()):
        try:
            plan = plan_money(
                hours.get(money_id, []),
                hours.get(energy_id, []),
                short.get(money_id, []),
                short.get(energy_id, []),
                rate,
                start,
            )
        except EnergyRowsMissing:
            skipped.append(money_id)
            continue
        if plan is None:
            continue  # no statistics: left alone
        with_rows = True
        if plan.hourly or plan.short:
            plans[money_id] = plan
    if not with_rows and not skipped:
        # Nothing was recorded with an earlier rate.
        runtime.statistics_recalculated()
        raise StatisticsImportError("no_statistics_yet")
    if not plans:
        raise StatisticsImportError(
            "energy_statistics_missing" if skipped else "nothing_to_recalculate"
        )

    metadata = await instance.async_add_executor_job(
        lambda: get_metadata(hass, statistic_ids=set(plans))
    )
    ends = [plan.until for plan in plans.values() if plan.until is not None]
    result: dict[str, Any] = {
        "start": min(p.start for p in plans.values()).astimezone(BERLIN).isoformat(),
        "end": max(ends).astimezone(BERLIN).isoformat() if ends else None,
        "rate_ct_per_kwh": round(runtime.rate_ct, 4),
        "sensors": {},
        "skipped": skipped,
    }
    from_first = not skipped
    for money_id, plan in plans.items():
        if money_id not in metadata:
            continue
        meta = metadata[money_id][1]
        if plan.hourly:
            async_import_statistics(hass, meta, _data(plan.hourly))
        if plan.short:
            instance.async_import_statistics(
                meta, _data(plan.short), StatisticsShortTerm
            )
        if plan.shift_from is not None and plan.shift:
            # Rows written after the latest one read continue from it.
            instance.async_adjust_statistics(
                money_id,
                plan.shift_from,
                plan.shift,
                meta["unit_of_measurement"] or "",
            )
        from_first &= plan.from_first
        result["sensors"][money_id] = _sensor_result(plan)
    # Written before the next press reads them.
    await instance.async_block_till_done()
    if from_first:
        runtime.statistics_recalculated()
    return result


def _data(rows: list[Row]) -> list[StatisticData]:
    return [
        StatisticData(start=moment, state=total if state is None else state, sum=total)
        for moment, state, total in rows
    ]


def _sensor_result(plan: MoneyPlan) -> Mapping[str, Any]:
    change = (
        None
        if plan.old_end is None or plan.new_end is None
        else round(plan.new_end - plan.old_end, 4)
    )
    return {
        "from": plan.start.astimezone(BERLIN).isoformat(),
        "until": plan.until.astimezone(BERLIN).isoformat() if plan.until else None,
        "hours": len(plan.hourly),
        "short_term": len(plan.short),
        "change": change,
    }
