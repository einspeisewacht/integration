"""Count quarter hours in which the remuneration dropped to zero, per year.

§ 51a Abs. 1 counts "die Anzahl der Viertelstunden, in denen sich der
anzulegende Wert nach Maßgabe des § 51 Absatz 1 ... auf null verringert hat":
independent of the plant's own feed-in, so night hours count too.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo
from typing import Any

from .ledger import PRICE_WAIT
from .prices import PriceTable
from .rules import Rule
from .timeslots import QUARTER, slot_start

# Longer gaps (e.g. HA off for weeks) are not counted backwards.
MAX_CATCH_UP = timedelta(days=14)


def _add(counts: dict[int, int], year: int) -> None:
    counts[year] = counts.get(year, 0) + 1


@dataclass
class QuarterCounts:
    """Quarter hours without remuneration per local calendar year."""

    counts: dict[int, int] = field(default_factory=dict)
    shadow_counts: dict[int, int] = field(default_factory=dict)
    missing_prices: int = 0

    def count(
        self, slot: datetime, price: float, rule: Rule, shadow_rule: Rule, tz: tzinfo
    ) -> None:
        year = slot.astimezone(tz).year
        if not rule.is_paid(slot, price):
            _add(self.counts, year)
        if not shadow_rule.is_paid(slot, price):
            _add(self.shadow_counts, year)


def count_range(
    prices: Mapping[datetime, float],
    start: datetime,
    end: datetime,
    rule: Rule,
    shadow_rule: Rule,
    tz: tzinfo,
) -> QuarterCounts:
    """Count the quarter hours from `start` (inclusive) to `end` (exclusive)."""
    result = QuarterCounts()
    slot = slot_start(start)
    while slot < end:
        price = prices.get(slot)
        if price is None:
            result.missing_prices += 1
        else:
            result.count(slot, price, rule, shadow_rule, tz)
        slot += QUARTER
    return result


@dataclass
class QuarterCounter:
    """Live counting; `next_slot` is the next quarter hour to check.

    `started` is the first quarter hour counted live; quarter hours before it
    can be added once from historical prices (`backfilled`).
    """

    next_slot: datetime | None = None
    started: datetime | None = None
    counts: dict[int, int] = field(default_factory=dict)
    shadow_counts: dict[int, int] = field(default_factory=dict)
    skipped_without_price: int = 0
    backfilled: bool = False

    def advance(
        self,
        now: datetime,
        prices: PriceTable,
        rule: Rule,
        shadow_rule: Rule,
        tz: tzinfo,
    ) -> None:
        """Evaluate every quarter hour that ended by `now`."""
        current = slot_start(now)
        if self.next_slot is None or current - self.next_slot > MAX_CATCH_UP:
            # First start (or a long gap): begin with the running quarter hour.
            self.next_slot = current
            if self.started is None:
                self.started = current
            return
        live = QuarterCounts(self.counts, self.shadow_counts)
        while self.next_slot < current:
            slot = self.next_slot
            price = prices.get(slot)
            if price is None:
                if now - (slot + QUARTER) < PRICE_WAIT:
                    return  # wait for the price
                self.skipped_without_price += 1
            else:
                live.count(slot, price, rule, shadow_rule, tz)
            self.next_slot = slot + QUARTER

    def add_backfill(self, result: QuarterCounts) -> None:
        """Add counts for the time before `started` (once)."""
        for year, count in result.counts.items():
            self.counts[year] = self.counts.get(year, 0) + count
        for year, count in result.shadow_counts.items():
            self.shadow_counts[year] = self.shadow_counts.get(year, 0) + count
        self.backfilled = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "next_slot": self.next_slot.isoformat() if self.next_slot else None,
            "started": self.started.isoformat() if self.started else None,
            "counts": {str(y): c for y, c in self.counts.items()},
            "shadow_counts": {str(y): c for y, c in self.shadow_counts.items()},
            "skipped_without_price": self.skipped_without_price,
            "backfilled": self.backfilled,
        }

    def restore(self, data: dict[str, Any]) -> None:
        next_slot = data.get("next_slot")
        self.next_slot = datetime.fromisoformat(next_slot) if next_slot else None
        started = data.get("started")
        self.started = datetime.fromisoformat(started) if started else None
        self.counts = {int(y): c for y, c in data.get("counts", {}).items()}
        self.shadow_counts = {
            int(y): c for y, c in data.get("shadow_counts", {}).items()
        }
        self.skipped_without_price = data.get("skipped_without_price", 0)
        self.backfilled = data.get("backfilled", False)
