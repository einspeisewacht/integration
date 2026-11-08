"""Money statistics recalculated from the energy sensors' rows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.einspeisewacht.recalculate import (
    HOUR,
    ROW_TOLERANCE,
    EnergyRowsMissing,
    plan_money,
)

H0 = datetime(2026, 10, 25, 0, tzinfo=UTC)
OLD, NEW = 0.08, 0.10


def at(hours: int, minutes: int = 0) -> datetime:
    return H0 + hours * HOUR + timedelta(minutes=minutes)


# Energy sensor: two imported hours (state = sum), then live with
# sum - state = 2 (the imported total).
ENERGY_HOURS = [
    (at(0), 1.0, 1.0),
    (at(1), 2.0, 2.0),
    (at(2), 0.5, 2.5),
    (at(3), 1.5, 3.5),
]
ENERGY_SHORT = [(at(4, 0), 1.5, 3.5), (at(4, 5), 1.7, 3.7)]
# Revenue at the old rate; at 04:02 the rate became 0.10: the value jumped
# from 0.12 to 0.15, Home Assistant added that to the sum (sum - state stays).
MONEY_HOURS = [
    (at(0), 0.08, 0.08),
    (at(1), 0.16, 0.16),
    (at(2), 0.04, 0.20),
    (at(3), 0.12, 0.28),
]
MONEY_SHORT = [(at(4, 0), 0.12, 0.28), (at(4, 5), 0.17, 0.33)]


def plan(**changes):
    args = {
        "money_hours": MONEY_HOURS,
        "energy_hours": ENERGY_HOURS,
        "money_short": MONEY_SHORT,
        "energy_short": ENERGY_SHORT,
        "rate": NEW,
        "start": None,
        **changes,
    }
    return plan_money(**args)


def test_rows_follow_the_energy_rows_at_the_new_rate() -> None:
    result = plan()
    assert result is not None
    assert result.from_first
    assert result.start == at(0)
    assert [(t, pytest.approx(s), pytest.approx(v)) for t, s, v in result.hourly] == [
        (at(0), 0.1, 0.1),
        (at(1), 0.2, 0.2),
        (at(2), 0.05, 0.25),
        (at(3), 0.15, 0.35),
    ]
    assert result.short == [
        (at(4, 0), pytest.approx(0.15), pytest.approx(0.35)),
        (at(4, 5), pytest.approx(0.17), pytest.approx(0.37)),
    ]
    assert result.until == at(4, 10)
    assert result.new_end - result.old_end == pytest.approx(0.04)
    # A row the recorder wrote after the latest one read (old continuation,
    # value 0.19 at 1.9 kWh) lands on rate x energy sum once shifted.
    assert result.shift_from == at(4, 10)
    assert 0.33 + (0.19 - 0.17) + result.shift == pytest.approx(NEW * 3.9)


def test_recalculating_again_changes_nothing() -> None:
    first = plan()
    assert first is not None
    again = plan(money_hours=first.hourly, money_short=first.short)
    assert again is not None
    assert again.hourly == first.hourly
    assert again.short == first.short
    assert again.shift == pytest.approx(0.0)
    # Nothing to write, nothing to shift.
    assert first.rows_written == 6
    assert (again.hourly_written, again.short_written) == ([], [])
    assert again.rows_written == 0
    assert not again.shifted


def test_only_changed_rows_are_written() -> None:
    """Rows within the tolerance stay; without energy nothing changes."""
    first = plan()
    assert first is not None
    nudged = [(t, s, v + ROW_TOLERANCE / 2) for t, s, v in first.hourly]
    nudged[2] = (at(2), 0.05, 0.25 + 3 * ROW_TOLERANCE)
    again = plan(money_hours=nudged, money_short=first.short)
    assert again is not None
    assert [row[0] for row in again.hourly_written] == [at(2)]
    assert again.short_written == []

    # A sensor without energy (lost revenue, all paid): 0 at any rate.
    zero_energy = [(t, 0.0, 0.0) for t, _, _ in ENERGY_HOURS]
    zero_short = [(t, 0.0, 0.0) for t, _, _ in ENERGY_SHORT]
    idle = plan(
        money_hours=zero_energy,
        energy_hours=zero_energy,
        money_short=zero_short,
        energy_short=zero_short,
    )
    assert idle is not None
    assert len(idle.hourly) == 4
    assert idle.rows_written == 0
    assert not idle.shifted


def test_latest_row_kept_nothing_shifted() -> None:
    """The latest short-term row already right: the recorder continues from
    it as stored, later rows are not shifted."""
    first = plan()
    assert first is not None
    short = [MONEY_SHORT[0], first.short[1]]
    again = plan(money_hours=first.hourly, money_short=short)
    assert again is not None
    assert [row[0] for row in again.short_written] == [at(4, 0)]
    assert not again.shifted


def test_from_a_day_on_the_rows_before_stay() -> None:
    """From 02:00 on: continues from the old sum of 01:00 (0.16)."""
    result = plan(start=at(2))
    assert result is not None
    assert not result.from_first
    assert [(t, pytest.approx(v)) for t, _, v in result.hourly] == [
        (at(2), 0.21),
        (at(3), 0.31),
    ]
    assert result.short[-1][2] == pytest.approx(0.33)
    # sum - state stays 0.16 for the rows after: nothing to shift.
    assert result.shift == pytest.approx(0.0)


def test_without_statistics_or_energy_rows() -> None:
    assert plan(money_hours=[]) is None
    with pytest.raises(EnergyRowsMissing):
        plan(energy_hours=ENERGY_HOURS[1:])
    # After the last row: nothing to rewrite.
    later = plan(start=at(6))
    assert later is not None
    assert not later.hourly
    assert not later.short


def test_without_short_term_rows_nothing_is_shifted() -> None:
    result = plan(money_short=[], energy_short=[])
    assert result is not None
    assert result.shift_from is None
    assert result.until == at(4)
    assert result.short == []
