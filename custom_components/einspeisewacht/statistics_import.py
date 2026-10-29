"""Action einspeisewacht.import_statistics: the total sensors' history before setup.

The four total sensors only have long-term statistics since the integration
was set up. This fills the hours before that, computed like the report (hourly
meter statistics against the known negative quarter hours), and shifts the
existing sums by the imported total so the series stays continuous - the same
adjustment Home Assistant's own "fix statistics" uses.

Only hours before each sensor's first existing statistic are written, so a
second call finds nothing left to do and is refused.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData
from homeassistant.components.recorder.statistics import (
    async_import_statistics,
    get_metadata,
    statistics_during_period,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .regime import local_midnight
from .report import HOUR, split_hour, unknown_slots

if TYPE_CHECKING:
    from . import EinspeisewachtConfigEntry

TOTAL_KEYS = ("energy_paid", "energy_unpaid", "revenue", "revenue_lost")


class StatisticsImportError(Exception):
    """Refused; `key` names the translated reason."""

    def __init__(self, key: str, placeholders: dict[str, str] | None = None) -> None:
        super().__init__(key)
        self.key = key
        self.placeholders = placeholders or {}


async def async_import_history(
    hass: HomeAssistant, entry: EinspeisewachtConfigEntry, first_day: date
) -> dict[str, Any]:
    """Import hourly statistics from `first_day` until each sensor's first one."""
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
    meter = dict(await runtime.async_hourly_energy(start, end + HOUR))
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
    return result
