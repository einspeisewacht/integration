"""Sensors: energy and revenue (paid/unpaid), negative quarter hours, rule."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import EinspeisewachtConfigEntry
from .catchup import Extension, extension
from .const import BERLIN
from .entity import PlantEntity
from .regime import Regime, shadow_needed
from .runtime import PlantRuntime


@dataclass(frozen=True, kw_only=True)
class TotalDescription(SensorEntityDescription):
    """A running total of the ledger."""


def _energy(key: str) -> TotalDescription:
    return TotalDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
    )


def _money(key: str) -> TotalDescription:
    # Home Assistant allows only "total" for monetary sensors.
    return TotalDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
    )


TOTALS = (
    _energy("energy_paid"),
    _energy("energy_unpaid"),
    _money("revenue"),
    _money("revenue_lost"),
)
SHADOW_TOTALS = (_energy("shadow_energy_unpaid"), _money("shadow_revenue_lost"))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EinspeisewachtConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Totals, quarter-hour count and rule; shadow values only where useful."""
    runtime = entry.runtime_data
    entities: list[SensorEntity] = [TotalSensor(entry, d) for d in TOTALS]
    entities.append(
        NegativeQuarterHoursSensor(
            entry, "negative_quarter_hours", lambda r: r.engine.counts()
        )
    )
    entities.append(ActiveRuleSensor(entry, "active_rule"))
    if runtime.derived.applies:
        # § 51a: only where negative prices can cost remuneration.
        entities.append(CatchUpSensor(entry, "catch_up"))
        entities.append(RemuneratedUntilSensor(entry, "remunerated_until"))
    if shadow_needed(runtime.derived, dt_util.now(BERLIN).date()):
        entities.extend(TotalSensor(entry, d) for d in SHADOW_TOTALS)
        entities.append(
            NegativeQuarterHoursSensor(
                entry,
                "shadow_negative_quarter_hours",
                lambda r: r.engine.shadow_counts(),
            )
        )
    _remove_stale(hass, entry, {entity.unique_id for entity in entities})
    async_add_entities(entities)


def _remove_stale(
    hass: HomeAssistant, entry: EinspeisewachtConfigEntry, provided: set[str | None]
) -> None:
    """Drop sensors this entry no longer provides.

    E.g. the shadow values after a reconfiguration or once the rule applies;
    otherwise they stay behind in the entity registry as orphans.
    """
    registry = er.async_get(hass)
    for registered in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registered.domain == "sensor" and registered.unique_id not in provided:
            registry.async_remove(registered.entity_id)


class TotalSensor(PlantEntity, SensorEntity):
    """Running total since setup (kWh or EUR)."""

    def __init__(
        self, entry: EinspeisewachtConfigEntry, description: TotalDescription
    ) -> None:
        super().__init__(entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float:
        return self.runtime.engine.ledger.totals.get(self.entity_description.key, 0.0)


class NegativeQuarterHoursSensor(PlantEntity, SensorEntity):
    """Quarter hours without remuneration in the current calendar year (§ 51a)."""

    def __init__(
        self,
        entry: EinspeisewachtConfigEntry,
        key: str,
        counts: Callable[[PlantRuntime], dict[int, int]],
    ) -> None:
        super().__init__(entry, key)
        self._counts = counts

    @property
    def native_value(self) -> int:
        return self._counts(self.runtime).get(dt_util.now(BERLIN).year, 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "years": {str(y): c for y, c in sorted(self._counts(self.runtime).items())}
        }


class ActiveRuleSensor(PlantEntity, SensorEntity):
    """The regime in use, with its start date and the rate."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: EinspeisewachtConfigEntry, key: str) -> None:
        super().__init__(entry, key)
        self._attr_options = [r.value for r in Regime]

    @property
    def native_value(self) -> str:
        return self.runtime.derived.regime.value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        applies_from = self.runtime.derived.applies_from
        return {
            "applies_from": applies_from.isoformat() if applies_from else None,
            "rate_ct_per_kwh": round(self.runtime.rate_ct, 4),
        }


def _extension(runtime: PlantRuntime) -> Extension:
    return extension(runtime.commissioned, runtime.engine.counts())


class CatchUpSensor(PlantEntity, SensorEntity):
    """Full-load quarter hours added after the regular period (§ 51a Abs. 2)."""

    @property
    def native_value(self) -> int:
        return _extension(self.runtime).full_load_quarter_hours

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        result = _extension(self.runtime)
        quarters = self.runtime.engine.quarters
        counting_since = (
            self.runtime.commissioned.isoformat()
            if quarters.backfilled
            else quarters.started.isoformat()
            if quarters.started
            else None
        )
        return {
            "negative_quarter_hours": result.negative_quarter_hours,
            "regular_end": result.regular_end.isoformat(),
            "months": [
                {"month": month.strftime("%Y-%m"), "quarter_hours": used}
                for month, used in result.months
            ],
            "counting_since": counting_since,
        }


class RemuneratedUntilSensor(PlantEntity, SensorEntity):
    """Last day of remuneration including the extension."""

    _attr_device_class = SensorDeviceClass.DATE

    @property
    def native_value(self) -> date:
        return _extension(self.runtime).extended_end
