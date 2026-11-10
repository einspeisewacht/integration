"""Overview on top of "Reconfigure": what is set up, what is missing."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from custom_components.einspeisewacht import overview
from custom_components.einspeisewacht.const import (
    CONF_BACKFILL,
    CONF_COMMISSIONED,
    CONF_FEED_IN_TYPE,
    CONF_OVERRIDE,
    CONF_OVERRIDE_DATE,
    CONF_POWER,
    CONF_RATE_MODE,
    CONF_RATES,
    CONF_SMART_METER,
    CONF_SMART_METER_DATE,
    FEED_IN_PARTIAL,
    OVERRIDE_AUTO,
    RATE_SINGLE,
    RATE_TIERED,
)
from custom_components.einspeisewacht.regime import (
    Derived,
    Plant,
    Regime,
    applies_on,
    derive,
    manual,
)
from custom_components.einspeisewacht.tariff import blended_rate

TRANSLATIONS = Path(__file__).parent.parent / "custom_components/einspeisewacht"
TODAY = date(2026, 11, 8)
METER = overview.Source("Smart Meter Einspeisung")
PRICE = overview.Source("EPEX Spot Marktpreis")


def texts(language: str) -> dict[str, str]:
    """The selector translations by the names the config flow gives them."""
    name = "strings.json" if language == "en" else f"translations/{language}.json"
    selectors = json.loads((TRANSLATIONS / name).read_text(encoding="utf-8"))[
        "selector"
    ]
    result = dict(selectors["overview"]["options"])
    for key, prefix in (("regime", "regime_"), ("feed_in_type", "feed_in_")):
        result.update({prefix + k: v for k, v in selectors[key]["options"].items()})
    return result


def config(**changes: Any) -> dict[str, Any]:
    """9 kWp from 31.07.2025 with iMSys the same day, one rate."""
    return {
        CONF_COMMISSIONED: "2025-07-31",
        CONF_POWER: 9.0,
        CONF_SMART_METER: True,
        CONF_SMART_METER_DATE: "2025-07-31",
        CONF_RATE_MODE: RATE_SINGLE,
        CONF_FEED_IN_TYPE: FEED_IN_PARTIAL,
        CONF_RATES: [7.94],
        CONF_OVERRIDE: OVERRIDE_AUTO,
        CONF_OVERRIDE_DATE: None,
        CONF_BACKFILL: True,
        **changes,
    }


def derived_of(values: dict[str, Any]) -> Derived:
    smart = values[CONF_SMART_METER_DATE] if values[CONF_SMART_METER] else None
    return derive(
        Plant(
            date.fromisoformat(values[CONF_COMMISSIONED]),
            values[CONF_POWER],
            date.fromisoformat(smart) if smart else None,
        )
    )


def build(
    values: dict[str, Any],
    language: str = "de",
    *,
    derived: Derived | None = None,
    rate: float | None = 7.94,
    meter: overview.Source = METER,
    price: overview.Source = PRICE,
    setup_day: date | None = date(2025, 10, 27),
) -> str:
    return overview.build(
        values,
        derived or derived_of(values),
        rate,
        meter,
        price,
        TODAY,
        setup_day,
        texts(language),
        language,
    )


def test_everything_set_up_german() -> None:
    assert build(config()) == (
        "**Eingerichtet**\n"
        "- **Anlage:** 9 kWp, in Betrieb seit 31.07.2025\n"
        "- **Vergütung:** 7,94 ct/kWh\n"
        "- **Regel heute:** Viertelstunden-Regel (§ 51 EEG) seit 01.01.2026"
        " (iMSys eingebaut am 31.07.2025)\n"
        "- **Einspeisezähler:** Smart Meter Einspeisung\n"
        "- **Day-Ahead-Preis:** EPEX Spot Marktpreis\n"
        "- **SMARD.de:** an – frühere Viertelstunden nachgezählt,"
        " Ersatz für fehlende Preise"
    )


def test_english_formatting() -> None:
    text = build(config(**{CONF_POWER: 9.75}), "en")
    assert "- **Plant:** 9.75 kWp, commissioned on 2025-07-31" in text
    assert "- **Remuneration:** 7.94 ct/kWh" in text
    assert "quarter-hour rule (§ 51 EEG) since 2026-01-01" in text


def test_rule_starts_next_year() -> None:
    """iMSys this year: no rule today, from 1 January."""
    values = config(**{CONF_SMART_METER_DATE: "2026-03-10"})
    assert (
        "**Regel heute:** noch keine – Viertelstunden-Regel ab 01.01.2027"
        " (iMSys eingebaut am 10.03.2026)" in build(values)
    )


def test_without_imsys_says_what_is_missing() -> None:
    values = config(**{CONF_SMART_METER: False, CONF_SMART_METER_DATE: None})
    text = build(values)
    assert "**Regel heute:** keine – greift erst ab dem 1. Januar" in text
    assert "**Was fehlt**\n- Kein iMSys eingetragen" in text


def test_tiered_rate_names_the_bands() -> None:
    values = config(
        **{CONF_POWER: 25.0, CONF_RATE_MODE: RATE_TIERED, CONF_RATES: [8.51, 7.43]}
    )
    rate = blended_rate(25, [8.51, 7.43], full_feed_in=False)
    text = build(values, rate=rate)
    assert (
        "**Vergütung:** 7,862 ct/kWh – Mischsatz nach Leistung aus"
        " 10 kW zu 8,51 ct, 15 kW zu 7,43 ct; Teileinspeisung (Überschuss)" in text
    )


@pytest.mark.parametrize(
    ("derived", "expected"),
    [
        (manual(date(2026, 5, 1)), "seit 01.05.2026 (von Hand gesetzt)"),
        (manual(None), "**Regel heute:** keine (von Hand gesetzt)"),
        (Derived(Regime.BELOW_2_KW), "keine – Anlagen unter 2 kW"),
        (Derived(Regime.NOT_AFFECTED), "keine – negative Preise kürzen"),
        (Derived(Regime.BLOCK_2021), "nicht berechnet: 4 zusammenhängend"),
    ],
)
def test_other_rules(derived: Derived, expected: str) -> None:
    assert expected in build(config(), derived=derived)


def test_no_hints_when_all_is_well() -> None:
    assert "Was fehlt" not in build(config())


@pytest.mark.parametrize(
    ("meter", "price", "smard", "expected"),
    [
        (
            overview.Source("sensor.gone", overview.MISSING),
            PRICE,
            True,
            "Einspeisezähler sensor.gone nicht gefunden – bis er wieder da ist,"
            " wird nichts gebucht.",
        ),
        (
            overview.Source("Leistung", overview.UNIT, "W"),
            PRICE,
            True,
            "Der Einspeisezähler meldet „W“",
        ),
        (
            METER,
            overview.Source("EPEX", overview.INVALID),
            False,
            "die Einspeisung wartet bis zu 24 Stunden darauf und zählt danach als"
            " vergütet. Mit SMARD.de",
        ),
        (
            METER,
            overview.Source("EPEX", overview.MISSING),
            True,
            "nach einer Stunde springt SMARD.de ein",
        ),
        (
            METER,
            overview.Source("Erlös", overview.OWN),
            False,
            "Der Preissensor ist ein Sensor von Einspeisewacht selbst",
        ),
    ],
)
def test_hints_with_consequence(
    meter: overview.Source, price: overview.Source, smard: bool, expected: str
) -> None:
    text = build(config(**{CONF_BACKFILL: smard}), meter=meter, price=price)
    assert "**Was fehlt**" in text
    assert expected in text


def test_smard_off_hint_only_when_it_costs_counting() -> None:
    """Without SMARD.de the extension misses the time before setup; only
    worth saying if the plant ran before the entry was set up."""
    values = config(**{CONF_BACKFILL: False})
    assert "erst ab der Einrichtung" in build(values)
    assert "erst ab der Einrichtung" not in build(values, setup_day=date(2025, 7, 31))
    not_affected = config(**{CONF_BACKFILL: False, CONF_COMMISSIONED: "2024-05-01"})
    assert "Was fehlt" not in build(not_affected)


def test_every_overview_key_exists_in_all_languages() -> None:
    keys = set(texts("en"))
    assert set(texts("de")) == keys
    for key in (
        "configured",
        "plant",
        "rule",
        "missing",
        "hint_smard_off",
        "rule_start",
    ):
        assert key in keys


def test_applies_on() -> None:
    later = derive(Plant(date(2025, 7, 31), 9, date(2026, 3, 10)))
    assert not applies_on(later, date(2026, 12, 31))
    assert applies_on(later, date(2027, 1, 1))
    assert not applies_on(Derived(Regime.WAITING_SMART_METER), TODAY)
    assert applies_on(manual(date(2026, 5, 1)), TODAY)
    assert not applies_on(manual(None), TODAY)


@pytest.mark.parametrize(
    ("value", "digits", "expected"),
    [(90, 0, "90"), (100, 0, "100"), (0, 0, "0"), (0.5, 3, "0,5"), (90.0, 2, "90")],
)
def test_format_number_keeps_whole_numbers(
    value: float, digits: int, expected: str
) -> None:
    assert overview.format_number(value, "de", digits) == expected
