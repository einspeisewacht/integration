"""Report for any period: hourly meter statistics against negative quarter hours.

Home Assistant keeps the meter's energy per hour (long-term statistics). Each
hour is spread evenly over its four quarter hours, which is exact whenever all
four have the same outcome and an estimate otherwise. Quarter hours whose price
was never seen count as remunerated and are listed as gaps.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any

from .quarters import QuarterCounter
from .rules import Rule
from .timeslots import QUARTER

HOUR = timedelta(hours=1)


@dataclass
class _Sums:
    energy_paid: float = 0.0
    energy_unpaid: float = 0.0
    negative_quarter_hours: int = 0

    def as_dict(self, rate: float) -> dict[str, Any]:
        return {
            "energy_paid_kwh": round(self.energy_paid, 3),
            "energy_unpaid_kwh": round(self.energy_unpaid, 3),
            "revenue_eur": round(self.energy_paid * rate, 2),
            "revenue_lost_eur": round(self.energy_unpaid * rate, 2),
            "negative_quarter_hours": self.negative_quarter_hours,
        }


def _ranges(slots: list[datetime]) -> list[tuple[datetime, datetime]]:
    ranges: list[tuple[datetime, datetime]] = []
    for slot in sorted(slots):
        if ranges and ranges[-1][1] == slot:
            ranges[-1] = (ranges[-1][0], slot + QUARTER)
        else:
            ranges.append((slot, slot + QUARTER))
    return ranges


def build_report(
    hourly: Iterable[tuple[datetime, float]],
    start: datetime,
    end: datetime,
    counter: QuarterCounter,
    rule: Rule,
    rate: float,
    tz: tzinfo,
) -> dict[str, Any]:
    """Sums for [start, end): hourly energy in kWh, rate in EUR/kWh."""
    # Step in UTC: adding 15 minutes to a local time would skip the repeated
    # hour at the end of daylight saving time.
    start, end = start.astimezone(UTC), end.astimezone(UTC)
    total = _Sums()
    months: dict[str, _Sums] = {}

    def month(slot: datetime) -> _Sums:
        return months.setdefault(slot.astimezone(tz).strftime("%Y-%m"), _Sums())

    hours_with_energy: set[datetime] = set()
    for hour, energy in hourly:
        if not start <= hour < end:
            continue
        hours_with_energy.add(hour)
        for i in range(4):
            slot = hour + i * QUARTER
            share = energy / 4
            price = counter.negatives.get(slot)
            unpaid = price is not None and not rule.is_paid(slot, price)
            for sums in (total, month(slot)):
                if unpaid:
                    sums.energy_unpaid += share
                else:
                    sums.energy_paid += share

    for slot, price in counter.negatives.items():
        if start <= slot < end and not rule.is_paid(slot, price):
            total.negative_quarter_hours += 1
            month(slot).negative_quarter_hours += 1

    unknown: list[datetime] = []
    missing_hours = 0
    slot = start
    while slot < end:
        if not counter.known(slot):
            unknown.append(slot)
        if slot.minute == 0 and slot not in hours_with_energy:
            missing_hours += 1
        slot += QUARTER

    return {
        **total.as_dict(rate),
        "months": [{"month": m, **s.as_dict(rate)} for m, s in sorted(months.items())],
        "gaps": {
            "quarter_hours_without_price": len(unknown),
            "price_ranges": [
                {
                    "start": a.astimezone(tz).isoformat(),
                    "end": b.astimezone(tz).isoformat(),
                }
                for a, b in _ranges(unknown)
            ],
            "hours_without_energy": missing_hours,
        },
    }
