"""Recalculating the money statistics after a rate change, and implausible
meter hours, against a real (in-memory) recorder: Home Assistant's own
5-minute and hourly compiles before and after it."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.recorder import Recorder, get_instance
from homeassistant.components.recorder.models import StatisticMeanType
from homeassistant.components.recorder.statistics import (
    async_import_statistics,
    statistics_during_period,
)
from homeassistant.components.recorder.tasks import StatisticsTask
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.einspeisewacht.const import CONF_RATES, DOMAIN
from custom_components.einspeisewacht.regime import local_midnight
from custom_components.einspeisewacht.runtime import PlantRuntime
from custom_components.einspeisewacht.smard import parse_week
from tests.conftest import load_fixture

from .conftest import METER, METER_ATTRIBUTES, entry_data
from .test_init import START, entity_id, setup

HOUR = timedelta(hours=1)
NEW_RATE = 0.10
# Money sensor -> energy sensor.
PAIRS = {"revenue": "energy_paid", "revenue_lost": "energy_unpaid"}

Rows = list[tuple[datetime, float, float]]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    recorder_mock: Recorder, enable_custom_integrations: None
) -> None:
    """The recorder must be prepared before hass (overrides the conftest fixture)."""


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


async def at(hass: HomeAssistant, freezer: FrozenDateTimeFactory, *t: int) -> None:
    freezer.move_to(utc(2026, 10, 25, *t))
    await hass.async_block_till_done()


async def meter(hass: HomeAssistant, wh: int) -> None:
    hass.states.async_set(METER, str(wh), METER_ATTRIBUTES)
    await hass.async_block_till_done()


async def compile_period(hass: HomeAssistant, start: datetime) -> None:
    """Home Assistant's 5-minute compile of [start, start + 5 min); at :55
    also the hour."""
    await async_wait_recording_done(hass)
    get_instance(hass).queue_task(StatisticsTask(start, False))
    await async_wait_recording_done(hass)


async def rows(hass: HomeAssistant, statistic_id: str, period: str) -> Rows:
    found = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        utc(2026, 10, 20),
        None,
        {statistic_id},
        period,
        None,
        {"state", "sum"},
    )
    return [
        (datetime.fromtimestamp(r["start"], UTC), r["state"], r["sum"])
        for r in found.get(statistic_id, [])
    ]


async def assert_money_follows_energy(
    hass: HomeAssistant, entry: MockConfigEntry, rate: float
) -> None:
    """Every money row is the energy row at the same start times the rate."""
    for money, energy in PAIRS.items():
        money_id, energy_id = (
            entity_id(hass, entry, money),
            entity_id(hass, entry, energy),
        )
        assert money_id and energy_id
        for period in ("hour", "5minute"):
            energy_rows = {t: (s, v) for t, s, v in await rows(hass, energy_id, period)}
            money_rows = await rows(hass, money_id, period)
            assert money_rows, (money, period)
            for start, state, total in money_rows:
                energy_state, energy_sum = energy_rows[start]
                assert total == pytest.approx(rate * energy_sum), (money, start)
                assert state == pytest.approx(rate * energy_state), (money, start)


async def press(hass: HomeAssistant, entry: MockConfigEntry) -> tuple[str, str]:
    """Press "Recalculate statistics": the notification's title and text."""
    button = er.async_get(hass).async_get_entity_id(
        "button", DOMAIN, f"{entry.entry_id}_recalculate_statistics"
    )
    assert button
    with patch(
        "custom_components.einspeisewacht.button.persistent_notification.async_create"
    ) as create:
        await hass.services.async_call(
            "button", "press", {"entity_id": button}, blocking=True
        )
    create.assert_called_once()
    assert create.call_args.kwargs["notification_id"] == (
        f"einspeisewacht_recalculate_{entry.entry_id}"
    )
    await async_wait_recording_done(hass)
    return create.call_args.kwargs["title"], create.call_args.args[1]


