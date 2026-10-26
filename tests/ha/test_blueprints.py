"""The blueprint as a real automation: which actions run on which change."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.automation.config import AUTOMATION_BLUEPRINT_SCHEMA
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml
from pytest_homeassistant_custom_component.common import async_mock_service

BLUEPRINT = (
    Path(__file__).parent.parent.parent
    / "blueprints"
    / "automation"
    / "einspeisewacht"
    / "vergutung_aus_an.yaml"
)
SENSOR = "binary_sensor.dach_vergutung_aktiv"


async def test_switches_on_changes_only(hass: HomeAssistant) -> None:
    hass.states.async_set(SENSOR, "on")
    unpaid = async_mock_service(hass, "test", "unpaid")
    paid = async_mock_service(hass, "test", "paid")
    blueprint = Blueprint(
        load_yaml(BLUEPRINT),
        expected_domain="automation",
        schema=AUTOMATION_BLUEPRINT_SCHEMA,
    )
    config = BlueprintInputs(
        blueprint,
        {
            "use_blueprint": {
                "path": BLUEPRINT.name,
                "input": {
                    "remunerated": SENSOR,
                    "unpaid_actions": [{"action": "test.unpaid"}],
                    "paid_actions": [{"action": "test.paid"}],
                },
            }
        },
    ).async_substitute()
    config.pop("use_blueprint", None)
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
