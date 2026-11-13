"""The blueprints as real automations: which actions run when."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.automation.config import AUTOMATION_BLUEPRINT_SCHEMA
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.einspeisewacht.const import (
    CONF_SMART_METER,
    CONF_SMART_METER_DATE,
)

from .test_init import entity_id, setup

BLUEPRINTS = (
    Path(__file__).parent.parent.parent / "blueprints" / "automation" / "einspeisewacht"
)
BLUEPRINT = BLUEPRINTS / "vergutung_aus_an.yaml"
DAY_BEFORE = BLUEPRINTS / "hinweis_am_vortag.yaml"
SENSOR = "binary_sensor.dach_vergutung_aktiv"

# 24.10.2026 18:00 CEST, the evening before the price fixture's day with
# negative quarter hours (25.10., the day the clocks go back).
EVENING = datetime(2026, 10, 24, 16, 0, tzinfo=UTC)


def automation(path: Path, inputs: dict[str, Any]) -> dict[str, Any]:
    """The automation config a blueprint gives with these inputs."""
    blueprint = Blueprint(
        load_yaml(path),
        expected_domain="automation",
        schema=AUTOMATION_BLUEPRINT_SCHEMA,
    )
    config = BlueprintInputs(
        blueprint, {"use_blueprint": {"path": path.name, "input": inputs}}
    ).async_substitute()
    config.pop("use_blueprint", None)
    return config


async def test_switches_on_changes_only(hass: HomeAssistant) -> None:
    hass.states.async_set(SENSOR, "on")
    unpaid = async_mock_service(hass, "test", "unpaid")
    paid = async_mock_service(hass, "test", "paid")
    config = automation(
        BLUEPRINT,
        {
            "remunerated": SENSOR,
            "unpaid_actions": [{"action": "test.unpaid"}],
            "paid_actions": [{"action": "test.paid"}],
        },
    )
    assert await async_setup_component(hass, "automation", {"automation": config})
    await hass.async_block_till_done()

    hass.states.async_set(SENSOR, "off")
    await hass.async_block_till_done()
    assert (len(unpaid), len(paid)) == (1, 0)

    hass.states.async_set(SENSOR, "on")
    await hass.async_block_till_done()
    assert (len(unpaid), len(paid)) == (1, 1)

    # A restart passes through "unavailable" and "unknown": nothing runs.
    for state in ("unavailable", "off", "unknown", "on"):
        hass.states.async_set(SENSOR, state)
        await hass.async_block_till_done()
    assert (len(unpaid), len(paid)) == (1, 1)


@pytest.mark.parametrize(
    ("language", "changes", "expected"),
    [
        (
            "de",
            {},
            "04:00–04:15, 04:30–04:45, 06:00–06:15, 14:00–14:30 und 15:00–15:15 "
            "Uhr ohne Vergütung.",
        ),
        # English calendar titles, same German notification.
        (
            "en",
            {},
            "04:00–04:15, 04:30–04:45, 06:00–06:15, 14:00–14:30 und 15:00–15:15 "
            "Uhr ohne Vergütung.",
        ),
        # Without iMSys the rule does not apply yet: still remunerated, no notice.
        ("de", {CONF_SMART_METER: False, CONF_SMART_METER_DATE: None}, None),
    ],
    ids=["de", "en", "rule_not_yet"],
)
@pytest.mark.freeze_time(EVENING - timedelta(minutes=1))
async def test_day_before(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    language: str,
    changes: dict[str, Any],
    expected: str | None,
) -> None:
    await hass.config.async_set_time_zone("Europe/Berlin")
    hass.config.language = language
    entry = await setup(hass, **changes)
    calendar = entity_id(hass, entry, "unpaid_windows")
    assert calendar is not None
    notify = async_mock_service(hass, "test", "notify")
    config = automation(
        DAY_BEFORE,
        {"calendar": calendar, "notify_device": "phone", "time": "18:00:00"},
    )
    # The app's notification needs a real phone; the same title and text
    # through a test action instead.
    app = config["actions"][-1]
    assert (app["domain"], app["type"], app["device_id"]) == (
        "mobile_app",
        "notify",
        "phone",
    )
    config["actions"][-1] = {
        "action": "test.notify",
        "data": {"title": app["title"], "message": app["message"]},
    }
    assert await async_setup_component(hass, "automation", {"automation": config})
    await hass.async_block_till_done()
    assert notify == []

    moment = EVENING + timedelta(seconds=1)
    freezer.move_to(moment)
    async_fire_time_changed(hass, moment)
    await hass.async_block_till_done()

    if expected is None:
        assert notify == []
        return
    (call,) = notify
    assert call.data == {"title": "Negative Strompreise morgen", "message": expected}

    # The next evening: no negative prices on the 26th, no notice.
    moment = EVENING + timedelta(days=1, hours=1, seconds=1)  # 18:00 CET
    freezer.move_to(moment)
    async_fire_time_changed(hass, moment)
    await hass.async_block_till_done()
    assert len(notify) == 1
