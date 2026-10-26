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


def test_counter_does_not_catch_up_long_gaps() -> None:
    counter = QuarterCounter(next_slot=DAY_START, started=DAY_START)
    later = DAY_START + MAX_CATCH_UP + timedelta(hours=1)
    counter.advance(later, PriceTable())
    assert counter.next_slot == later.replace(minute=0)
    assert counter.started == DAY_START


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
    restored = QuarterCounter()
    restored.restore(json.loads(json.dumps(counter.as_dict())))
    assert restored == counter
    # 0.1.0b3 stored counts only: start afresh.
    legacy = QuarterCounter()
    legacy.restore({"next_slot": DAY_START.isoformat(), "counts": {"2026": 3}})
    assert legacy == QuarterCounter()


# --- engine -------------------------------------------------------------------


def make_engine() -> Engine:
    return Engine(
        meter=MeterTracker(max_power_kw=9),
        valuation=FeedInValuation(
            rate=RATE, rule=NegativeQuarterHour(), shadow_rule=NegativeQuarterHour()
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
    data = json.loads(json.dumps(engine.as_dict()))
    restored = make_engine()
    restored.restore(data)
    assert restored.as_dict() == engine.as_dict()


def test_engine_prunes_old_prices() -> None:
    engine = make_engine()
    for parsed in fixture_parsed():
        engine.on_prices(parsed, DAY_START)
    engine.tick(DAY_START + timedelta(days=20))
    assert engine.prices.prices == {}
