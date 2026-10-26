"""Rules deciding whether feed-in during a quarter hour is remunerated.

Each rule covers one legal regime. Which rule applies to a plant (commissioning
date, size, smart meter) is decided elsewhere; the legal sources are listed in
docs/ENTWICKLUNG.md, section 2.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


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
