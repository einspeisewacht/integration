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
        "rates: 7.94"
    )


def test_settings_whitelist() -> None:
    data = entry_data(meter_previous=["sensor.old_export"])
    text = render("", [("settings", lines(settings(data)))])
    assert text.splitlines()[3:] == [
        "backfill_smard: no",
        "commissioned: 2025-06",
        "feed_in_type: partial",
        "override: auto",
        "override_date: none",
        "power_kw: 8.5",
        "rate_mode: single",
        "rates: 7.94",
        "smart_meter: yes",
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


def test_text_and_utc() -> None:
    """Settings in plain text, not Python's spelling (same in all sister projects)."""
    from datetime import UTC, date, datetime, timedelta, timezone

    from custom_components.einspeisewacht.issue_report import text, utc

    assert text(True) == "yes"
    assert text(False) == "no"
    assert text(None) == "none"
    assert text([7.94, 8]) == "7.94, 8"
    assert text([]) == "none"
    assert text({"a": 1, "b": None}) == "a 1, b none"
    assert text(date(2026, 1, 1)) == "2026-01-01"
    assert text(0.5) == "0.5"
    moment = datetime(
        2026, 11, 7, 13, 39, 32, 639925, tzinfo=timezone(timedelta(hours=1))
    )
    assert text(moment) == utc(moment) == "2026-11-07 12:39 UTC"
    assert utc(datetime(2026, 11, 7, 12, 0, tzinfo=UTC)) == "2026-11-07 12:00 UTC"
    assert utc(None) == "-"
