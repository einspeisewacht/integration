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
    hours, hour = [], start
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
        PlantRuntime, "async_hourly_energy", return_value=hourly(start, LIVE_START)
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
    assert result["sensors"][paid_id]["hours"] == hours

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
