"""Buttons of the plant device.

"Recalculate statistics": the money sensors' long-term statistics with the
current rate (statistics_import.async_recalculate); the result as a
notification.

"Report for a bug report": a short report as a notification (issue_report.py).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.translation import async_get_translations

from . import EinspeisewachtConfigEntry
from .const import (
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
    DOMAIN,
    VERSION,
)
from .entity import PlantEntity
from .issue_report import Lines, build, show, utc
from .issue_report import settings as format_settings
from .prices import ParsedPrices
from .runtime import PlantRuntime
from .statistics_import import StatisticsImportError, async_recalculate

NAME = "Einspeisewacht"

# The settings in the report, a whitelist: the plant's name and the entity
# ids of meter and price sensor (also earlier ones) stay out.
SETTINGS = (
    CONF_BACKFILL,
    CONF_FEED_IN_TYPE,
    CONF_OVERRIDE,
    CONF_OVERRIDE_DATE,
    CONF_POWER,
    CONF_RATE_MODE,
    CONF_RATES,
    CONF_SMART_METER,
)
# Dates the public plant register (Marktstammdatenregister) lists next to
# the capacity: to the month only, which is all the rules need besides the
# derived regime and start.
MONTH_ONLY = (CONF_COMMISSIONED, CONF_SMART_METER_DATE)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EinspeisewachtConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([RecalculateStatistics(entry), IssueReport(entry)])


class RecalculateStatistics(PlantEntity, ButtonEntity):
    """Recalculate the money sensors' long-term statistics with the current
    rate, e.g. after the rate was corrected; the result as a notification."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: EinspeisewachtConfigEntry) -> None:
        super().__init__(entry, "recalculate_statistics")
        self._entry = entry

    async def async_press(self) -> None:
        hass, entry = self.hass, self._entry
        texts = await notification_texts(hass)
        german = (hass.config.language or "").startswith("de")
        name = entry.runtime_data.name
        try:
            result = await async_recalculate(hass, entry)
        except StatisticsImportError as err:
            title = _fill(texts["recalculate_failed_title"], name=name)
            message = _fill(texts[f"import_{err.key}"], **err.placeholders)
        else:
            title = _fill(texts["recalculated_title"], name=name)
            message = recalculated_message(hass, result, texts, german)
        persistent_notification.async_create(
            hass,
            message,
            title=title,
            notification_id=f"{DOMAIN}_recalculate_{entry.entry_id}",
        )


async def notification_texts(hass: HomeAssistant) -> dict[str, str]:
    """The notification's texts in the user's language: kept with the
    action's error messages (category "exceptions" of the translations)."""
    prefix = f"component.{DOMAIN}.exceptions."
    raw = await async_get_translations(
        hass, hass.config.language, "exceptions", {DOMAIN}
    )
    return {
        key.removeprefix(prefix).removesuffix(".message"): text
        for key, text in raw.items()
        if key.startswith(prefix)
    }


def _fill(text: str, **values: str) -> str:
    for key, value in values.items():
        text = text.replace(f"{{{key}}}", value)
    return text


def _moment(value: str, german: bool) -> str:
    moment = datetime.fromisoformat(value)
    return f"{moment:%d.%m.%Y %H:%M}" if german else f"{moment:%Y-%m-%d %H:%M}"


def _number(value: float, digits: int, german: bool) -> str:
    text = f"{value:+.{digits}f}"
    return text.replace(".", ",") if german else text


def recalculated_message(
    hass: HomeAssistant,
    result: Mapping[str, Any],
    texts: Mapping[str, str],
    german: bool,
) -> str:
    """What was recalculated: the period, the rate, each sensor's change of
    its sum, sensors left out."""
    sensors: Mapping[str, Mapping[str, Any]] = result["sensors"]
    rate = f"{result['rate_ct_per_kwh']:.4g}"
    parts = [
        _fill(
            texts["recalculated"],
            count=str(len(sensors)),
            start=_moment(result["start"], german),
            end=_moment(result["end"], german) if result["end"] else "-",
            rate=rate.replace(".", ",") if german else rate,
        )
    ]
    lines = []
    for entity_id, info in sensors.items():
        if info.get("change") is None:
            continue
        state = hass.states.get(entity_id)
        label = state.name if state is not None else entity_id
        lines.append(f"- {label}: {_number(info['change'], 2, german)} €")
    if lines:
        parts.append(texts["recalculated_changes"] + "\n" + "\n".join(lines))
    if result.get("skipped"):
        labels = []
        for entity_id in result["skipped"]:
            state = hass.states.get(entity_id)
            labels.append(state.name if state is not None else entity_id)
        parts.append(_fill(texts["recalculated_skipped"], sensors=", ".join(labels)))
    return "\n\n".join(parts)