def outdated(hass: HomeAssistant, entry: MockConfigEntry) -> bool:
    issue = f"statistics_outdated_{entry.entry_id}"
    return ir.async_get(hass).async_get_issue(DOMAIN, issue) is not None


async def booked_hour_and_new_rate(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> MockConfigEntry:
    """An hour booked at 7.94 ct (03:00 UTC, compiled), then the rate
    corrected to 10 ct at 04:02 and the next 5 minutes compiled."""
    entry = await setup(hass)
    await at(hass, freezer, 3, 5, 10)
    await compile_period(hass, utc(2026, 10, 25, 3, 0))
    # 0.25 kWh at a negative price, then 0.3 kWh mostly at price 0.
    await at(hass, freezer, 3, 14, 30)
    await meter(hass, 1250)
    await at(hass, freezer, 3, 29, 30)
    await meter(hass, 1550)
    await at(hass, freezer, 3, 35, 10)
    await compile_period(hass, utc(2026, 10, 25, 3, 30))
    await at(hass, freezer, 4, 0, 10)
    await compile_period(hass, utc(2026, 10, 25, 3, 55))
    assert not outdated(hass, entry)

    await at(hass, freezer, 4, 2)
    hass.config_entries.async_update_entry(
        entry, data=entry_data(**{CONF_RATES: [NEW_RATE * 100]})
    )
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert outdated(hass, entry)
    await at(hass, freezer, 4, 5, 10)
    await compile_period(hass, utc(2026, 10, 25, 4, 0))
    return entry


@pytest.mark.freeze_time(START)
async def test_recalculate_after_a_rate_change(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """The past hour gets the new rate, the next compiles continue without
    a jump, a second press changes nothing."""
    entry = await booked_hour_and_new_rate(hass, freezer)
    revenue = entity_id(hass, entry, "revenue")
    paid = entity_id(hass, entry, "energy_paid")
    assert revenue and paid
    # Home Assistant booked the jump of the value into the next 5 minutes.
    old_hour = (await rows(hass, revenue, "hour"))[-1]
    jump = (await rows(hass, revenue, "5minute"))[-1][2] - old_hour[2]
    assert jump == pytest.approx(old_hour[1] / 0.0794 * (NEW_RATE - 0.0794))
    assert jump > 0.005

    title, message = await press(hass, entry)
    assert title == "Einspeisewacht: statistics recalculated (Dach)"
    assert "with the current rate of 10 ct/kWh" in message
    assert "Change of the total:" in message
    await assert_money_follows_energy(hass, entry, NEW_RATE)
    assert not outdated(hass, entry)
    hours = await rows(hass, revenue, "hour")
    short = await rows(hass, revenue, "5minute")

    # Idempotent: pressing again changes nothing.
    await press(hass, entry)
    assert await rows(hass, revenue, "hour") == hours
    assert await rows(hass, revenue, "5minute") == short

    # The next live compiles continue from the new rows: no jump, nothing
    # counted twice, also in the hourly row of the hour of the change.
    await at(hass, freezer, 4, 9, 30)
    await meter(hass, 1650)
    await at(hass, freezer, 4, 15, 10)
    await compile_period(hass, utc(2026, 10, 25, 4, 10))
    await at(hass, freezer, 5, 0, 10)
    await compile_period(hass, utc(2026, 10, 25, 4, 55))
    await assert_money_follows_energy(hass, entry, NEW_RATE)
    hours = await rows(hass, revenue, "hour")
    paid_hours = await rows(hass, paid, "hour")
    assert hours[-1][0] == utc(2026, 10, 25, 4)
    assert hours[-1][2] - hours[-2][2] == pytest.approx(
        NEW_RATE * (paid_hours[-1][2] - paid_hours[-2][2])
    )


@pytest.mark.freeze_time(START)
async def test_replace_from_a_day_before_the_setup(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """The action with `replace`: the time before the setup imported first
    (at the current rate), then everything recalculated."""
    entry = await booked_hour_and_new_rate(hass, freezer)
    engine = entry.runtime_data.engine
    start = local_midnight(date(2026, 10, 25))  # 24.10. 22:00 UTC
    week = parse_week(load_fixture("smard_week_2026-10-19.json"))
    engine.add_backfill(week, start, engine.quarters.started)
    before = [(start + h * HOUR, 1.0) for h in range(5)]  # until the setup hour
    with patch.object(PlantRuntime, "async_hourly_energy", return_value=(before, [])):
        result = await hass.services.async_call(
            DOMAIN,
            "import_statistics",
            {"config_entry_id": entry.entry_id, "start": "2026-10-25", "replace": True},
            blocking=True,
            return_response=True,
        )
    await async_wait_recording_done(hass)
    assert result["imported"]["sensors"]
    assert result["rate_ct_per_kwh"] == 10
    assert len(result["sensors"]) == 2
    revenue = entity_id(hass, entry, "revenue")
    assert (await rows(hass, revenue, "hour"))[0][0] == start
    await assert_money_follows_energy(hass, entry, NEW_RATE)
    assert not outdated(hass, entry)


@pytest.mark.freeze_time(START)
async def test_nothing_to_recalculate(hass: HomeAssistant) -> None:
    """No statistics yet: the notification says so; a later day finds none."""
    entry = await setup(hass)
    title, message = await press(hass, entry)
    assert title == "Einspeisewacht: statistics not recalculated (Dach)"
    assert "no statistics yet" in message
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "import_statistics",
            {"config_entry_id": entry.entry_id, "start": "2026-10-26", "replace": True},
            blocking=True,
            return_response=True,
        )
    assert err.value.translation_key == "import_no_statistics_yet"


async def meter_statistics(
    hass: HomeAssistant, states: list[tuple[int, float]]
) -> None:
    """Meter rows (kWh) on 24.10.: (hour UTC, state); the sum as Home
    Assistant compiles it, a fall below 90 % as a new cycle."""
    metadata: dict[str, Any] = {
        "has_sum": True,
        "mean_type": StatisticMeanType.NONE,
        "name": None,
        "source": "recorder",
        "statistic_id": METER,
        "unit_class": "energy",
        "unit_of_measurement": "kWh",
    }
    total, previous, data = 0.0, None, []
    for hour, state in states:
        if previous is not None:
            total += state if state < 0.9 * previous else state - previous
        previous = state
        data.append({"start": utc(2026, 10, 24, hour), "state": state, "sum": total})
    async_import_statistics(hass, metadata, data)  # type: ignore[arg-type]
    await async_wait_recording_done(hass)


@pytest.mark.freeze_time(START)
async def test_report_leaves_out_a_unit_glitch(hass: HomeAssistant) -> None:
    """The meter reported Wh as kWh for a moment: 107 -> 109851.5 -> 110.131
    kWh, later the statistics went down by 2 kWh. Without the check the
    report would count about 110,000 kWh; a sunny hour of 8 kWh stays."""
    entry = await setup(hass)
    await meter_statistics(
        hass,
        [
            (6, 106.6),
            (7, 107.0),
            (8, 109_851.5),
            (9, 110.131),
            (10, 110.5),
            (11, 118.5),
            (12, 116.5),
            (13, 117.0),
        ],
    )
    result = await hass.services.async_call(
        DOMAIN,
        "report",
        {"config_entry_id": entry.entry_id, "start": "2026-10-24", "end": "2026-10-24"},
        blocking=True,
        return_response=True,
    )
    assert result["gaps"]["hours_implausible"] == {
        "count": 3,
        "hours": [
            "2026-10-24T10:00:00+02:00",
            "2026-10-24T11:00:00+02:00",
            "2026-10-24T14:00:00+02:00",
        ],
    }
    # 0.4 + 0.369 + 8 + 0.5 kWh; prices unknown before the setup: paid.
    assert result["energy_paid_kwh"] + result["energy_unpaid_kwh"] == pytest.approx(
        9.269
    )
