"""Quarter-hour counter (§ 51a) and the engine tying everything together."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.einspeisewacht.const import BERLIN
from custom_components.einspeisewacht.engine import Engine
from custom_components.einspeisewacht.ledger import FeedInValuation
from custom_components.einspeisewacht.meter import MeterTracker
from custom_components.einspeisewacht.prices import PriceTable, parse_interval_prices
from custom_components.einspeisewacht.quarters import MAX_CATCH_UP, QuarterCounter
from custom_components.einspeisewacht.report import build_report, unknown_slots
from custom_components.einspeisewacht.rules import AlwaysPaid, NegativeQuarterHour
from tests.conftest import load_fixture

DAY_START = datetime(2026, 10, 24, 22, tzinfo=UTC)  # 25.10. 00:00 local
DAY_END = datetime(2026, 10, 25, 23, tzinfo=UTC)  # 26.10. 00:00 local
RATE = 0.0794


def fixture_parsed() -> list:
    fixture = load_fixture("epex_spot_2026-10-25.json")
    return [
        parse_interval_prices(fixture["history_supplement"]),
        parse_interval_prices(fixture["attributes"]["data"]),
    ]


def fixture_prices() -> PriceTable:
    table = PriceTable()
    for parsed in fixture_parsed():
        table.merge(parsed.prices)
    return table


# --- counter ------------------------------------------------------------------

EPOCH = datetime(2020, 1, 1, tzinfo=UTC)
RULE = NegativeQuarterHour()


def test_counter_records_negative_quarter_hours_of_dst_day() -> None:
    counter = QuarterCounter(next_slot=DAY_START, started=DAY_START)
    counter.advance(DAY_END, fixture_prices())
    assert len(counter.negatives) == 6
    assert counter.counts(RULE, EPOCH, BERLIN) == {2026: 6}
    assert counter.counts(AlwaysPaid(), EPOCH, BERLIN) == {}
    assert counter.next_slot == DAY_END
    assert counter.known(DAY_START) and not counter.known(DAY_END)


def test_counter_counts_follow_the_rule_without_recounting() -> None:
    counter = QuarterCounter(next_slot=DAY_START, started=DAY_START)
    counter.advance(DAY_END, fixture_prices())
    # 14:00 CET = 13:00 UTC: a rule starting then counts only the last three.
    later = NegativeQuarterHour(applies_from=datetime(2026, 10, 25, 13, tzinfo=UTC))
    assert counter.counts(later, EPOCH, BERLIN) == {2026: 3}
    assert counter.counts(RULE, datetime(2026, 10, 25, 13, tzinfo=UTC), BERLIN) == {
        2026: 3
    }


def test_counter_starts_with_running_quarter_hour() -> None:
    counter = QuarterCounter()
    counter.advance(DAY_END + timedelta(minutes=7), PriceTable())
    assert counter.next_slot == counter.started == DAY_END
    assert counter.negatives == {}


def test_counter_waits_for_missing_price_then_skips() -> None:
    counter = QuarterCounter(next_slot=DAY_START, started=DAY_START)
    prices = PriceTable()
    counter.advance(DAY_START + timedelta(hours=1), prices)
    assert counter.next_slot == DAY_START
    counter.advance(DAY_START + timedelta(hours=24, minutes=15), prices)
    assert counter.next_slot == DAY_START + timedelta(minutes=15)
    assert counter.missing == {DAY_START}
    assert not counter.known(DAY_START)


def test_counter_counts_a_price_that_arrives_late() -> None:
    negative = datetime(2026, 10, 25, 3, tzinfo=UTC)  # 04:00 CET, price below 0
    counter = QuarterCounter(next_slot=negative, started=negative)
    counter.advance(negative + timedelta(hours=24, minutes=15), PriceTable())
    assert counter.missing == {negative}
    # The price sensor delivers the previous day after all.
    assert counter.resolve(fixture_prices())
    assert counter.missing == set()
    assert negative in counter.negatives
    assert counter.known(negative)
    assert not counter.resolve(fixture_prices())


def test_counter_does_not_catch_up_long_gaps() -> None:
    counter = QuarterCounter(next_slot=DAY_START, started=DAY_START)
    later = DAY_START + MAX_CATCH_UP + timedelta(hours=1, minutes=5)
    back = later.replace(minute=0)
    counter.advance(later, PriceTable())
    assert counter.next_slot == back
    assert counter.started == DAY_START
    # The skipped time stays unknown: one range, not a quarter hour each.
    assert counter.gaps == [(DAY_START, back)]
    assert counter.missing == set()
    assert not counter.known(DAY_START)
    assert not counter.known(back - timedelta(minutes=15))
    assert len(unknown_slots(DAY_START, back, counter)) == (back - DAY_START) / (
        timedelta(minutes=15)
    )
    counter.advance(back + timedelta(minutes=15), PriceTable({back: 0.05}))
    assert counter.known(back)


def test_report_shows_a_long_gap() -> None:
    """HA was off for weeks: the report lists the time as without price."""
    counter = QuarterCounter(next_slot=DAY_START, started=DAY_START)
    back = DAY_START + MAX_CATCH_UP + timedelta(days=1)
    counter.advance(back, PriceTable())
    report = build_report([], DAY_START, DAY_END, counter, RULE, RATE, BERLIN)
    assert report["gaps"]["quarter_hours_without_price"] == 100  # 25-hour day


def test_counter_years_follow_local_time() -> None:
    # 01.01.2026 00:00 local is 31.12.2025 23:00 UTC.
    first = datetime(2025, 12, 31, 22, 45, tzinfo=UTC)
    prices = PriceTable({first: -0.01, first + timedelta(minutes=15): -0.01})
    counter = QuarterCounter(next_slot=first, started=first)
    counter.advance(first + timedelta(minutes=30), prices)
    assert counter.counts(RULE, EPOCH, BERLIN) == {2025: 1, 2026: 1}


def test_counter_round_trip_and_legacy_data() -> None:
    counter = QuarterCounter(next_slot=DAY_START, started=DAY_START)
    counter.advance(DAY_END, fixture_prices())
    counter.missing.add(DAY_END)
    counter.gaps.append((DAY_START - timedelta(days=30), DAY_START - timedelta(days=9)))
    restored = QuarterCounter()
    restored.restore(
        json.loads(json.dumps(counter.as_dict())),
        json.loads(json.dumps(counter.negatives_dict())),
    )
    assert restored == counter
    # 0.1.0b3 stored counts only: start afresh.
    legacy = QuarterCounter()
    legacy.restore({"next_slot": DAY_START.isoformat(), "counts": {"2026": 3}}, None)
    assert legacy == QuarterCounter()


# --- engine -------------------------------------------------------------------


def make_engine(rate: float = RATE, rule=None) -> Engine:
    return Engine(
        meter=MeterTracker(max_power_kw=9),
        valuation=FeedInValuation(
            rate=rate,
            rule=rule or NegativeQuarterHour(),
            shadow_rule=NegativeQuarterHour(),
        ),
    )


def test_engine_day() -> None:
    engine = make_engine()
    # HA starts at 25.10. 00:00 local; the forecast arrives first.
    for parsed in fixture_parsed():
        engine.on_prices(parsed, DAY_START)
    at, value = DAY_START, 1234.0
    while at <= DAY_END:
        engine.on_meter(value, at, at)
        engine.tick(at)
        at += timedelta(minutes=5)
        value += 1 / 12  # 1 kW
    totals = engine.ledger.totals
    assert totals["energy_unpaid"] == pytest.approx(1.5)
    assert totals["energy_paid"] == pytest.approx(25 - 1.5)
    assert engine.counts() == {2026: 6}
    assert engine.shadow_counts() == {2026: 6}
    assert engine.meter_events == {"first": 1}


def test_engine_waits_for_prices_after_a_start() -> None:
    """HA was off for over a day; at the start the price sensor is not ready yet."""
    engine = make_engine()
    engine.quarters = QuarterCounter(next_slot=DAY_START, started=DAY_START)
    # 25 kWh over 25.10. while no prices were known: held back.
    engine.on_meter(1000.0, DAY_START, DAY_START)
    engine.on_meter(1025.0, DAY_END, DAY_END)
    start = DAY_END + timedelta(hours=25)
    engine.tick(start)
    assert engine.ledger.totals.get("energy_paid", 0) == 0
    assert engine.quarters.missing == set()
    # Seconds later the sensor delivers its forecast, previous day included
    # (one attribute, as EPEX Spot has it).
    fixture = load_fixture("epex_spot_2026-10-25.json")
    engine.on_prices(
        parse_interval_prices(
            fixture["history_supplement"] + fixture["attributes"]["data"]
        ),
        start,
    )
    assert engine.ledger.totals["energy_unpaid"] == pytest.approx(1.5)
    assert engine.ledger.totals["energy_paid"] == pytest.approx(25 - 1.5)
    assert engine.counts() == {2026: 6}


def test_engine_fills_prices_the_sensor_left_open() -> None:
    """The price sensor stopped after 24.10. 23:00 local; SMARD.de has the day."""
    engine = make_engine()
    engine.quarters = QuarterCounter(next_slot=DAY_START, started=DAY_START)
    sensor, smard = fixture_parsed()  # 24.10. 22:00-23:00 UTC, then the rest
    engine.on_prices(sensor, DAY_START)
    engine.on_meter(1000.0, DAY_START, DAY_START)
    engine.on_meter(1025.0, DAY_END, DAY_END)
    now = DAY_END + timedelta(hours=2)
    engine.tick(now)
    assert engine.price_gap(now) == DAY_START + timedelta(hours=1)
    kept = next(iter(sensor.prices))
    # SMARD.de prices only where the sensor had none.
    assert engine.fill_prices({**smard.prices, kept: -1.0}, now) == len(smard.prices)
    assert engine.prices.get(kept) == sensor.prices[kept]
    assert engine.ledger.totals["energy_unpaid"] == pytest.approx(1.5)
    assert engine.counts() == {2026: 6}
    assert engine.price_gap(now) is None
    assert engine.fill_prices(smard.prices, now) == 0


def test_engine_paid_now() -> None:
    engine = make_engine()
    for parsed in fixture_parsed():
        engine.on_prices(parsed, DAY_START)
    assert (
        engine.paid_now(datetime(2026, 10, 25, 3, 5, tzinfo=UTC)) is False
    )  # 04:05 CET
    assert engine.paid_now(datetime(2026, 10, 25, 3, 20, tzinfo=UTC)) is True  # price 0
    assert engine.paid_now(datetime(2026, 11, 1, tzinfo=UTC)) is None


def test_engine_round_trip_is_json() -> None:
    engine = make_engine()
    for parsed in fixture_parsed():
        engine.on_prices(parsed, DAY_START)
    engine.on_meter(1.0, DAY_START, DAY_START)
    engine.on_meter(
        1.5, DAY_START + timedelta(minutes=20), DAY_START + timedelta(minutes=20)
    )
    engine.tick(DAY_END)
    live = json.loads(json.dumps(engine.as_live_dict()))
    history = json.loads(json.dumps(engine.as_history_dict()))
    assert "prices" not in live and "negatives" in history
    restored = make_engine()
    restored.restore(live, history)
    assert restored.as_live_dict() == engine.as_live_dict()
    assert restored.as_history_dict() == engine.as_history_dict()


def test_engine_restores_single_file_of_0_1_0b4() -> None:
    engine = make_engine()
    for parsed in fixture_parsed():
        engine.on_prices(parsed, DAY_START)
    engine.tick(DAY_END)
    old = {**engine.as_live_dict(), "prices": engine.prices.as_dict()}
    old["quarters"] = {**old["quarters"], "negatives": engine.quarters.negatives_dict()}
    restored = make_engine()
    restored.restore(json.loads(json.dumps(old)))
    assert restored.counts() == {2026: 6}
    assert restored.prices == engine.prices


def test_engine_tracks_history_changes() -> None:
    engine = make_engine()
    for parsed in fixture_parsed():
        engine.on_prices(parsed, DAY_START)
    version = engine.history_version
    assert version >= 1
    engine.on_prices(parsed, DAY_START)  # same forecast again: nothing to write
    assert engine.history_version == version
    negatives = engine.negatives_version
    # 25.10. has 25 hours: 04:00-04:15 CET (negative) ends 5 h 15 min after midnight.
    engine.tick(DAY_START + timedelta(hours=5, minutes=15))
    assert engine.negatives_version == negatives + 1
    # Ticks without new negatives or pruning change nothing.
    version = engine.history_version
    engine.tick(DAY_START + timedelta(hours=5, minutes=30))
    assert engine.history_version == version


def test_engine_prunes_old_prices_about_daily() -> None:
    engine = make_engine()
    for parsed in fixture_parsed():
        engine.on_prices(parsed, DAY_START)
    # Oldest price only half a day beyond the retention: not yet.
    engine.tick(DAY_START + timedelta(days=15, hours=12))
    assert DAY_START in engine.prices.prices
    engine.tick(DAY_START + timedelta(days=20))
    assert engine.prices.prices == {}


def booked_day(rate: float = RATE, rule=None) -> Engine:
    """1 kW all day on 25.10.2026 (six negative quarter hours)."""
    engine = make_engine(rate, rule)
    for parsed in fixture_parsed():
        engine.on_prices(parsed, DAY_START)
    at, value = DAY_START, 1234.0
    while at <= DAY_END:
        engine.on_meter(value, at, at)
        engine.tick(at)
        at += timedelta(minutes=5)
        value += 1 / 12
    return engine


def reloaded(engine: Engine, rate: float = RATE, rule=None) -> Engine:
    """The engine after a restart with the given (reconfigured) rate and rule."""
    restored = make_engine(rate, rule)
    restored.restore(
        json.loads(json.dumps(engine.as_live_dict())),
        json.loads(json.dumps(engine.as_history_dict())),
    )
    return restored


def test_engine_corrected_rate_applies_since_setup() -> None:
    engine = booked_day()
    restored = reloaded(engine, rate=0.0821)
    totals = restored.ledger.totals
    assert totals["energy_paid"] == engine.ledger.totals["energy_paid"]
    assert totals["revenue"] == pytest.approx(totals["energy_paid"] * 0.0821)
    assert totals["revenue_lost"] == pytest.approx(1.5 * 0.0821)
    assert totals["shadow_revenue_lost"] == pytest.approx(1.5 * 0.0821)
    assert restored.rule_change is None
    # New bookings use the new rate as well.
    restored.on_meter(1236.0, DAY_END + timedelta(hours=1), DAY_END)
    assert restored.ledger.totals["revenue"] == pytest.approx(
        restored.ledger.totals["energy_paid"] * 0.0821
    )


def test_engine_reports_a_rule_change_for_booked_quarter_hours() -> None:
    engine = booked_day()
    totals = dict(engine.ledger.totals)
    # Reconfigured to "not affected": the six booked negative quarter hours
    # would be paid now. The energy totals keep their split (no decrease of a
    # TOTAL_INCREASING sensor), the change is recorded.
    restored = reloaded(engine, rule=AlwaysPaid())
    assert restored.ledger.totals == pytest.approx(totals)
    assert restored.rule_change == {
        "until": restored.quarters.next_slot.isoformat(),
        "quarter_hours": 6,
    }
    assert restored.rule_history == [(NegativeQuarterHour(), DAY_END)]
    # Kept over the next restart.
    again = reloaded(restored, rule=AlwaysPaid())
    assert again.rule_change == restored.rule_change
    # A rule that judges the booked quarter hours alike changes nothing.
    later = NegativeQuarterHour(applies_from=DAY_START)
    assert reloaded(engine, rule=later).rule_change is None
    assert reloaded(engine).rule_change is None
    # Changed back: everything booked agrees again, the history is dropped.
    back = reloaded(again)
    assert back.rule_change is None and back.rule_history == []


def test_engine_rule_change_counts_each_period_by_its_rule() -> None:
    """Changed twice: quarter hours count against the rule that booked them."""
    engine = reloaded(booked_day(), rule=AlwaysPaid())
    assert engine.rule_change["quarter_hours"] == 6
    # Another rule that also pays everything up to now: nothing new differs,
    # the six quarter hours booked under the first rule still do.
    later = NegativeQuarterHour(applies_from=DAY_END)
    again = reloaded(engine, rule=later)
    assert again.rule_change == engine.rule_change
    assert len(again.rule_history) == 2
