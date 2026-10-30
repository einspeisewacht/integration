"""Rules deciding whether feed-in during a quarter hour is remunerated.

Each rule covers one legal regime. Which rule applies to a plant (commissioning
date, size, smart meter) is decided elsewhere; the legal sources are listed in
docs/ENTWICKLUNG.md, section 2.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


class Rule(Protocol):
    """Decides per quarter hour; `price` is the day-ahead price in EUR/kWh."""

    def is_paid(self, slot: datetime, price: float) -> bool: ...


@dataclass(frozen=True)
class AlwaysPaid:
    """Plant not affected by negative prices."""

    def is_paid(self, slot: datetime, price: float) -> bool:
        return True


@dataclass(frozen=True)
class NegativeQuarterHour:
    """No remuneration for any quarter hour with a negative price (new regime).

    A price of exactly 0 is not negative. Before `applies_from` (e.g. while a
    small plant has no smart meter) everything is paid.
    """

    applies_from: datetime | None = None

    def is_paid(self, slot: datetime, price: float) -> bool:
        if self.applies_from is not None and slot < self.applies_from:
            return True
        return price >= 0


def rule_as_dict(rule: Rule) -> dict[str, Any]:
    """The rule as stored with the totals it booked."""
    if isinstance(rule, NegativeQuarterHour):
        start = rule.applies_from
        return {
            "type": "negative_quarter_hour",
            "applies_from": start.isoformat() if start else None,
        }
    if isinstance(rule, AlwaysPaid):
        return {"type": "always_paid"}
    # Saving must never fail; rule_from_dict reads it back as no rule.
    return {"type": "unknown"}


def rule_from_dict(data: Mapping[str, Any] | None) -> Rule | None:
    """The stored rule; None if none was stored (older versions) or it is unknown."""
    if not data:
        return None
    if data.get("type") == "always_paid":
        return AlwaysPaid()
    if data.get("type") == "negative_quarter_hour":
        start = data.get("applies_from")
        return NegativeQuarterHour(datetime.fromisoformat(start) if start else None)
    return None
