"""Static checks for the bundled automation blueprints (run locally and in CI)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from homeassistant.components.automation.config import AUTOMATION_BLUEPRINT_SCHEMA
from homeassistant.components.blueprint.models import Blueprint
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template
from homeassistant.util.yaml import load_yaml

from custom_components.einspeisewacht.calendar import TEXTS

BLUEPRINTS = (
    Path(__file__).parent.parent / "blueprints" / "automation" / "einspeisewacht"
)
FILES = sorted(BLUEPRINTS.glob("*.yaml"))
DAY_BEFORE = BLUEPRINTS / "hinweis_am_vortag.yaml"


def test_blueprints_exist() -> None:
    assert [f.name for f in FILES] == [
        "hinweis_am_vortag.yaml",
        "vergutung_aus_an.yaml",
    ]


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_blueprint_is_valid(path: Path) -> None:
    blueprint = Blueprint(
        load_yaml(path),
        expected_domain="automation",
        schema=AUTOMATION_BLUEPRINT_SCHEMA,
    )
    meta = blueprint.metadata
    assert meta["name"].startswith("Einspeisewacht")
    # The import button and HA's "re-import" use this URL.
    assert meta["source_url"] == (
        "https://github.com/einspeisewacht/integration/blob/main/"
        f"blueprints/automation/einspeisewacht/{path.name}"
    )
    assert meta["homeassistant"]["min_version"] == "2026.3.0"


def test_day_before_knows_the_calendar_titles() -> None:
    """The titles of windows without remuneration, in both languages of the
    calendar; "still remunerated" is not among them."""
    raw = load_yaml(DAY_BEFORE)
    assert raw["variables"]["unpaid_titles"] == [
        texts["unpaid"] for texts in TEXTS.values()
    ]
    for texts in TEXTS.values():
        assert texts["paid"] not in raw["variables"]["unpaid_titles"]
    inputs = raw["blueprint"]["input"]
    assert inputs["calendar"]["selector"]["entity"]["filter"] == {
        "integration": "einspeisewacht",
        "domain": "calendar",
    }
    assert inputs["time"]["default"] == "18:00:00"


def _event(start: str, end: str, summary: str) -> dict[str, str]:
    return {"start": start, "end": end, "summary": summary}


def _render_day_before(events: list[dict[str, str]]) -> tuple[bool, Any]:
    """Whether the blueprint notifies for these events of tomorrow, and the
    text it sends (rendered by Home Assistant's template engine)."""
    actions = load_yaml(DAY_BEFORE)["actions"]
    titles = load_yaml(DAY_BEFORE)["variables"]["unpaid_titles"]

    async def render() -> tuple[bool, Any]:
        hass = HomeAssistant(str(Path(__file__).parent))
        await hass.config.async_set_time_zone("Europe/Berlin")
        try:
            agenda = {"calendar.dach_negative_preise": {"events": events}}
            windows = Template(actions[1]["variables"]["windows"], hass).async_render(
                {
                    "calendar": "calendar.dach_negative_preise",
                    "unpaid_titles": titles,
                    "agenda": agenda,
                }
            )
            notify = Template(actions[2]["value_template"], hass).async_render(
                {"windows": windows}
            )
            if not notify:
                return False, None
            return True, Template(actions[3]["message"], hass).async_render(
                {"windows": windows}
            )
        finally:
            await hass.async_stop(force=True)

    return asyncio.run(render())


def test_day_before_text() -> None:
    unpaid_de, unpaid_en = TEXTS["de"]["unpaid"], TEXTS["en"]["unpaid"]
    paid = TEXTS["de"]["paid"]
    one = [_event("2026-05-18T11:00:00+02:00", "2026-05-18T14:30:00+02:00", unpaid_de)]
    assert _render_day_before(one) == (True, "11:00–14:30 Uhr ohne Vergütung.")

    several = [
        _event("2026-10-25T04:00:00+01:00", "2026-10-25T04:15:00+01:00", unpaid_en),
        _event("2026-10-25T06:00:00+01:00", "2026-10-25T06:15:00+01:00", paid),
        _event("2026-10-25T14:00:00+01:00", "2026-10-25T14:30:00+01:00", unpaid_en),
        _event("2026-10-25T15:00:00+01:00", "2026-10-25T15:15:00+01:00", unpaid_en),
    ]
    assert _render_day_before(several) == (
        True,
        "04:00–04:15, 14:00–14:30 und 15:00–15:15 Uhr ohne Vergütung.",
    )


def test_day_before_stays_quiet() -> None:
    """Nothing tomorrow, or only windows the rule does not apply to yet."""
    assert _render_day_before([]) == (False, None)
    paid = [
        _event(
            "2026-05-18T11:00:00+02:00",
            "2026-05-18T14:30:00+02:00",
            TEXTS["de"]["paid"],
        )
    ]
    assert _render_day_before(paid) == (False, None)
