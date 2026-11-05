"""The report for a bug report: plain text, empty sections left out, only
whitelisted settings, no dates of the plant to the day."""

from __future__ import annotations

from custom_components.einspeisewacht.button import settings
from custom_components.einspeisewacht.issue_report import issue_key, render
from custom_components.einspeisewacht.issue_report import settings as lines
from tests.ha.conftest import METER, PRICE, entry_data


def test_render_sections_and_lines() -> None:
    text = render(
        "Einspeisewacht 0.1.6, Home Assistant 2026.11.0",
        [
            ("entry", [("regime", "quarter_hour")]),
            ("sources", []),
            ("settings", lines({"rates": [7.94], "power_kw": 8.5})),
        ],
    )
    assert text == (
        "Einspeisewacht 0.1.6, Home Assistant 2026.11.0\n"
        "\n"
        "[entry]\n"
        "regime: quarter_hour\n"
        "\n"
        "[settings]\n"
        "power_kw: 8.5\n"
        "rates: [7.94]"
    )


def test_settings_whitelist() -> None:
    data = entry_data(meter_previous=["sensor.old_export"])
    text = render("", [("settings", lines(settings(data)))])
    assert text.splitlines()[3:] == [
        "backfill_smard: False",
        "commissioned: 2025-06",
        "feed_in_type: partial",
        "override: auto",
        "override_date: None",
        "power_kw: 8.5",
        "rate_mode: single",
        "rates: [7.94]",
        "smart_meter: True",
        "smart_meter_date: 2025-06",
    ]
    for private in ("Dach", METER, PRICE, "sensor.old_export", "2025-06-15"):
        assert private not in text
    assert (
        settings(entry_data(smart_meter=False, smart_meter_date=None))[
            "smart_meter_date"
        ]
        is None
    )


def test_issue_key_prefix_and_suffix() -> None:
    assert issue_key("price_missing_abc", "abc") == "price_missing"
    assert issue_key("abc_missing_entity", "abc") == "missing_entity"
    assert issue_key("price_missing_xabc", "abc") is None
    assert issue_key("price_missing_def", "abc") is None
