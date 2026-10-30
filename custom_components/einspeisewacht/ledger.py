"""Book energy per quarter hour against the price of that quarter hour.

The ledger is the reusable core: it looks up prices, holds back pieces whose
price is not known yet and keeps running totals. What a booking means (feed-in
remuneration, later also purchase cost) is decided by a valuation.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from .prices import PriceTable
from .rules import Rule

# How long a piece waits for its price before it is booked without one.
PRICE_WAIT = timedelta(hours=24)

# Money totals of a feed-in valuation and the energy totals they are worth.
MONEY_TOTALS = {
    "revenue": "energy_paid",
    "revenue_lost": "energy_unpaid",
    "shadow_revenue_lost": "shadow_energy_unpaid",
}


class Valuation(Protocol):
    """Adds one piece of energy to the totals."""

    def book(
        self,
        totals: dict[str, float],
        slot: datetime,
        energy: float,
        price: float | None,
    ) -> None: ...


@dataclass
class FeedInValuation:
    """Feed-in with a fixed remuneration rate (EUR/kWh) and a rule.

    `shadow_rule` books what would be lost if the negative-price rule applied
    already (e.g. before a smart meter is installed). Without a price, a piece
    counts as paid. Only energy is added up; the money totals are always the
    energy totals times the rate (`reprice`).
    """

    rate: float
    rule: Rule
    shadow_rule: Rule

    def book(
        self,
        totals: dict[str, float],
        slot: datetime,
        energy: float,
        price: float | None,
    ) -> None:
        paid = price is None or self.rule.is_paid(slot, price)
        _add(totals, "energy_paid" if paid else "energy_unpaid", energy)
        if price is not None and not self.shadow_rule.is_paid(slot, price):
            _add(totals, "shadow_energy_unpaid", energy)
        self.reprice(totals)

    def reprice(self, totals: dict[str, float]) -> None:
        """Recompute the money totals from the energy totals at this rate.

        A plant has one rate (a single one, or one blend of capacity bands), so
        money is energy times rate: a corrected rate applies to everything
        booked since setup, not only to new bookings.
        """
        for money, energy in MONEY_TOTALS.items():
            if energy in totals:
                totals[money] = totals[energy] * self.rate
            else:
                totals.pop(money, None)


def _add(totals: dict[str, float], key: str, value: float) -> None:
    totals[key] = totals.get(key, 0.0) + value


@dataclass
class Ledger:
    """Running totals plus pieces still waiting for their price."""

    totals: dict[str, float] = field(default_factory=dict)
    # slot -> [energy, first seen]
    pending: dict[datetime, tuple[float, datetime]] = field(default_factory=dict)
    booked_without_price: int = 0

    def book(
        self,
        pieces: Iterable[tuple[datetime, float]],
        prices: PriceTable,
        valuation: Valuation,
        now: datetime,
    ) -> None:
        """Book pieces whose price is known; hold back the others."""
        for slot, energy in pieces:
            price = prices.get(slot)
            if price is None:
                if energy == 0:
                    # A night in a long gap: nothing to wait for.
                    continue
                held, since = self.pending.get(slot, (0.0, now))
                self.pending[slot] = (held + energy, since)
            else:
                valuation.book(self.totals, slot, energy, price)

    def retry_pending(
        self, prices: PriceTable, valuation: Valuation, now: datetime
    ) -> None:
        """Book held-back pieces once their price is known or the wait is over."""
        for slot, (energy, since) in sorted(self.pending.items()):
            price = prices.get(slot)
            if price is None and now - since < PRICE_WAIT:
                continue
            if price is None:
                self.booked_without_price += 1
            valuation.book(self.totals, slot, energy, price)
            del self.pending[slot]

    def as_dict(self) -> dict[str, Any]:
        return {
            "totals": dict(self.totals),
            "pending": [
                [slot.isoformat(), energy, since.isoformat()]
                for slot, (energy, since) in sorted(self.pending.items())
            ],
            "booked_without_price": self.booked_without_price,
        }

    def restore(self, data: dict[str, Any]) -> None:
        self.totals = dict(data.get("totals", {}))
        self.pending = {
            datetime.fromisoformat(slot): (energy, datetime.fromisoformat(since))
            for slot, energy, since in data.get("pending", [])
            if energy != 0  # held back by 0.1.3 and earlier
        }
        self.booked_without_price = data.get("booked_without_price", 0)
