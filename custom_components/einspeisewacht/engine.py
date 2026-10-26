"""One plant's accounting: meter, prices, ledger and quarter-hour counter.

Pure Python; the Home Assistant side (runtime.py) feeds it readings, price
forecasts and clock ticks, and stores `as_dict()`.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from .const import BERLIN
from .ledger import FeedInValuation, Ledger
from .meter import MeterTracker, MeterUpdate
from .prices import ParsedPrices, PriceTable
from .quarters import QuarterCounter
from .rules import Rule
from .timeslots import slot_start

# Prices older than this are dropped from storage (pending pieces give up
# after a day, the counter catches up for at most two weeks).
PRICE_RETENTION = timedelta(days=15)
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass
class Engine:
    """Accounting of one plant and meter."""

    meter: MeterTracker
    valuation: FeedInValuation
    prices: PriceTable = field(default_factory=PriceTable)
    ledger: Ledger = field(default_factory=Ledger)
    quarters: QuarterCounter = field(default_factory=QuarterCounter)
    meter_events: Counter[str] = field(default_factory=Counter)
    last_parse: ParsedPrices | None = None
    # Quarter hours before commissioning never count (§ 51a counts from the
    # year of commissioning; nothing is paid before it anyway).
    since: datetime = EPOCH

    @property
    def rule(self) -> Rule:
        return self.valuation.rule

    @property
    def shadow_rule(self) -> Rule:
        return self.valuation.shadow_rule

    def counts(self) -> dict[int, int]:
        """Quarter hours without remuneration per local calendar year."""
        return self.quarters.counts(self.rule, self.since, BERLIN)

    def shadow_counts(self) -> dict[int, int]:
        """The same if the quarter-hour rule applied already."""
        return self.quarters.counts(self.shadow_rule, self.since, BERLIN)

    def on_meter(self, value_kwh: float, at: datetime, now: datetime) -> MeterUpdate:
        """A new meter reading in kWh."""
        update = self.meter.update(value_kwh, at)
        if update.event is not None:
            self.meter_events[update.event] += 1
        self.ledger.book(update.pieces, self.prices, self.valuation, now)
        return update

    def on_prices(self, parsed: ParsedPrices, now: datetime) -> None:
        """A new price forecast from the price sensor."""
        self.last_parse = parsed
        self.prices.merge(parsed.prices)
        self.tick(now)

    def tick(self, now: datetime) -> None:
        """Clock tick (every quarter hour) or after new prices."""
        self.ledger.retry_pending(self.prices, self.valuation, now)
        self.quarters.advance(now, self.prices)
        self.prices.prune(slot_start(now) - PRICE_RETENTION)

    def paid_now(self, now: datetime) -> bool | None:
        """Whether feed-in is remunerated right now; None if the price is unknown."""
        slot = slot_start(now)
        price = self.prices.get(slot)
        return None if price is None else self.rule.is_paid(slot, price)

    def as_dict(self) -> dict[str, Any]:
        return {
            "meter": self.meter.as_dict(),
            "prices": self.prices.as_dict(),
            "ledger": self.ledger.as_dict(),
            "quarters": self.quarters.as_dict(),
            "meter_events": dict(self.meter_events),
        }

    def restore(self, data: dict[str, Any]) -> None:
        self.meter.restore(data.get("meter", {}))
        self.prices.restore(data.get("prices", {}))
        self.ledger.restore(data.get("ledger", {}))
        self.quarters.restore(data.get("quarters", {}))
        self.meter_events = Counter(data.get("meter_events", {}))
