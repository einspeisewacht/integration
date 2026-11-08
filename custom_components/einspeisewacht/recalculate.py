"""Money statistics recalculated with the current rate. Pure Python.

Revenue and lost revenue are energy times the rate (ledger.FeedInValuation):
a corrected rate gives the sensors new totals at once, but Home Assistant's
long-term statistics only see the change of the value, in the hour of the
correction; past hours, days and months keep the old rate.

The energy sensors' own statistics hold what was booked per hour (live, and
imported before the setup), so the money rows follow from them exactly:
sum = base + rate x (energy sum - energy base), state = rate x energy state.
From the sensor's first row on both bases are 0 (energy base: the energy
sum before that row, normally none).

How Home Assistant continues a sum (checked against HA 2026.10,
components/sensor/recorder.py `compile_statistics`): every 5 minutes it reads
the latest short-term row and adds the change of the sensor's value,
sum = last sum + (value now - last state). For a sensor without
`last_reset`, `sum - state` therefore stays the same from row to row, also
across a jump of the value (the reload with a new rate). The hourly row is a
copy of the hour's last short-term row.

So the hourly rows and the short-term rows up to the latest one are
rewritten, and rows the recorder writes after that latest one (in the
moment between reading and writing) are shifted by `shift`, chosen so their
`sum - state` matches the new rows: the next compile continues without a
jump and counts nothing twice.

Only rows whose value changes are written (`hourly_written`,
`short_written`): rows that already hold the target within ROW_TOLERANCE
stay, so a sensor whose values do not change (no energy, or a second press)
is not touched at all, and small hardware (an SD card) gets no needless
writes. The rate has no date of its own (it applies from the commissioning),
so every row from the first one is checked. Later rows are shifted only if
the latest short-term row is rewritten: otherwise the recorder continues
from that stored row as before.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

FIVE_MINUTES = timedelta(minutes=5)
HOUR = timedelta(hours=1)
# A recalculated row differing from the stored one by less (EUR, in state
# and in sum) is not written.
ROW_TOLERANCE = 0.0005

# (start, state, sum) as read from the statistics.
Row = tuple[datetime, float | None, float]


@dataclass
class MoneyPlan:
    """What a recalculation writes for one money sensor."""

    start: datetime
    hourly: list[Row] = field(default_factory=list)
    short: list[Row] = field(default_factory=list)
    # Rows from this moment on are shifted by `shift` (None: no short-term
    # rows, nothing for the recorder to continue from).
    shift_from: datetime | None = None
    shift: float = 0.0
    # The old and the new sum at the newest rewritten row.
    old_end: float | None = None
    new_end: float | None = None
    # The end of the rewritten rows.
    until: datetime | None = None
    # From the sensor's first row on (no old rows left before).
    from_first: bool = True
    # The rows of `hourly` and `short` whose values change: written.
    hourly_written: list[Row] = field(default_factory=list)
    short_written: list[Row] = field(default_factory=list)

    @property
    def rows_written(self) -> int:
        return len(self.hourly_written) + len(self.short_written)

    @property
    def shifted(self) -> bool:
        """Whether rows after the latest one read are shifted."""
        return self.shift_from is not None and abs(self.shift) > 1e-12


class EnergyRowsMissing(Exception):
    """A money row has no energy row at the same start: left alone."""


def _before(rows: Sequence[Row], moment: datetime) -> float:
    """The sum of the last row before `moment` (0 without one)."""
    total = 0.0
    for start, _state, value in rows:
        if start >= moment:
            break
        total = value
    return total


def _differs(new: Row, old: Row) -> bool:
    """Whether a recalculated row differs from the stored one (a row
    without state is written with its sum as state)."""
    _, state, total = new
    _, old_state, old_total = old
    if old_state is None:
        return True
    written = total if state is None else state
    return (
        abs(written - old_state) > ROW_TOLERANCE
        or abs(total - old_total) > ROW_TOLERANCE
    )


def plan_money(
    money_hours: Sequence[Row],
    energy_hours: Sequence[Row],
    money_short: Sequence[Row],
    energy_short: Sequence[Row],
    rate: float,
    start: datetime | None = None,
) -> MoneyPlan | None:
    """The rows of a money sensor from its first row (or from `start`, a
    whole hour) on, from the rows of its energy sensor at `rate` (EUR/kWh).

    None: the sensor has no statistics; no rows in the plan: nothing from
    `start` on. Raises EnergyRowsMissing if an hourly money row has no
    energy row (statistics of one of them removed).
    """
    if not money_hours:
        return None
    first = money_hours[0][0]
    from_first = start is None or start <= first
    begin = first if from_first or start is None else start
    base_money = 0.0 if from_first else _before(money_hours, begin)
    base_energy = _before(energy_hours, begin)

    def money(state: float | None, total: float) -> tuple[float | None, float]:
        return (
            None if state is None else rate * state,
            base_money + rate * (total - base_energy),
        )

    plan = MoneyPlan(start=begin, from_first=from_first)
    energy = {row[0]: row for row in energy_hours}
    for stored in money_hours:
        moment, _state, old = stored
        if moment < begin:
            continue
        if moment not in energy:
            raise EnergyRowsMissing(moment)
        state, total = money(energy[moment][1], energy[moment][2])
        plan.hourly.append((moment, state, total))
        if _differs(plan.hourly[-1], stored):
            plan.hourly_written.append(plan.hourly[-1])
        plan.old_end, plan.new_end, plan.until = old, total, moment + HOUR

    energy_5 = {row[0]: row for row in energy_short}
    latest: tuple[Row, Row] | None = None
    for row in money_short:
        moment = row[0]
        if moment < begin or moment not in energy_5:
            continue
        state, total = money(energy_5[moment][1], energy_5[moment][2])
        plan.short.append((moment, state, total))
        if _differs(plan.short[-1], row):
            plan.short_written.append(plan.short[-1])
        latest = (row, energy_5[moment])
    if latest is not None:
        (moment, old_state, old_sum), (_, energy_state, energy_sum) = latest
        plan.shift_from = moment + FIVE_MINUTES
        plan.old_end, plan.new_end = old_sum, plan.short[-1][2]
        plan.until = moment + FIVE_MINUTES
        rewritten = bool(plan.short_written) and plan.short_written[-1][0] == moment
        if rewritten and old_state is not None and energy_state is not None:
            # Later rows: sum = state + old offset; wanted: the new offset.
            new_offset = base_money + rate * (energy_sum - energy_state - base_energy)
            plan.shift = new_offset - (old_sum - old_state)
    return plan
