"""Negative quarter hours since commissioning, and what they cost per rule.

§ 51a Abs. 1 counts "die Anzahl der Viertelstunden, in denen sich der
anzulegende Wert nach Maßgabe des § 51 Absatz 1 ... auf null verringert hat":
independent of the plant's own feed-in, so night hours count too.

Only negative quarter hours can cost remuneration, so they are stored with
their price; how many count follows from the rule at the time of asking. A
changed rule therefore needs no new history.
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


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


def _moment(text: str | None) -> datetime | None:
    return datetime.fromisoformat(text) if text else None


@dataclass
class QuarterCounter:
    """Which quarter hours had a negative price, and which are known at all.

    Known: from `backfill_from` to `started` once backfilled (historical
    prices), and from `started` to `next_slot` (live), except `missing`
    quarter hours whose price never arrived.
    """

    next_slot: datetime | None = None
    started: datetime | None = None
    backfill_from: datetime | None = None
    backfilled: bool = False
    negatives: dict[datetime, float] = field(default_factory=dict)
    missing: set[datetime] = field(default_factory=set)

    def advance(self, now: datetime, prices: PriceTable) -> bool:
        """Record every quarter hour that ended by `now`; True if a negative one was added."""
        found = False
        current = slot_start(now)
        if self.next_slot is None or current - self.next_slot > MAX_CATCH_UP:
            # First start (or a long gap): begin with the running quarter hour.
            self.next_slot = current
            if self.started is None:
                self.started = current
            return False
        while self.next_slot < current:
            slot = self.next_slot
            price = prices.get(slot)
            if price is None:
                if now - (slot + QUARTER) < PRICE_WAIT:
                    return found  # wait for the price
                self.missing.add(slot)
            elif price < 0:
                self.negatives[slot] = price
                found = True
            self.next_slot = slot + QUARTER
        return found

    def resolve(self, prices: PriceTable) -> bool:
        """Count missing quarter hours whose price arrived late; True if a negative one was added.

        A price sensor can deliver the previous day after more than a day
        without data (EPEX Spot keeps it in its forecast attribute).
        """
        found = False
        for slot in sorted(self.missing):
            price = prices.get(slot)
            if price is None:
                continue
            self.missing.discard(slot)
            if price < 0:
                self.negatives[slot] = price
                found = True
        return found

    def add_backfill(
        self, prices: Mapping[datetime, float], start: datetime, end: datetime
    ) -> int:
        """Record historical prices from `start` to `end`; returns missing quarter hours."""
        self.negatives = {s: p for s, p in self.negatives.items() if s >= end}
        self.missing = {s for s in self.missing if s >= end}
        slot = slot_start(start)
        while slot < end:
            price = prices.get(slot)
            if price is None:
                self.missing.add(slot)
            elif price < 0:
                self.negatives[slot] = price
            slot += QUARTER
        self.backfill_from = slot_start(start)
        self.backfilled = True
        return sum(1 for s in self.missing if s < end)

    def known(self, slot: datetime) -> bool:
        """Whether the price of `slot` was seen (negative or not)."""
        if slot in self.missing or self.started is None or self.next_slot is None:
            return False
        if self.started <= slot < self.next_slot:
            return True
        return (
            self.backfilled
            and self.backfill_from is not None
            and self.backfill_from <= slot < self.started
        )

    def counts(self, rule: Rule, since: datetime, tz: tzinfo) -> dict[int, int]:
        """Quarter hours without remuneration per local calendar year."""
        result: dict[int, int] = {}
        for slot, price in self.negatives.items():
            if slot >= since and not rule.is_paid(slot, price):
                year = slot.astimezone(tz).year
                result[year] = result.get(year, 0) + 1
        return result

    def as_dict(self) -> dict[str, Any]:
        return {
            "next_slot": _iso(self.next_slot),
            "started": _iso(self.started),
            "backfill_from": _iso(self.backfill_from),
            "backfilled": self.backfilled,
            "missing": sorted(s.isoformat() for s in self.missing),
        }

    def negatives_dict(self) -> dict[str, float]:
        return {s.isoformat(): p for s, p in sorted(self.negatives.items())}

    def restore(self, data: dict[str, Any], negatives: dict[str, float] | None) -> None:
        """Pointers from the live state, negative quarter hours from the history.

        Without both (0.1.0b3 kept counts only, or the history is lost) the
        counter starts afresh.
        """
        if not data or negatives is None:
            return
        self.next_slot = _moment(data.get("next_slot"))
        self.started = _moment(data.get("started"))
        self.backfill_from = _moment(data.get("backfill_from"))
        self.backfilled = data.get("backfilled", False)
        self.negatives = {datetime.fromisoformat(s): p for s, p in negatives.items()}
        self.missing = {datetime.fromisoformat(s) for s in data.get("missing", [])}
