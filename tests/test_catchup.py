"""Extension (§ 51a), SMARD.de parsing, backfill counting and calendar windows."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from custom_components.einspeisewacht.catchup import (
    MONTHLY_QUOTA,
    extension,
    regular_end,
)
from custom_components.einspeisewacht.const import BERLIN
from custom_components.einspeisewacht.prices import parse_interval_prices
from custom_components.einspeisewacht.quarters import QuarterCounter
from custom_components.einspeisewacht.rules import AlwaysPaid, NegativeQuarterHour
from custom_components.einspeisewacht.smard import (
    parse_index,
    parse_week,
    week_url,
    weeks_covering,
)
from custom_components.einspeisewacht.timeslots import QUARTER
from custom_components.einspeisewacht.windows import negative_windows
from tests.conftest import load_fixture

DAY_START = datetime(2026, 10, 24, 22, tzinfo=UTC)  # 25.10.2026 00:00 local
DAY_END = datetime(2026, 10, 25, 23, tzinfo=UTC)


# --- § 51a ---------------------------------------------------------------------


def test_quota_table() -> None:
    assert MONTHLY_QUOTA == (87, 189, 340, 442, 490, 508, 498, 453, 371, 231, 118, 73)
    assert sum(MONTHLY_QUOTA) == 3800


def test_regular_end() -> None:
    # Plants from 2000 left the scheme at the end of 2020.
    assert regular_end(date(2000, 6, 1)) == date(2020, 12, 31)
    assert regular_end(date(2025, 7, 31)) == date(2045, 12, 31)


def test_extension_example_from_the_law_review() -> None:
    # 600 quarter hours -> 300 full-load quarter hours -> Jan (87) + Feb (189) + 24 in March.
    result = extension(date(2025, 6, 15), {2026: 600})
    assert result.full_load_quarter_hours == 300
    assert result.months == (
        (date(2046, 1, 1), 87),
        (date(2046, 2, 1), 189),
        (date(2046, 3, 1), 24),
    )
    assert result.extended_end == date(2046, 3, 31)


def test_extension_rounds_up_and_counts_only_twenty_years() -> None:
    assert extension(date(2025, 6, 15), {2025: 5}).full_load_quarter_hours == 3
    # Counted: 2025 ... 2044; 2045 (last regular year) is not.
    result = extension(date(2025, 6, 15), {2024: 50, 2044: 2, 2045: 100})
    assert result.negative_quarter_hours == 2
    assert result.full_load_quarter_hours == 1


def test_no_extension() -> None:
    result = extension(date(2025, 6, 15), {})
    assert result.full_load_quarter_hours == 0
    assert result.months == ()
    assert result.extended_end == date(2045, 12, 31)


def test_extension_over_a_full_year() -> None:
    result = extension(date(2025, 6, 15), {2026: 7602})  # 3801 full-load quarter hours
    assert len(result.months) == 13
    assert result.months[-1] == (date(2047, 1, 1), 1)
    assert result.extended_end == date(2047, 1, 31)


# --- SMARD.de ------------------------------------------------------------------


def test_parse_index_and_weeks() -> None:
    index = parse_index(load_fixture("smard_index_quarterhour.json"))
    assert index == sorted(index)
    weeks = weeks_covering(index, DAY_START, DAY_END)
    assert weeks == [1792360800000]  # Monday 19.10.2026 00:00 CEST
    assert week_url(weeks[0]).endswith("/4169_DE-LU_quarterhour_1792360800000.json")
    # A range over a week boundary needs both files.
    assert len(weeks_covering(index, DAY_START, DAY_START + timedelta(days=2))) == 2


def test_smard_matches_epex_fixture() -> None:
    smard = parse_week(load_fixture("smard_week_2026-10-19.json"))
    assert len(smard) == 676  # 7 days + 1 hour (DST)
    epex = load_fixture("epex_spot_2026-10-25.json")
    entries = epex["history_supplement"] + epex["attributes"]["data"]
    for slot, price in parse_interval_prices(entries).prices.items():
        if DAY_START <= slot < DAY_END:
            assert smard[slot] == pytest.approx(price, abs=1e-9)


def test_smard_hourly_before_october_2025() -> None:
    prices = parse_week(load_fixture("smard_week_2025-09-29.json"))
    hour = datetime(2025, 9, 30, 10, tzinfo=UTC)
    assert len({prices[hour + i * QUARTER] for i in range(4)}) == 1
    assert len(prices) == 672


def test_backfill_matches_live_counting() -> None:
    prices = parse_week(load_fixture("smard_week_2026-10-19.json"))
    rule = NegativeQuarterHour()
    since = datetime(2020, 1, 1, tzinfo=UTC)
    backfilled = QuarterCounter(started=DAY_END, next_slot=DAY_END)
    assert backfilled.add_backfill(prices, DAY_START, DAY_END) == 0
    from custom_components.einspeisewacht.prices import PriceTable

    live = QuarterCounter(next_slot=DAY_START, started=DAY_START)
    live.advance(DAY_END, PriceTable(prices))
    assert backfilled.negatives == live.negatives
    assert backfilled.counts(rule, since, BERLIN) == {2026: 6}
    assert backfilled.known(DAY_START) and backfilled.known(DAY_END - QUARTER)


def test_backfill_reports_missing_prices() -> None:
    counter = QuarterCounter(started=DAY_START + timedelta(hours=1))
    counter.next_slot = counter.started
    assert counter.add_backfill({}, DAY_START, DAY_START + timedelta(hours=1)) == 4
    assert not counter.known(DAY_START)


def test_backfill_replaces_earlier_backfill_but_keeps_live_values() -> None:
    week = parse_week(load_fixture("smard_week_2026-10-19.json"))
    counter = QuarterCounter(started=DAY_END, next_slot=DAY_END + QUARTER)
    counter.negatives[DAY_END] = -0.5  # live
    counter.add_backfill(week, DAY_START, DAY_END)
    counter.add_backfill(week, DAY_START + timedelta(hours=12), DAY_END)
    assert len(counter.negatives) == 1 + 3  # live + 14:00, 14:15, 15:00 CET
    assert counter.backfill_from == DAY_START + timedelta(hours=12)


# --- calendar windows ----------------------------------------------------------


def test_negative_windows_of_dst_day() -> None:
    epex = load_fixture("epex_spot_2026-10-25.json")
    prices = parse_interval_prices(
        epex["history_supplement"] + epex["attributes"]["data"]
    ).prices
    windows = negative_windows(prices, NegativeQuarterHour())
    local = [
        (
            w.start.astimezone(BERLIN).strftime("%H:%M"),
            w.end.astimezone(BERLIN).strftime("%H:%M"),
        )
        for w in windows
    ]
    assert local == [
        ("04:00", "04:15"),
        ("04:30", "04:45"),
        ("06:00", "06:15"),
        ("14:00", "14:30"),
        ("15:00", "15:15"),
    ]
    assert not any(w.paid for w in windows)
    assert windows[3].lowest_price == -0.00001


def test_negative_windows_while_rule_does_not_apply() -> None:
    prices = {DAY_START: -0.01, DAY_START + QUARTER: -0.02}
    (window,) = negative_windows(prices, AlwaysPaid())
    assert window.paid
    assert window.lowest_price == -0.02
    assert window.end == DAY_START + 2 * QUARTER
