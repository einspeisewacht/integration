"""Short overview of a plant entry, shown on top of "Reconfigure".

What is set up (plant, rate, rule in force today, sources, SMARD.de) and what
is missing, with its consequence. Pure Python: the texts come from the
translations (`selector.overview.options.*`), the facts about the source
entities from the caller.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from .const import (
    CONF_BACKFILL,
    CONF_COMMISSIONED,
    CONF_FEED_IN_TYPE,
    CONF_POWER,
    CONF_RATE_MODE,
    CONF_RATES,
    CONF_SMART_METER,
    CONF_SMART_METER_DATE,
    FEED_IN_FULL,
    FEED_IN_PARTIAL,
    RATE_TIERED,
)
from .regime import BLOCK_REGIMES, Derived, Regime, applies_on
from .tariff import bands

# Problems of a source entity, found by the caller.
MISSING = "missing"  # no state (removed, or not there yet)
UNIT = "unit"  # meter: unit not Wh, kWh or MWh
INVALID = "invalid"  # price: neither forecast nor numeric state
OWN = "own"  # a sensor of Einspeisewacht itself, not read


@dataclass(frozen=True)
class Source:
    """A source entity as the overview shows it."""

    name: str  # friendly name, else the entity id
    problem: str | None = None
    unit: str | None = None  # meter unit, for UNIT


def format_date(day: date | None, language: str) -> str:
    """dd.mm.yyyy in German, ISO otherwise; a dash without a date."""
    if day is None:
        return "–"
    return day.strftime("%d.%m.%Y") if language.startswith("de") else day.isoformat()


def format_number(value: float, language: str, digits: int = 3) -> str:
    """Up to `digits` decimals without trailing zeros, decimal comma in German."""
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return text.replace(".", ",") if language.startswith("de") else text


def build(
    config: Mapping[str, Any],
    derived: Derived,
    rate: float | None,
    meter: Source,
    price: Source,
    today: date,
    setup_day: date | None,
    texts: Mapping[str, str],
    language: str,
) -> str:
    """The overview as Markdown: "Set up" with a list, then "Missing" (only
    when something is missing), headed as in the sister integrations.

    `texts` maps the keys of `selector.overview.options` (and `regime_<x>`,
    `feed_in_<x>` for the labels of those selectors) to translated templates.
    """

    def text(key: str, **values: str) -> str:
        return texts.get(key, key).format(**values)

    def day(value: date | None) -> str:
        return format_date(value, language)

    commissioned = date.fromisoformat(config[CONF_COMMISSIONED])
    power = float(config[CONF_POWER])
    smard = bool(config.get(CONF_BACKFILL))
    lines = [
        text(
            "plant",
            power=format_number(power, language, 2),
            commissioned=day(commissioned),
        ),
        _rate_line(config, rate, power, text, language),
        text("rule", rule=_rule_today(config, derived, today, text, day)),
        text("meter", meter=meter.name),
        text("price", price=price.name),
        text("smard_on" if smard else "smard_off"),
    ]
    hints = _hints(config, derived, meter, price, smard, commissioned, setup_day, text)
    result = text("configured") + "\n" + "\n".join(f"- {line}" for line in lines)
    if hints:
        result += "\n\n" + text("missing") + "\n" + "\n".join(f"- {h}" for h in hints)
    return result


def _rate_line(
    config: Mapping[str, Any],
    rate: float | None,
    power: float,
    text: Any,
    language: str,
) -> str:
    if rate is None:
        return text("rate_unknown")
    shown = format_number(rate, language)
    if config.get(CONF_RATE_MODE) != RATE_TIERED:
        return text("rate_single", rate=shown)
    full = config.get(CONF_FEED_IN_TYPE) == FEED_IN_FULL
    reached = bands(power, full)
    rates = [float(r) for r in config.get(CONF_RATES) or []]
    parts = ", ".join(
        text(
            "rate_part",
            kw=format_number(min(power, upper) - lower, language, 2),
            rate=format_number(band_rate, language),
        )
        for (lower, upper), band_rate in zip(reached, rates, strict=False)
    )
    feed_in = text(f"feed_in_{FEED_IN_FULL if full else FEED_IN_PARTIAL}")
    return text("rate_tiered", rate=shown, parts=parts, feed_in=feed_in)


def _rule_today(
    config: Mapping[str, Any],
    derived: Derived,
    today: date,
    text: Any,
    day: Any,
) -> str:
    regime = derived.regime
    if derived.applies:
        key = "rule_since" if applies_on(derived, today) else "rule_from"
        result = text(key, date=day(derived.applies_from))
        if regime is Regime.MANUAL_FROM_DATE:
            return f"{result} {text('rule_manual')}"
        smart_meter = config.get(CONF_SMART_METER) and config.get(CONF_SMART_METER_DATE)
        if smart_meter and float(config[CONF_POWER]) < 100:
            installed = date.fromisoformat(config[CONF_SMART_METER_DATE])
            return f"{result} {text('rule_imsys', date=day(installed))}"
        return result
    if regime in BLOCK_REGIMES:
        return text("rule_unsupported", rule=text(f"regime_{regime.value}"))
    if regime is Regime.MANUAL_NEVER:
        return f"{text('rule_none')} {text('rule_manual')}"
    if regime is Regime.WAITING_SMART_METER:
        return text("rule_waiting")
    if regime is Regime.BELOW_2_KW:
        return text("rule_below_2_kw")
    return text("rule_not_affected")


def _hints(
    config: Mapping[str, Any],
    derived: Derived,
    meter: Source,
    price: Source,
    smard: bool,
    commissioned: date,
    setup_day: date | None,
    text: Any,
) -> list[str]:
    """What is missing, each with what it costs; only what matters."""
    hints: list[str] = []
    if meter.problem == MISSING:
        hints.append(text("hint_meter_missing", meter=meter.name))
    elif meter.problem == UNIT:
        hints.append(text("hint_meter_unit", unit=meter.unit or "–"))
    elif meter.problem == OWN:
        hints.append(text("hint_meter_own"))
    if price.problem == OWN:
        hints.append(text("hint_price_own_smard" if smard else "hint_price_own"))
    elif price.problem in (MISSING, INVALID):
        hints.append(text("hint_price_smard" if smard else "hint_price"))
    if derived.regime is Regime.WAITING_SMART_METER:
        hints.append(text("hint_imsys"))
    if (
        derived.applies
        and not smard
        and setup_day is not None
        and commissioned < setup_day
    ):
        hints.append(text("hint_smard_off"))
    return hints
