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

    instance = get_instance(hass)
    start = max(local_midnight(first_day), runtime.engine.since)
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
    for entity_id in entity_ids.values():
        rows = existing.get(entity_id)
        if not rows:
            raise StatisticsImportError("no_statistics_yet")
        firsts[entity_id] = dt_util.utc_from_timestamp(rows[0]["start"])
    end = max(firsts.values())
    if end <= start:
        raise StatisticsImportError("nothing_to_import")
    if unknown := unknown_slots(start, end, runtime.engine.quarters):
        raise StatisticsImportError("prices_missing", {"count": str(len(unknown))})

    metadata = await instance.async_add_executor_job(
        lambda: get_metadata(hass, statistic_ids=set(entity_ids.values()))
    )
    rate = runtime.rate_ct / 100
    hourly = [
        (hour, *split_hour(hour, energy, runtime.engine.quarters, runtime.engine.rule))
        for hour, energy in await runtime.async_hourly_energy(start, end)
    ]
    values = {
        "energy_paid": lambda paid, unpaid: paid,
        "energy_unpaid": lambda paid, unpaid: unpaid,
        "revenue": lambda paid, unpaid: paid * rate,
        "revenue_lost": lambda paid, unpaid: unpaid * rate,
    }

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
        # Shift every later sum (short- and long-term) by what was added before.
        instance.async_adjust_statistics(
            entity_id, first, total, meta["unit_of_measurement"] or ""
        )
        result["sensors"][entity_id] = {
            "hours": len(rows),
            "added": round(total, 3),
            "until": (first - HOUR).isoformat(),
        }
    return result
