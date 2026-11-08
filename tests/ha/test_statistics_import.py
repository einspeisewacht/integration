"""The import_statistics action against a real (in-memory) recorder."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

import pytest
from homeassistant.components.recorder import Recorder, get_instance
from homeassistant.components.recorder.models import StatisticMeanType
from homeassistant.components.recorder.statistics import (
    async_import_statistics,
    statistics_during_period,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.einspeisewacht.const import DOMAIN
from custom_components.einspeisewacht.regime import local_midnight
from custom_components.einspeisewacht.runtime import PlantRuntime
from custom_components.einspeisewacht.smard import parse_week
from custom_components.einspeisewacht.statistics_import import async_recalculate
from tests.conftest import load_fixture

from .test_init import START, entity_id, setup

LIVE_START = datetime(2026, 10, 25, 3, tzinfo=UTC)  # first quarter hour counted live
IMPORT_FROM = date(2026, 10, 24)
RATE = 0.0794
KEYS = ("energy_paid", "energy_unpaid", "revenue", "revenue_lost")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    recorder_mock: Recorder, enable_custom_integrations: None
) -> None:
    """The recorder must be prepared before hass (overrides the conftest fixture)."""


def hourly(start: datetime, end: datetime) -> list[tuple[datetime, float]]:
    # Step in UTC: local steps would skip the repeated hour on 25.10.
    hours, hour = [], start.astimezone(UTC)
    while hour < end:
        hours.append((hour, 1.0))
        hour += timedelta(hours=1)
    return hours


async def import_statistics(hass: HomeAssistant, entry_id: str) -> dict:
    return await hass.services.async_call(
        DOMAIN,
        "import_statistics",
        {"config_entry_id": entry_id, "start": IMPORT_FROM.isoformat()},
        blocking=True,
        return_response=True,
    )


async def sums(hass: HomeAssistant, statistic_id: str) -> list[tuple[datetime, float]]:
    rows = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        datetime(2026, 10, 20, tzinfo=UTC),
        None,
        {statistic_id},
        "hour",
        None,
        {"sum"},
    )
    return [
        (datetime.fromtimestamp(r["start"], UTC), r["sum"]) for r in rows[statistic_id]
    ]


@pytest.mark.freeze_time(START)
async def test_import_statistics(recorder_mock: Recorder, hass: HomeAssistant) -> None:
    entry = await setup(hass)
    ids = {key: entity_id(hass, entry, key) for key in KEYS}

    # Statistics as Home Assistant compiles them from setup on: one hour so far.
    for key, statistic_id in ids.items():
        energy = key.startswith("energy")
        async_import_statistics(
            hass,
            {
                "has_sum": True,
                "mean_type": StatisticMeanType.NONE,
                "name": None,
                "source": "recorder",
                "statistic_id": statistic_id,
                "unit_class": "energy" if energy else None,
                "unit_of_measurement": "kWh" if energy else "EUR",
            },
            [{"start": LIVE_START, "state": 0.5, "sum": 0.5}],
        )
    await async_wait_recording_done(hass)

    start = local_midnight(IMPORT_FROM)  # 23.10. 22:00 UTC
    with patch.object(
        PlantRuntime,
        "async_hourly_energy",
        return_value=(hourly(start, LIVE_START), []),
    ):
        # Without prices for the period: refused.
        with pytest.raises(ServiceValidationError) as err:
            await import_statistics(hass, entry.entry_id)
        assert err.value.translation_key == "import_prices_missing"

        # With the history from SMARD.de (as the opt-in backfill would add it).
        week = parse_week(load_fixture("smard_week_2026-10-19.json"))
        entry.runtime_data.engine.add_backfill(week, start, LIVE_START)
        result = await import_statistics(hass, entry.entry_id)
        await async_wait_recording_done(hass)

    hours = int((LIVE_START - start).total_seconds() // 3600)  # 29
    paid_id, unpaid_id = ids["energy_paid"], ids["energy_unpaid"]
    assert result["sensors"][paid_id]["hours"] == hours, (
        result,
        await sums(hass, paid_id),
    )

    paid, unpaid = await sums(hass, paid_id), await sums(hass, unpaid_id)
    added = paid[-2][1] + unpaid[-2][1]
    assert added == pytest.approx(hours)  # 1 kWh per hour, split by price
    # The series is continuous: the first compiled hour moved up by the import.
    assert paid[-1] == (LIVE_START, pytest.approx(paid[-2][1] + 0.5))
    assert paid[0][0] == start
    revenue = await sums(hass, ids["revenue"])
    assert revenue[-2][1] == pytest.approx(paid[-2][1] * RATE)

    # Nothing left to fill in.
    with pytest.raises(ServiceValidationError) as err:
        await import_statistics(hass, entry.entry_id)
    assert err.value.translation_key == "import_nothing_to_import"


@pytest.mark.freeze_time(datetime(2026, 10, 25, 3, 40, 30, tzinfo=UTC))
async def test_import_statistics_adds_the_setup_hour_before_the_setup(
    recorder_mock: Recorder, hass: HomeAssistant
) -> None:
    """Set up at 03:40: the sensors missed 03:00-03:30 of their first hour."""
    entry = await setup(hass)
    ids = {key: entity_id(hass, entry, key) for key in KEYS}
    # The sensors booked 0.5 kWh of the setup hour (0.25 paid, 0.25 not).
    for key, statistic_id in ids.items():
        energy = key.startswith("energy")
        value = 0.25 if energy else 0.25 * RATE
        async_import_statistics(
            hass,
            {
                "has_sum": True,
                "mean_type": StatisticMeanType.NONE,
                "name": None,
                "source": "recorder",
                "statistic_id": statistic_id,
                "unit_class": "energy" if energy else None,
                "unit_of_measurement": "kWh" if energy else "EUR",
            },
            [{"start": LIVE_START, "state": value, "sum": value}],
        )
    await async_wait_recording_done(hass)

    engine = entry.runtime_data.engine
    start = local_midnight(IMPORT_FROM)
    week = parse_week(load_fixture("smard_week_2026-10-19.json"))
    engine.add_backfill(week, start, engine.quarters.started)
    # The meter: 1 kWh in every hour, the setup hour included.
    with patch.object(
        PlantRuntime,
        "async_hourly_energy",
        return_value=(hourly(start, LIVE_START + timedelta(hours=1)), []),
    ):
        await import_statistics(hass, entry.entry_id)
        await async_wait_recording_done(hass)

    # 0.5 kWh before the setup: 03:00 (negative) and 03:15 (price 0).
    paid, unpaid = (
        await sums(hass, ids["energy_paid"]),
        await sums(hass, ids["energy_unpaid"]),
    )
    assert paid[-1] == (LIVE_START, pytest.approx(paid[-2][1] + 0.25 + 0.25))
    assert unpaid[-1] == (LIVE_START, pytest.approx(unpaid[-2][1] + 0.25 + 0.25))
    assert paid[-2][1] + unpaid[-2][1] == pytest.approx(29)


@pytest.mark.freeze_time(START)
async def test_import_statistics_refuses_start_after_setup(
    recorder_mock: Recorder, hass: HomeAssistant
) -> None:
    """From the setup on the sensors have statistics of their own."""
    entry = await setup(hass)
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "import_statistics",
            {"config_entry_id": entry.entry_id, "start": "2026-10-26"},
            blocking=True,
            return_response=True,
        )
    assert err.value.translation_key == "import_start_after_setup"


@pytest.mark.freeze_time(START)
async def test_import_recalculate_import_earlier_without_jump(
    recorder_mock: Recorder, hass: HomeAssistant
) -> None:
    """Import, recalculate with a new rate, import again from an earlier day:
    the first row of the first import gets the second import's total plus its
    own change (seen in Tarifwacht: a jump at that boundary), and a second
    recalculation finds nothing to change."""
    entry = await setup(hass)
    ids = {key: entity_id(hass, entry, key) for key in KEYS}
    for key, statistic_id in ids.items():
        energy = key.startswith("energy")
        value = 0.5 if energy else 0.5 * RATE
        async_import_statistics(
            hass,
            {
                "has_sum": True,
                "mean_type": StatisticMeanType.NONE,
                "name": None,
                "source": "recorder",
                "statistic_id": statistic_id,
                "unit_class": "energy" if energy else None,
                "unit_of_measurement": "kWh" if energy else "EUR",
            },
            [{"start": LIVE_START, "state": value, "sum": value}],
        )
    await async_wait_recording_done(hass)
    runtime = entry.runtime_data
    earlier = date(2026, 10, 22)
    week = parse_week(load_fixture("smard_week_2026-10-19.json"))
    runtime.engine.add_backfill(week, local_midnight(earlier), LIVE_START)

    async def import_from(day: date) -> None:
        with patch.object(
            PlantRuntime,
            "async_hourly_energy",
            return_value=(hourly(local_midnight(day), LIVE_START), []),
        ):
            await hass.services.async_call(
                DOMAIN,
                "import_statistics",
                {"config_entry_id": entry.entry_id, "start": day.isoformat()},
                blocking=True,
                return_response=True,
            )
        await async_wait_recording_done(hass)

    await import_from(IMPORT_FROM)
    new_rate = 0.10
    with patch.object(runtime, "rate_ct", new_rate * 100):
        result = await async_recalculate(hass, entry)
        assert result["rows_written"] > 0
        await async_wait_recording_done(hass)
        await import_from(earlier)
        # Recalculated once more: every row already holds the current rate.
        again = await async_recalculate(hass, entry)
        assert again["rows_written"] == 0

    paid, unpaid = (
        await sums(hass, ids["energy_paid"]),
        await sums(hass, ids["energy_unpaid"]),
    )
    assert paid[0][0] == local_midnight(earlier)
    totals = [p + u for (_, p), (_, u) in zip(paid, unpaid, strict=True)]
    # 1 kWh in every imported hour, 0.5 + 0.5 in the compiled one: no jump
    # anywhere, also not at the start of the first import (24.10. 00:00).
    steps = [b - a for a, b in zip([0.0, *totals], totals, strict=False)]
    assert len(steps) == 3 * 24 + 6
    assert steps == pytest.approx([1.0] * len(steps))
    for money, energy in (("revenue", paid), ("revenue_lost", unpaid)):
        money_sums = await sums(hass, ids[money])
        assert [s for _, s in money_sums] == pytest.approx(
            [new_rate * s for _, s in energy], abs=0.0005
        ), money
