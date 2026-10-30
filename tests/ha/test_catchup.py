"""Extension sensors, calendar and the opt-in SMARD.de backfill."""

from __future__ import annotations

import asyncio
import copy
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.einspeisewacht.const import (
    CONF_BACKFILL,
    CONF_COMMISSIONED,
    CONF_OVERRIDE,
    CONF_OVERRIDE_DATE,
    DOMAIN,
    OVERRIDE_FROM_DATE,
)
from custom_components.einspeisewacht.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.einspeisewacht.regime import local_midnight
from custom_components.einspeisewacht.runtime import PlantRuntime
from custom_components.einspeisewacht.smard import INDEX_URL, parse_week, week_url
from tests.conftest import load_fixture

from .conftest import PRICE, price_attributes
from .test_init import START, entity_id, setup, value

WEEK = 1792360800000  # Monday 19.10.2026 00:00 CEST
NEXT_WEEK = 1792969200000  # Monday 26.10.2026 00:00 CET


@pytest.mark.freeze_time(START)
async def test_extension_and_calendar(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    entry = await setup(hass)
    assert value(hass, entry, "catch_up") == "0"
    assert value(hass, entry, "remunerated_until") == "2045-12-31"

    # Later that day new prices arrive; counting catches up to 16:00 UTC.
    freezer.move_to(datetime(2026, 10, 25, 16, tzinfo=UTC))
    hass.states.async_set(PRICE, "0.02", price_attributes())
    await hass.async_block_till_done()
    assert value(hass, entry, "negative_quarter_hours") == "6"
    assert value(hass, entry, "catch_up") == "3"  # 6 x 0.5
    assert value(hass, entry, "remunerated_until") == "2046-01-31"
    attributes = hass.states.get(entity_id(hass, entry, "catch_up")).attributes
    assert attributes["months"] == [{"month": "2046-01", "quarter_hours": 3}]

    calendar = entity_id(hass, entry, "unpaid_windows")
    response = await hass.services.async_call(
        "calendar",
        "get_events",
        {
            "entity_id": calendar,
            "start_date_time": "2026-10-25T00:00:00+02:00",
            "end_date_time": "2026-10-26T00:00:00+01:00",
        },
        blocking=True,
        return_response=True,
    )
    events = response[calendar]["events"]
    # The test instance runs in another time zone: compare moments, not strings.
    starts = [datetime.fromisoformat(e["start"]) for e in events]
    assert starts == [
        datetime.fromisoformat(f"2026-10-25T{t}:00+01:00")
        for t in ("04:00", "04:30", "06:00", "14:00", "15:00")
    ]
    assert datetime.fromisoformat(events[3]["end"]) == datetime.fromisoformat(
        "2026-10-25T14:30:00+01:00"
    )
    assert {e["summary"] for e in events} == {"No feed-in remuneration"}


@pytest.mark.freeze_time(START)
async def test_backfill_from_smard(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("custom_components.einspeisewacht.runtime.SMARD_PAUSE", 0)
    aioclient_mock.get(INDEX_URL, json=load_fixture("smard_index_quarterhour.json"))
    week = load_fixture("smard_week_2026-10-19.json")
    aioclient_mock.get(week_url(WEEK), json=week)

    changes = {
        CONF_COMMISSIONED: "2026-10-20",
        CONF_OVERRIDE: OVERRIDE_FROM_DATE,
        CONF_OVERRIDE_DATE: "2026-10-01",
        CONF_BACKFILL: True,
    }
    entry = await setup(hass, **changes)
    await hass.async_block_till_done(wait_background_tasks=True)

    # Commissioning until live counting began; the rule applies throughout.
    first, live_start = (
        local_midnight(date(2026, 10, 20)),
        datetime(2026, 10, 25, 3, tzinfo=UTC),
    )
    expected = sum(
        1
        for slot, price in parse_week(week).items()
        if first <= slot < live_start and price < 0
    )
    assert value(hass, entry, "negative_quarter_hours") == str(expected)
    assert aioclient_mock.call_count == 2
    headers = aioclient_mock.mock_calls[0][3]
    assert headers["User-Agent"].startswith("Einspeisewacht/")

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["backfill"] == {
        "enabled": True,
        "done": True,
        "error": None,
        "missing_prices": 0,
    }


@pytest.mark.freeze_time(START)
async def test_prices_from_smard_while_the_sensor_is_out(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The price sensor's forecast ends at 04:00 UTC; SMARD.de fills the gap."""
    monkeypatch.setattr("custom_components.einspeisewacht.runtime.SMARD_PAUSE", 0)
    aioclient_mock.get(INDEX_URL, json=load_fixture("smard_index_quarterhour.json"))
    week = load_fixture("smard_week_2026-10-19.json")
    aioclient_mock.get(week_url(WEEK), json=week)
    aioclient_mock.get(week_url(NEXT_WEEK), json={"series": []})
    gap = datetime(2026, 10, 25, 4, tzinfo=UTC)
    attributes = price_attributes()
    attributes["data"] = [
        e for e in attributes["data"] if datetime.fromisoformat(e["start_time"]) < gap
    ]
    monkeypatch.setattr("tests.ha.test_init.price_attributes", lambda: attributes)
    changes = {
        CONF_COMMISSIONED: "2026-10-20",
        CONF_OVERRIDE: OVERRIDE_FROM_DATE,
        CONF_OVERRIDE_DATE: "2026-10-01",
        CONF_BACKFILL: True,
    }
    entry = await setup(hass, **changes)
    await hass.async_block_till_done(wait_background_tasks=True)
    backfilled = int(value(hass, entry, "negative_quarter_hours"))
    calls = aioclient_mock.call_count

    # Quarter-hour ticks until 05:15; at 05:00 the quarter hour from 04:00 has
    # waited an hour for its price.
    moment = datetime(2026, 10, 25, 3, 15, 1, tzinfo=UTC)
    while moment <= datetime(2026, 10, 25, 5, 15, 1, tzinfo=UTC):
        freezer.move_to(moment)
        async_fire_time_changed(hass, moment)
        await hass.async_block_till_done(wait_background_tasks=True)
        moment += timedelta(minutes=15)

    # 03:00 and 03:30 from the sensor, 05:00 (negative) from SMARD.de.
    assert value(hass, entry, "negative_quarter_hours") == str(backfilled + 3)
    assert aioclient_mock.call_count == calls + 3  # index and two weeks, once
    # The sensor is still broken: the repair issue stays.
    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"price_missing_{entry.entry_id}"
    )
    assert issue is not None
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["smard_fill"]["filled_quarter_hours"] > 0


@pytest.mark.freeze_time(START)
async def test_backfill_failure_raises_issue(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(INDEX_URL, status=503)
    entry = await setup(hass, **{CONF_BACKFILL: True})
    await hass.async_block_till_done(wait_background_tasks=True)

    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"smard_failed_{entry.entry_id}")
    assert issue is not None
    assert issue.translation_key == "smard_failed"
    # Live booking keeps working.
    assert value(hass, entry, "remunerated") == "off"
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["backfill"]["done"] is False

    # Removing the entry removes the issue.
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, f"smard_failed_{entry.entry_id}")
        is None
    )


