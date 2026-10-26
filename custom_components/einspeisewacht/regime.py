"""Which negative-price rule applies to a PV plant (docs/ENTWICKLUNG.md, section 2).

Thresholds are "weniger als": a plant of exactly 2, 100, 400 or 500 kW is
affected. Installed capacity is aggregated per § 24 EEG; the user enters it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from .const import BERLIN
from .rules import AlwaysPaid, NegativeQuarterHour, Rule

# Solarspitzengesetz, BGBl. 2025 I Nr. 51: current § 51 for plants from this day.
NEW_REGIME_START = date(2025, 2, 25)


class Regime(StrEnum):
    """Legal regime of a plant; also the state of the "active rule" sensor."""

    QUARTER_HOUR = "quarter_hour"  # § 51 Abs. 1: every negative quarter hour
    WAITING_SMART_METER = "waiting_smart_meter"  # § 51 Abs. 2 Satz 1 Nr. 1
    BELOW_2_KW = "below_2_kw"  # § 51 Abs. 2 Satz 1 Nr. 2
    # Hour-block rules of older versions; not supported yet (stage 2).
    BLOCK_2023 = "block_2023"  # § 51 a. F. via § 100 Abs. 46: >= 400 kW
    BLOCK_2021 = "block_2021"  # EEG 2021: >= 500 kW, 4 h
    BLOCK_2016 = "block_2016"  # EEG 2021 § 100 Abs. 2 Nr. 13: >= 500 kW, 6 h
    NOT_AFFECTED = "not_affected"
    # Manual overrides.
    MANUAL_FROM_DATE = "manual_from_date"
    MANUAL_NEVER = "manual_never"


BLOCK_REGIMES = frozenset({Regime.BLOCK_2023, Regime.BLOCK_2021, Regime.BLOCK_2016})


@dataclass(frozen=True)
class Plant:
    """What the user tells about the plant."""

    commissioned: date
    power_kw: float
    smart_meter_installed: date | None = None


@dataclass(frozen=True)
class Derived:
    """The applicable regime and the first day it applies (local time)."""

    regime: Regime
    applies_from: date | None = None

    @property
    def applies(self) -> bool:
        """True if negative prices cost remuneration at some point."""
        return self.regime in (Regime.QUARTER_HOUR, Regime.MANUAL_FROM_DATE)


def derive(plant: Plant) -> Derived:
    """Derive the regime from commissioning date, size and smart meter."""
    year = plant.commissioned.year
    if plant.commissioned >= NEW_REGIME_START:
        if plant.power_kw < 2:
            return Derived(Regime.BELOW_2_KW)
        if plant.power_kw < 100:
            if plant.smart_meter_installed is None:
                return Derived(Regime.WAITING_SMART_METER)
            # Not "for periods before the end of the calendar year in which the
            # plant is equipped with a smart metering system".
            start = date(plant.smart_meter_installed.year + 1, 1, 1)
            return Derived(Regime.QUARTER_HOUR, max(start, plant.commissioned))
        return Derived(Regime.QUARTER_HOUR, plant.commissioned)
    if year >= 2023:
        return Derived(
            Regime.BLOCK_2023 if plant.power_kw >= 400 else Regime.NOT_AFFECTED
        )
    if year >= 2021:
        return Derived(
            Regime.BLOCK_2021 if plant.power_kw >= 500 else Regime.NOT_AFFECTED
        )
    if year >= 2016:
        return Derived(
            Regime.BLOCK_2016 if plant.power_kw >= 500 else Regime.NOT_AFFECTED
        )
    return Derived(Regime.NOT_AFFECTED)


def manual(from_date: date | None) -> Derived:
    """Override: every negative quarter hour from `from_date`, or never."""
    if from_date is None:
        return Derived(Regime.MANUAL_NEVER)
    return Derived(Regime.MANUAL_FROM_DATE, from_date)


def local_midnight(day: date) -> datetime:
    """Start of a local calendar day as an aware datetime."""
    return datetime(day.year, day.month, day.day, tzinfo=BERLIN)


def rule_for(derived: Derived) -> Rule:
    """The rule that books feed-in for this regime."""
    if not derived.applies:
        return AlwaysPaid()
    start = local_midnight(derived.applies_from) if derived.applies_from else None
    return NegativeQuarterHour(applies_from=start)


def shadow_needed(derived: Derived, today: date) -> bool:
    """Whether "would be lost" values add anything to the real ones.

    They do while the quarter-hour rule does not apply yet (no smart meter, a
    later start date, a manual "never"). Block regimes get their own rules.
    """
    if derived.regime in BLOCK_REGIMES or derived.regime is Regime.NOT_AFFECTED:
        return False
    if derived.regime is Regime.BELOW_2_KW:
        return False
    if not derived.applies:
        return True
    return derived.applies_from is not None and today < derived.applies_from
