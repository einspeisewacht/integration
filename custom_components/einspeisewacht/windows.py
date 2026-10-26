"""Time windows with negative prices, for the calendar."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from .rules import Rule
from .timeslots import QUARTER


@dataclass(frozen=True)
class Window:
    """Consecutive quarter hours with a negative price and the same outcome."""

    start: datetime
    end: datetime
    paid: bool  # True: negative price, but the rule does not apply (yet)
    lowest_price: float  # EUR/kWh


def negative_windows(prices: Mapping[datetime, float], rule: Rule) -> list[Window]:
    """Merge consecutive negative quarter hours into windows, in time order."""
    windows: list[Window] = []
    for slot in sorted(prices):
        price = prices[slot]
        if price >= 0:
            continue
        paid = rule.is_paid(slot, price)
        last = windows[-1] if windows else None
        if last and last.end == slot and last.paid == paid:
            windows[-1] = Window(
                last.start, slot + QUARTER, paid, min(last.lowest_price, price)
            )
        else:
            windows.append(Window(slot, slot + QUARTER, paid, price))
    return windows