@pytest.mark.freeze_time(START)
async def test_no_extension_sensors_while_rule_does_not_apply(
    hass: HomeAssistant,
) -> None:
    entry = await setup(hass, smart_meter=False, smart_meter_date=None)
    assert entity_id(hass, entry, "catch_up") is None
    assert entity_id(hass, entry, "remunerated_until") is None
    assert entity_id(hass, entry, "unpaid_windows") is not None


@pytest.mark.freeze_time(START)
async def test_hanging_backfill_is_cancelled_on_stop(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A SMARD.de download still running at unload is cancelled and awaited;
    the old runtime writes nothing over the files of the next one."""
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def hanging(self, start: datetime, end: datetime) -> dict:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return {}

    monkeypatch.setattr(PlantRuntime, "_async_fetch_smard", hanging)
    entry = await setup(hass, **{CONF_COMMISSIONED: "2026-10-20", CONF_BACKFILL: True})
    assert started.is_set()
    runtime = entry.runtime_data
    assert runtime._tasks

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert cancelled.is_set()
    assert not runtime._tasks
    key = f"{DOMAIN}.{entry.entry_id}.history"
    saved = copy.deepcopy(hass_storage[key])

    # A late change of the stopped runtime schedules no delayed write.
    runtime.engine.negatives_version += 1
    runtime._changed()
    freezer.tick(timedelta(seconds=30))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass_storage[key] == saved