class IssueReport(PlantEntity, ButtonEntity):
    """A short report to copy into a bug report, as a notification: what an
    issue needs without the diagnostics download (issue_report.py)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: EinspeisewachtConfigEntry) -> None:
        super().__init__(entry, "issue_report")
        self._entry = entry

    async def async_press(self) -> None:
        entry = self._entry
        runtime = entry.runtime_data
        report = build(
            self.hass,
            DOMAIN,
            NAME,
            VERSION,
            entry,
            mapping={"meter": runtime.meter_entity, "price": runtime.price_entity},
            extra=entry_lines(runtime),
            # No meter reading, as in the diagnostics.
            private=("meter",),
            setting_lines=format_settings(settings(entry.data)),
        )
        show(self.hass, DOMAIN, NAME, entry, report)


def settings(data: Mapping[str, Any]) -> dict[str, Any]:
    """The whitelisted settings; dates of the plant to the month."""
    shown = {key: data[key] for key in SETTINGS if key in data}
    for key in MONTH_ONLY:
        if key in data:
            shown[key] = str(data[key])[:7] if data[key] else data[key]
    return shown


def entry_lines(runtime: PlantRuntime) -> Lines:
    """Regime, prices, meter, bookings and SMARD.de: what diagnostics.py
    shows, in short."""
    engine = runtime.engine
    derived = runtime.derived
    quarters = engine.quarters
    lines: Lines = [
        ("regime", derived.regime.value),
        ("applies from", _applies_from(runtime)),
        ("rate", f"{runtime.rate_ct:.4g} ct/kWh"),
        ("prices", _prices(engine.prices.prices)),
        ("price sensor", _price_sensor(engine.last_parse)),
        (
            "meter",
            "no reading yet"
            if engine.meter.last_time is None
            else f"last reading {utc(engine.meter.last_time)}",
        ),
        ("meter events", _counts(engine.meter_events)),
        ("waiting for a price", f"{len(engine.ledger.pending)} quarter hours"),
        ("booked without a price", str(engine.ledger.booked_without_price)),
        ("negative quarter hours", _years(engine.counts())),
    ]
    if not derived.applies:
        lines.append(("if the rule applied", _years(engine.shadow_counts())))
    lines += [
        (
            "counting since",
            utc(quarters.started),
        ),
        (
            "without a price",
            f"{len(quarters.missing)} quarter hours, {len(quarters.gaps)} gaps",
        ),
        ("rule change", _rule_change(engine.rule_change)),
        ("SMARD.de", _smard(runtime)),
    ]
    if runtime.unknown_unit is not None:
        lines.append(("unknown meter unit", runtime.unknown_unit))
    return lines


def _applies_from(runtime: PlantRuntime) -> str:
    applies_from = runtime.derived.applies_from
    if applies_from is None:
        return "-"
    # Not the commissioning day itself (see MONTH_ONLY).
    if applies_from == runtime.commissioned:
        return "commissioning day"
    return applies_from.isoformat()


def _prices(prices: Mapping[datetime, float]) -> str:
    if not prices:
        return "none"
    return f"{len(prices)} quarter hours until {utc(max(prices))}"


def _price_sensor(parsed: ParsedPrices | None) -> str:
    if parsed is None:
        return "no price read yet"
    resolution = parsed.resolution
    minutes = "-" if resolution is None else f"{resolution.total_seconds() / 60:g} min"
    return f"resolution {minutes}, {parsed.skipped} entries skipped"


def _counts(counts: Mapping[Any, int]) -> str:
    """Events: `first 1, reset 2`."""
    return (
        ", ".join(f"{key} {count}" for key, count in sorted(counts.items())) or "none"
    )


def _years(counts: Mapping[Any, int]) -> str:
    """Quarter hours per year: `2025: 12, 2026: 340`."""
    return (
        ", ".join(f"{year}: {count}" for year, count in sorted(counts.items()))
        or "none"
    )


def _rule_change(change: Mapping[str, Any] | None) -> str:
    if change is None:
        return "none"
    return f"{change['quarter_hours']} quarter hours until {change.get('until') or '-'}"


def _smard(runtime: PlantRuntime) -> str:
    if not runtime.backfill_enabled:
        return "off"
    quarters = runtime.engine.quarters
    if runtime.backfill_error:
        backfill = f"backfill failed ({runtime.backfill_error})"
    elif quarters.backfilled:
        missing = runtime.backfill_missing
        backfill = "backfill done" + (f", {missing} without a price" if missing else "")
    else:
        backfill = "backfill pending"
    fill = f"{runtime.smard_filled} prices filled in"
    if runtime.smard_fill_error:
        fill += f" (last try failed: {runtime.smard_fill_error})"
    return f"{backfill}; {fill}"
