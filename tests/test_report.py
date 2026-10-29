"""Report from hourly statistics and the negative quarter hours."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.einspeisewacht.const import BERLIN
from custom_components.einspeisewacht.quarters import QuarterCounter
from custom_components.einspeisewacht.report import HOUR, build_report, split_hour
from custom_components.einspeisewacht.rules import AlwaysPaid, NegativeQuarterHour
from custom_components.einspeisewacht.smard import parse_week
from tests.conftest import load_fixture

DAY_START = datetime(2026, 10, 24, 22, tzinfo=UTC)  # 25.10.2026 00:00 local
DAY_END = datetime(2026, 10, 25, 23, tzinfo=UTC)  # 25 hours (DST)
RATE = 0.0794


def counter(known_from: datetime = DAY_START) -> QuarterCounter:
    result = QuarterCounter(started=DAY_END, next_slot=DAY_END)
    result.add_backfill(
        parse_week(load_fixture("smard_week_2026-10-19.json")), known_from, DAY_END
    )
    return result


def hours(
    start: datetime, end: datetime, kwh: float = 1.0
) -> list[tuple[datetime, float]]:
    result = []
    while start < end:
        result.append((start, kwh))
        start += HOUR
    return result


def test_report_of_dst_day() -> None:
    report = build_report(
        hours(DAY_START, DAY_END),
        DAY_START,
        DAY_END,
        counter(),
        NegativeQuarterHour(),
        RATE,
        BERLIN,
    )
    assert report["energy_unpaid_kwh"] == pytest.approx(
        1.5
    )  # 6 quarter hours x 0.25 kWh
    assert report["energy_paid_kwh"] == pytest.approx(23.5)
    assert report["revenue_lost_eur"] == pytest.approx(round(1.5 * RATE, 2))
    assert report["revenue_eur"] == pytest.approx(round(23.5 * RATE, 2))
    assert report["negative_quarter_hours"] == 6
    assert [m["month"] for m in report["months"]] == ["2026-10"]
    assert report["gaps"] == {
        "quarter_hours_without_price": 0,
        "price_ranges": [],
        "hours_without_energy": 0,
    }


def test_report_with_local_period_bounds() -> None:
    """Bounds in local time (as the action passes them) must not skip the DST hour."""
    start = datetime(2026, 10, 25, tzinfo=BERLIN)
    end = datetime(2026, 10, 26, tzinfo=BERLIN)
    report = build_report(
        hours(DAY_START, DAY_END),
        start,
        end,
        counter(DAY_START + 5 * HOUR),
        NegativeQuarterHour(),
        RATE,
        BERLIN,
    )
    assert report["energy_paid_kwh"] + report["energy_unpaid_kwh"] == pytest.approx(25)
    assert report["gaps"]["quarter_hours_without_price"] == 20
    assert report["gaps"]["hours_without_energy"] == 0


def test_report_while_rule_does_not_apply() -> None:
    report = build_report(
        hours(DAY_START, DAY_END),
        DAY_START,
        DAY_END,
        counter(),
        AlwaysPaid(),
        RATE,
        BERLIN,
    )
    assert report["energy_unpaid_kwh"] == 0
    assert report["negative_quarter_hours"] == 0


def test_report_lists_gaps() -> None:
    known_from = DAY_START + timedelta(hours=12)  # 12:00 CET
    report = build_report(
        hours(DAY_START, DAY_END - 2 * HOUR),
        DAY_START,
        DAY_END,
        counter(known_from),
        NegativeQuarterHour(),
        RATE,
        BERLIN,
    )
    gaps = report["gaps"]
    assert gaps["quarter_hours_without_price"] == 48
    assert gaps["price_ranges"] == [
        {"start": "2026-10-25T00:00:00+02:00", "end": "2026-10-25T11:00:00+01:00"}
    ]
    assert gaps["hours_without_energy"] == 2
    # Negative quarter hours before 12:00 are unknown and count as paid.
    assert report["negative_quarter_hours"] == 3


def test_report_splits_months_in_local_time() -> None:
    start = datetime(2026, 10, 31, 22, tzinfo=UTC)  # 31.10. 23:00 CET
    end = start + 2 * HOUR
    report = build_report(
        hours(start, end),
        start,
        end,
        QuarterCounter(),
        NegativeQuarterHour(),
        RATE,
        BERLIN,
    )
    assert [(m["month"], m["energy_paid_kwh"]) for m in report["months"]] == [
        ("2026-10", 1.0),
        ("2026-11", 1.0),
    ]


def test_split_hour_until_spreads_over_the_quarter_hours_before() -> None:
    hour = datetime(2026, 10, 25, 3, tzinfo=UTC)  # 03:00 negative, 03:15 price 0
    rule = NegativeQuarterHour()
    assert split_hour(hour, 1.0, counter(), rule) == pytest.approx((0.5, 0.5))
    until = hour + timedelta(minutes=30)
    assert split_hour(hour, 1.0, counter(), rule, until=until) == pytest.approx(
        (0.5, 0.5)
    )
    until = hour + timedelta(minutes=15)
    assert split_hour(hour, 1.0, counter(), rule, until=until) == pytest.approx(
        (0.0, 1.0)
    )
