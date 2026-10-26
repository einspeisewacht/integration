"""Count quarter hours in which the remuneration dropped to zero, per year.

§ 51a Abs. 1 counts "die Anzahl der Viertelstunden, in denen sich der
anzulegende Wert nach Maßgabe des § 51 Absatz 1 ... auf null verringert hat":
independent of the plant's own feed-in, so night hours count too.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo
from typing import Any

from .ledger import PRICE_WAIT
from .prices import PriceTable
from .rules import Rule
from .timeslots import QUARTER, slot_start

# Longer gaps (e.g. HA off for weeks) are not counted backwards.
MAX_CATCH_UP = timedelta(days=14)


@dataclass
class QuarterCounter:
    """Counts per local calendar year; `next_slot` is the next one to check."""

    next_slot: datetime | None = None
    counts: dict[int, int] = field(default_factory=dict)
    shadow_counts: dict[int, int] = field(default_factory=dict)
    skipped_without_price: int = 0

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
            return
        while self.next_slot < current:
            slot = self.next_slot
            price = prices.get(slot)
            if price is None:
                if now - (slot + QUARTER) < PRICE_WAIT:
                    return  # wait for the price
                self.skipped_without_price += 1
            else:
                year = slot.astimezone(tz).year
                if not rule.is_paid(slot, price):
                    self.counts[year] = self.counts.get(year, 0) + 1
                if not shadow_rule.is_paid(slot, price):
                    self.shadow_counts[year] = self.shadow_counts.get(year, 0) + 1
            self.next_slot = slot + QUARTER

    def as_dict(self) -> dict[str, Any]:
        return {
            "next_slot": self.next_slot.isoformat() if self.next_slot else None,
            "counts": {str(y): c for y, c in self.counts.items()},
            "shadow_counts": {str(y): c for y, c in self.shadow_counts.items()},
            "skipped_without_price": self.skipped_without_price,
        }

    def restore(self, data: dict[str, Any]) -> None:
        next_slot = data.get("next_slot")
        self.next_slot = datetime.fromisoformat(next_slot) if next_slot else None
        self.counts = {int(y): c for y, c in data.get("counts", {}).items()}
        self.shadow_counts = {
            int(y): c for y, c in data.get("shadow_counts", {}).items()
        }
        self.skipped_without_price = data.get("skipped_without_price", 0)
