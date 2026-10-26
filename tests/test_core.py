"""Booking core: time slots, meter, prices, rules, ledger (no Home Assistant)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.einspeisewacht.ledger import (
    PRICE_WAIT,
    FeedInValuation,
    Ledger,
)
from custom_components.einspeisewacht.meter import MeterEvent, MeterTracker, to_kwh
from custom_components.einspeisewacht.prices import PriceTable, parse_interval_prices
from custom_components.einspeisewacht.rules import AlwaysPaid, NegativeQuarterHour
from custom_components.einspeisewacht.solar import daylight_weight
from custom_components.einspeisewacht.timeslots import (
    QUARTER,
    slot_start,
    split_interval,
)
from tests.conftest import load_fixture

RATE = 0.0794  # EUR/kWh


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def fixture_prices() -> PriceTable:
    fixture = load_fixture("epex_spot_2026-10-25.json")
    table = PriceTable()
    for entries in (fixture["history_supplement"], fixture["attributes"]["data"]):
        table.merge(parse_interval_prices(entries).prices)
    return table


# --- time slots ---------------------------------------------------------------


def test_slot_start_floors_in_utc() -> None:
    local = datetime.fromisoformat("2026-10-25T02:59:59+01:00")
    assert slot_start(local) == utc(2026, 10, 25, 1, 45)
    with pytest.raises(ValueError):
        slot_start(datetime(2026, 1, 1))  # noqa: DTZ001


def test_split_interval_is_proportional() -> None:
    pieces = split_interval(utc(2026, 1, 1, 9, 10), utc(2026, 1, 1, 9, 20), 0.004)
    assert pieces == [
        (utc(2026, 1, 1, 9, 0), pytest.approx(0.002)),
        (utc(2026, 1, 1, 9, 15), pytest.approx(0.002)),
    ]


def test_split_interval_over_gap_keeps_sum() -> None:
    pieces = split_interval(utc(2026, 1, 1, 8, 7), utc(2026, 1, 1, 11, 2), 3.0)
    assert len(pieces) == 13  # 08:00 ... 11:00
    assert sum(e for _, e in pieces) == pytest.approx(3.0)
    assert pieces[0][0] == utc(2026, 1, 1, 8, 0)
    assert pieces[-1][0] == utc(2026, 1, 1, 11, 0)


def test_split_interval_empty() -> None:
    at = utc(2026, 1, 1, 9, 0)
    assert split_interval(at, at, 0.5) == [(at, 0.5)]


# --- meter --------------------------------------------------------------------


def test_units() -> None:
    assert to_kwh(1234567.0, "Wh") == pytest.approx(1234.567)
    assert to_kwh(1.5, "kWh") == 1.5
    with pytest.raises(KeyError):
        to_kwh(1.0, "W")


def test_meter_first_reading_is_baseline() -> None:
    meter = MeterTracker(max_power_kw=9)
    update = meter.update(100.0, utc(2026, 1, 1, 9))
    assert update.event is MeterEvent.FIRST
    assert update.pieces == []


def test_meter_reset_and_jump_are_not_booked() -> None:
    meter = MeterTracker(max_power_kw=9)
    meter.update(1234.567, utc(2026, 1, 1, 9, 0))
    # Inverter restart reports 0, then the real counter again.
    reset = meter.update(0.0, utc(2026, 1, 1, 9, 1))
    jump = meter.update(1234.568, utc(2026, 1, 1, 9, 2))
    assert reset.event is MeterEvent.RESET and reset.pieces == []
    assert jump.event is MeterEvent.JUMP and jump.pieces == []
    # Normal operation continues from the new baseline.
    normal = meter.update(1234.578, utc(2026, 1, 1, 9, 3))
    assert normal.event is None
    assert sum(e for _, e in normal.pieces) == pytest.approx(0.010)


def test_meter_allows_full_power_and_whole_wh_steps() -> None:
    meter = MeterTracker(max_power_kw=9)
    meter.update(0.0, utc(2026, 6, 1, 12, 0, 0))
    # 9 kW for one hour.
    assert meter.update(9.0, utc(2026, 6, 1, 13, 0, 0)).event is None
    # 1 Wh one second later (rounding of the counter).
    assert meter.update(9.001, utc(2026, 6, 1, 13, 0, 1)).event is None


def test_meter_ignores_out_of_order_readings() -> None:
    meter = MeterTracker(max_power_kw=9)
    meter.update(1.0, utc(2026, 1, 1, 9, 5))
    assert meter.update(0.5, utc(2026, 1, 1, 9, 0)).pieces == []
    assert meter.last_value == 1.0


def test_meter_round_trip() -> None:
    meter = MeterTracker(max_power_kw=9)
    meter.update(1.0, utc(2026, 1, 1, 9, 5))
    restored = MeterTracker(max_power_kw=9)
    restored.restore(meter.as_dict())
    assert restored == meter


# --- prices -------------------------------------------------------------------


def test_parse_epex_fixture() -> None:
    fixture = load_fixture("epex_spot_2026-10-25.json")
    parsed = parse_interval_prices(fixture["attributes"]["data"])
    assert parsed.skipped == 0
    assert parsed.resolution == QUARTER
    assert len(parsed.prices) == 192
    # The repeated hour: both 02:45 CEST and 02:00 CET exist, one hour apart in UTC.
    assert parsed.prices[utc(2026, 10, 25, 0, 45)] == 0
    assert parsed.prices[utc(2026, 10, 25, 1, 0)] == 0.00001


def test_parse_hourly_prices_cover_four_quarters() -> None:
    parsed = parse_interval_prices(
        [
            {
                "start_time": "2026-01-01T10:00:00+01:00",
                "end_time": "2026-01-01T11:00:00+01:00",
                "price_per_kwh": -0.01,
            }
        ]
    )
    assert parsed.resolution == timedelta(hours=1)
    assert sorted(parsed.prices) == [utc(2026, 1, 1, 9, m) for m in (0, 15, 30, 45)]


def test_parse_skips_broken_entries() -> None:
    parsed = parse_interval_prices(
        [
            {"start_time": "2026-01-01T10:00:00+01:00"},
            {"start_time": "x", "end_time": "y", "price_per_kwh": 1},
            {
                "start_time": "2026-01-01T10:05:00+01:00",
                "end_time": "2026-01-01T10:20:00+01:00",
                "price_per_kwh": 0.1,
            },
            {
                "start_time": "2026-01-01T10:00:00",
                "end_time": "2026-01-01T10:15:00",
                "price_per_kwh": 0.1,
            },
        ]
    )
    assert parsed.prices == {}
    assert parsed.skipped == 4
    assert parsed.resolution is None


def test_price_table_prune_and_round_trip() -> None:
    table = fixture_prices()
    table.prune(utc(2026, 10, 26, 0))
    assert min(table.prices) == utc(2026, 10, 26, 0)
    restored = PriceTable()
    restored.restore(table.as_dict())
    assert restored == table


# --- rules --------------------------------------------------------------------


def test_zero_is_not_negative() -> None:
    rule = NegativeQuarterHour()
    slot = utc(2026, 10, 25, 9)
    assert rule.is_paid(slot, 0.0)
    assert rule.is_paid(slot, 0.00001)
    assert not rule.is_paid(slot, -0.00001)
    assert AlwaysPaid().is_paid(slot, -1.0)


def test_rule_applies_from() -> None:
    rule = NegativeQuarterHour(applies_from=utc(2025, 12, 31, 23))
    assert rule.is_paid(utc(2025, 12, 31, 22, 45), -0.1)
    assert not rule.is_paid(utc(2025, 12, 31, 23), -0.1)


# --- ledger -------------------------------------------------------------------


def valuation(rule=None) -> FeedInValuation:
    return FeedInValuation(
        rate=RATE, rule=rule or NegativeQuarterHour(), shadow_rule=NegativeQuarterHour()
    )


def simulate_constant_feed_in(rule, step: timedelta) -> Ledger:
    """1 kW feed-in all day on 25.10.2026, meter read every `step`."""
    prices = fixture_prices()
    meter, ledger, val = MeterTracker(max_power_kw=9), Ledger(), valuation(rule)
    start, end = utc(2026, 10, 24, 22), utc(2026, 10, 25, 23)
    at, value = start, 1000.0
    while at <= end:
        update = meter.update(value, at)
        ledger.book(update.pieces, prices, val, at)
        at += step
        value += step.total_seconds() / 3600
    return ledger


@pytest.mark.parametrize("step", [timedelta(minutes=7), timedelta(seconds=61)])
def test_dst_day_constant_feed_in(step: timedelta) -> None:
    ledger = simulate_constant_feed_in(NegativeQuarterHour(), step)
    totals = ledger.totals
    booked = totals["energy_paid"] + totals["energy_unpaid"]
    covered = (utc(2026, 10, 25, 23) - utc(2026, 10, 24, 22)).total_seconds() / 3600
    # The last reading may stop short of midnight; everything read is booked.
    assert booked == pytest.approx(covered - (covered % (step.total_seconds() / 3600)))
    # 6 negative quarter hours at 1 kW = 1.5 kWh; exactly-0 prices stay paid.
    assert totals["energy_unpaid"] == pytest.approx(1.5)
    assert totals["revenue_lost"] == pytest.approx(1.5 * RATE)
    assert totals["revenue"] == pytest.approx(totals["energy_paid"] * RATE)
    assert totals["shadow_energy_unpaid"] == pytest.approx(1.5)
    assert ledger.pending == {}


def test_rule_not_applying_yet_books_shadow_only() -> None:
    ledger = simulate_constant_feed_in(AlwaysPaid(), timedelta(minutes=7))
    assert "energy_unpaid" not in ledger.totals
    assert ledger.totals["shadow_energy_unpaid"] == pytest.approx(1.5)
    assert ledger.totals["shadow_revenue_lost"] == pytest.approx(1.5 * RATE)


def test_missing_price_waits_then_books_paid() -> None:
    prices, ledger, val = PriceTable(), Ledger(), valuation()
    slot, now = utc(2026, 10, 25, 3), utc(2026, 10, 25, 3, 10)
    ledger.book([(slot, 0.1), (slot, 0.2)], prices, val, now)
    assert ledger.pending == {slot: (pytest.approx(0.3), now)}
    ledger.retry_pending(prices, val, now + PRICE_WAIT - timedelta(seconds=1))
    assert slot in ledger.pending
    ledger.retry_pending(prices, val, now + PRICE_WAIT)
    assert ledger.pending == {}
    assert ledger.booked_without_price == 1
    assert ledger.totals["energy_paid"] == pytest.approx(0.3)


def test_missing_price_booked_when_it_arrives() -> None:
    prices, ledger, val = PriceTable(), Ledger(), valuation()
    slot, now = utc(2026, 10, 25, 3), utc(2026, 10, 25, 3, 10)
    ledger.book([(slot, 0.25)], prices, val, now)
    prices.merge({slot: -0.00001})
    ledger.retry_pending(prices, val, now + timedelta(minutes=1))
    assert ledger.totals == {
        "energy_unpaid": pytest.approx(0.25),
        "revenue_lost": pytest.approx(0.25 * RATE),
        "shadow_energy_unpaid": pytest.approx(0.25),
        "shadow_revenue_lost": pytest.approx(0.25 * RATE),
    }


def test_ledger_round_trip() -> None:
    prices, ledger, val = PriceTable(), Ledger(), valuation()
    ledger.book([(utc(2026, 10, 25, 3), 0.1)], prices, val, utc(2026, 10, 25, 3, 5))
    ledger.totals["energy_paid"] = 1.0
    restored = Ledger()
    restored.restore(ledger.as_dict())
    assert restored == ledger


# --- gaps -----------------------------------------------------------------------


def test_split_interval_by_weight() -> None:
    start, end = utc(2026, 1, 1, 9, 0), utc(2026, 1, 1, 9, 30)
    # All weight in the second quarter hour.
    pieces = split_interval(start, end, 1.0, lambda m: 1.0 if m.minute >= 15 else 0.0)
    assert pieces == [(start, 0.0), (utc(2026, 1, 1, 9, 15), 1.0)]
    # No weight anywhere: linear.
    assert split_interval(start, end, 1.0, lambda m: 0.0) == split_interval(
        start, end, 1.0
    )


def test_long_gap_is_spread_by_daylight() -> None:
    weight = daylight_weight(48.78, 9.18)  # Stuttgart
    assert weight(utc(2026, 6, 21, 0)) == 0
    assert weight(utc(2026, 6, 21, 11)) > 0.85
    meter = MeterTracker(max_power_kw=9)
    meter.update(100.0, utc(2026, 6, 20, 18), weight)
    update = meter.update(130.0, utc(2026, 6, 21, 12), weight)  # HA off overnight
    assert update.event is MeterEvent.GAP
    by_slot = dict(update.pieces)
    assert sum(by_slot.values()) == pytest.approx(30.0)
    assert by_slot[utc(2026, 6, 21, 0)] == 0  # 02:00 CEST, dark
    assert by_slot[utc(2026, 6, 21, 10)] > by_slot[utc(2026, 6, 21, 5)]
    # Short gaps stay linear and are no event.
    assert meter.update(130.5, utc(2026, 6, 21, 12, 30), weight).event is None
