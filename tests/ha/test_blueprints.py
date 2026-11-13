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
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.einspeisewacht.const import (
    CONF_METER,
    CONF_NAME,
    CONF_SMART_METER,
    CONF_SMART_METER_DATE,
    DOMAIN,
)

from .conftest import METER_ATTRIBUTES, entry_data
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


WINDOWS = "04:00–04:15, 04:30–04:45, 06:00–06:15, 14:00–14:30 {} 15:00–15:15"


async def add_plant(hass: HomeAssistant, name: str) -> MockConfigEntry:
    """A second plant with its own meter."""
    meter = f"sensor.grid_export_{name.lower()}"
    hass.states.async_set(meter, "500", METER_ATTRIBUTES)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=meter,
        title=name,
        data=entry_data(**{CONF_NAME: name, CONF_METER: meter}),
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def add_phone(hass: HomeAssistant) -> str:
    """A phone of the Home Assistant app named "Phone": its notify action is
    notify.mobile_app_phone."""
    entry = MockConfigEntry(domain="mobile_app", title="Phone")
    entry.add_to_hass(hass)
    return (
        dr.async_get(hass)
        .async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={("mobile_app", "phone")},
            name="Phone",
        )
        .id
    )


@pytest.mark.parametrize(
    ("ha_language", "language", "phone", "plants", "changes", "expected"),
    [
        # One plant: no name in the title.
        (
            "de",
            "de",
            True,
            1,
            {},
            (
                "Einspeisewacht: Negative Strompreise morgen",
                WINDOWS.format("und") + " Uhr ohne Vergütung.",
            ),
        ),
        # English calendar titles, English message; two plants: the name of
        # the calendar's plant in the title.
        (
            "en",
            "en",
            True,
            2,
            {},
            (
                "Einspeisewacht · Dach: Negative electricity prices tomorrow",
                WINDOWS.format("and") + " without remuneration.",
            ),
        ),
        # English calendar titles, German message; no phone, more actions only.
        (
            "en",
            "de",
            False,
            2,
            {},
            (
                "Einspeisewacht · Dach: Negative Strompreise morgen",
                WINDOWS.format("und") + " Uhr ohne Vergütung.",
            ),
        ),
        # Without iMSys the rule does not apply yet: still remunerated, no notice.
        (
            "de",
            "de",
            True,
            1,
            {CONF_SMART_METER: False, CONF_SMART_METER_DATE: None},
            None,
        ),
    ],
    ids=["de", "en_two_plants", "en_calendar_de_message_no_phone", "rule_not_yet"],
)
@pytest.mark.freeze_time(EVENING - timedelta(minutes=1))
async def test_day_before(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    ha_language: str,
    language: str,
    phone: bool,
    plants: int,
    changes: dict[str, Any],
    expected: tuple[str, str] | None,
) -> None:
    await hass.config.async_set_time_zone("Europe/Berlin")
    hass.config.language = ha_language
    entry = await setup(hass, **changes)
    if plants == 2:
        await add_plant(hass, "Garage")
    calendar = entity_id(hass, entry, "unpaid_windows")
    assert calendar is not None
    notify = async_mock_service(hass, "notify", "mobile_app_phone")
    extra = async_mock_service(hass, "test", "extra")
    inputs: dict[str, Any] = {
        "calendar": calendar,
        "time": "18:00:00",
        "language": language,
        "extra_actions": [
            {"action": "test.extra", "data": {"message": "{{ title }}: {{ message }}"}}
        ],
    }
    if phone:
        inputs["notify_device"] = add_phone(hass)
    config = automation(DAY_BEFORE, inputs)
    assert await async_setup_component(hass, "automation", {"automation": config})
    await hass.async_block_till_done()
    assert (notify, extra) == ([], [])

    moment = EVENING + timedelta(seconds=1)
    freezer.move_to(moment)
    async_fire_time_changed(hass, moment)
    await hass.async_block_till_done()

    if expected is None:
        assert (notify, extra) == ([], [])
        return
    title, message = expected
    if phone:
        (call,) = notify
        assert call.data == {"title": title, "message": message}
    else:
        assert notify == []
    (call,) = extra
    assert call.data == {"message": f"{title}: {message}"}

    # The next evening: no negative prices on the 26th, no notice.
    moment = EVENING + timedelta(days=1, hours=1, seconds=1)  # 18:00 CET
    freezer.move_to(moment)
    async_fire_time_changed(hass, moment)
    await hass.async_block_till_done()
    assert (len(notify), len(extra)) == (1 if phone else 0, 1)
