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
SWITCH = BLUEPRINTS / "vergutung_aus_an.yaml"
CALENDAR = "calendar.dach_negative_preise"


def _blueprint(path: Path) -> Blueprint:
    return Blueprint(
        load_yaml(path),
        expected_domain="automation",
        schema=AUTOMATION_BLUEPRINT_SCHEMA,
    )


def _fields(inputs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """All inputs, also those in sections, by key; sections themselves too."""
    found: dict[str, dict[str, Any]] = {}
    for key, value in inputs.items():
        found[key] = value
        if "input" in value:
            found.update(_fields(value["input"]))
    return found


def test_blueprints_exist() -> None:
    assert [f.name for f in FILES] == [
        "hinweis_am_vortag.yaml",
        "vergutung_aus_an.yaml",
    ]


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_blueprint_is_valid(path: Path) -> None:
    meta = _blueprint(path).metadata
    assert meta["name"].startswith("Einspeisewacht")
    # The import button and HA's "re-import" use this URL.
    assert meta["source_url"] == (
        "https://github.com/einspeisewacht/integration/blob/main/"
        f"blueprints/automation/einspeisewacht/{path.name}"
    )
    assert meta["homeassistant"]["min_version"] == "2026.3.0"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_blueprint_is_bilingual(path: Path) -> None:
    """Blueprints have no translations: German and English in one text."""
    meta = _blueprint(path).metadata
    assert " / " in meta["name"]
    german, english = meta["description"].split("\n\n")
    assert "Einspeisewacht" in german
    assert "Einspeisewacht" in english
    for key, field in _fields(meta["input"]).items():
        assert " / " in field["name"], key
        if "description" in field:
            assert " / " in field["description"], key


def test_switch_keeps_its_inputs() -> None:
    """Only the texts changed: keys, defaults, triggers and actions stay."""
    raw = load_yaml(SWITCH)
    inputs = raw["blueprint"]["input"]
    assert list(inputs) == ["remunerated", "unpaid_actions", "paid_actions"]
    assert inputs["unpaid_actions"]["default"] == []
    assert inputs["paid_actions"]["default"] == []
    assert [(t["from"], t["to"], t["id"]) for t in raw["triggers"]] == [
        ("on", "off", "unpaid"),
        ("off", "on", "paid"),
    ]
    assert (raw["mode"], raw["max"]) == ("queued", 5)


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


def test_day_before_inputs() -> None:
    """Phone optional, language German by default, more actions collapsed."""
    blueprint = _blueprint(DAY_BEFORE)
    assert set(blueprint.inputs) == {
        "calendar",
        "notify_device",
        "time",
        "language",
        "extra_actions",
    }
    inputs = blueprint.metadata["input"]
    phone = inputs["notify_device"]
    assert phone["default"] == ""
    assert phone["selector"]["device"]["filter"] == [{"integration": "mobile_app"}]
    language = inputs["language"]
    assert language["default"] == "de"
    assert [o["value"] for o in language["selector"]["select"]["options"]] == [
        "de",
        "en",
    ]
    more = inputs["more"]
    assert more["collapsed"] is True
    assert more["input"]["extra_actions"]["default"] == []
    assert more["input"]["extra_actions"]["selector"] == {"action": {}}


def _event(start: str, end: str, summary: str) -> dict[str, str]:
    return {"start": start, "end": end, "summary": summary}


def _render_day_before(
    events: list[dict[str, str]],
    lang: str = "de",
    device: str | None = "Dach",
    phone: str = "phone_id",
) -> dict[str, Any] | None:
    """What the blueprint sends for these events of tomorrow (rendered by
    Home Assistant's template engine): title, message and the phone's notify
    action; None when it stays quiet. The device registry is stubbed:
    `device_name` of the calendar gives `device`, the phone is "Pixel 8"."""
    raw = load_yaml(DAY_BEFORE)
    variables, actions = raw["variables"], raw["actions"]
    stubs = {
        "device_name": lambda entity: device if entity == CALENDAR else None,
        "device_attr": lambda device_id, attr: (
            "Pixel 8" if (device_id, attr) == ("phone_id", "name") else None
        ),
    }

    async def render() -> dict[str, Any] | None:
        hass = HomeAssistant(str(Path(__file__).parent))
        await hass.config.async_set_time_zone("Europe/Berlin")
        try:
            values: dict[str, Any] = {
                "calendar": CALENDAR,
                "notify_device": phone,
                "lang": lang,
                "unpaid_titles": variables["unpaid_titles"],
            }
            for key in ("device", "head", "phone_action"):
                values[key] = Template(variables[key], hass).async_render(
                    {**values, **stubs}
                )
            values["agenda"] = {CALENDAR: {"events": events}}
            values["windows"] = Template(
                actions[1]["variables"]["windows"], hass
            ).async_render(values)
            if not Template(actions[2]["value_template"], hass).async_render(values):
                return None
            text = actions[3]["variables"]
            sent = {
                key: Template(text[key], hass).async_render(values)
                for key in ("title", "message")
            }
            # The phone gets them when one is chosen; the more actions always.
            phone_if = actions[4]
            sent["phone"] = (
                values["phone_action"]
                if Template(phone_if["if"][0]["value_template"], hass).async_render(
                    values
                )
                else None
            )
            assert phone_if["then"][0]["data"] == {
                "title": "{{ title }}",
                "message": "{{ message }}",
            }
            return sent
        finally:
            await hass.async_stop(force=True)

    return asyncio.run(render())


ONE = [
    _event(
        "2026-05-18T11:00:00+02:00",
        "2026-05-18T14:30:00+02:00",
        TEXTS["de"]["unpaid"],
    )
]
SEVERAL = [
    _event(
        "2026-10-25T04:00:00+01:00", "2026-10-25T04:15:00+01:00", TEXTS["en"]["unpaid"]
    ),
    _event(
        "2026-10-25T06:00:00+01:00", "2026-10-25T06:15:00+01:00", TEXTS["de"]["paid"]
    ),
    _event(
        "2026-10-25T14:00:00+01:00", "2026-10-25T14:30:00+01:00", TEXTS["en"]["unpaid"]
    ),
    _event(
        "2026-10-25T15:00:00+01:00", "2026-10-25T15:15:00+01:00", TEXTS["en"]["unpaid"]
    ),
]


def test_day_before_text_german() -> None:
    assert _render_day_before(ONE) == {
        "title": "Einspeisewacht · Dach: Negative Strompreise morgen",
        "message": "11:00–14:30 Uhr ohne Vergütung.",
        "phone": "notify.mobile_app_pixel_8",
    }
    assert _render_day_before(SEVERAL)["message"] == (
        "04:00–04:15, 14:00–14:30 und 15:00–15:15 Uhr ohne Vergütung."
    )


def test_day_before_text_english() -> None:
    assert _render_day_before(ONE, lang="en") == {
        "title": "Einspeisewacht · Dach: Negative electricity prices tomorrow",
        "message": "11:00–14:30 without remuneration.",
        "phone": "notify.mobile_app_pixel_8",
    }
    assert _render_day_before(SEVERAL, lang="en")["message"] == (
        "04:00–04:15, 14:00–14:30 and 15:00–15:15 without remuneration."
    )


def test_day_before_without_device_or_phone() -> None:
    """A calendar without a device: just Einspeisewacht in the title. No
    phone: only the more actions run."""
    sent = _render_day_before(ONE, device=None, phone="")
    assert sent == {
        "title": "Einspeisewacht: Negative Strompreise morgen",
        "message": "11:00–14:30 Uhr ohne Vergütung.",
        "phone": None,
    }


def test_day_before_window_up_to_midnight() -> None:
    """A window ending at midnight ends at 24:00, not 00:00."""
    late = [
        _event(
            "2026-05-18T23:00:00+02:00",
            "2026-05-19T00:00:00+02:00",
            TEXTS["de"]["unpaid"],
        )
    ]
    assert _render_day_before(late)["message"] == "23:00–24:00 Uhr ohne Vergütung."
    assert (
        _render_day_before(late, lang="en")["message"]
        == "23:00–24:00 without remuneration."
    )


def test_day_before_more_actions_get_title_and_message() -> None:
    """The more actions run last, with title and message set before."""
    actions = load_yaml(DAY_BEFORE)["actions"]
    assert set(actions[3]["variables"]) == {"title", "message"}
    assert actions[-1]["sequence"].name == "extra_actions"


def test_day_before_stays_quiet() -> None:
    """Nothing tomorrow, or only windows the rule does not apply to yet."""
    assert _render_day_before([]) is None
    paid = [
        _event(
            "2026-05-18T11:00:00+02:00",
            "2026-05-18T14:30:00+02:00",
            TEXTS["de"]["paid"],
        )
    ]
    assert _render_day_before(paid) is None
