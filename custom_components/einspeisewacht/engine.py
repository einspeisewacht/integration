"""One plant's accounting: meter, prices, ledger and quarter-hour counter.

Pure Python; the Home Assistant side (runtime.py) feeds it readings, price
forecasts and clock ticks. It stores the small, often changing live state
(`as_live_dict()`) apart from the history (`as_history_dict()`: prices and
negative quarter hours), which changes rarely: `history_version` and
`negatives_version` tell when it needs writing.

The money totals always follow the current rate (`FeedInValuation.reprice`).
The energy totals keep the rule they were booked with: moving energy from
"unpaid" to "paid" would lower a TOTAL_INCREASING sensor, which Home Assistant
takes for a meter reset. Earlier rules are kept with the quarter hour they
were replaced at (`rule_history`); while one of them judged a recorded quarter
hour unlike the current rule, `rule_change` says so (a repair issue).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from .const import BERLIN
from .ledger import FeedInValuation, Ledger
from .meter import MeterTracker, MeterUpdate
from .prices import ParsedPrices, PriceTable
from .quarters import QuarterCounter
from .rules import Rule, rule_as_dict, rule_from_dict
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
    # Spreads the energy of long gaps between readings (the sun's height).
    weight: Callable[[datetime], float] | None = None
    history_version: int = 0
    negatives_version: int = 0
    # Ticks wait for the first forecast after a start: until then a missing
    # price may only mean that the price sensor is not ready yet, and a tick
    # would give up on it (counter) or book the energy as paid (ledger).
    prices_seen: bool = False
    # Rules booked before the current one, each with the quarter hour it was
    # replaced at; dropped once nothing booked differs from the current rule.
    rule_history: list[tuple[Rule, datetime]] = field(default_factory=list)
    # Booked quarter hours an earlier rule judged unlike the current one:
    # {"until": end of that rule, "quarter_hours": n}; None if there are none.
    rule_change: dict[str, Any] | None = None

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
        update = self.meter.update(value_kwh, at, self.weight)
        if update.event is not None:
            self.meter_events[update.event] += 1
        self.ledger.book(update.pieces, self.prices, self.valuation, now)
        return update

    def on_prices(self, parsed: ParsedPrices, now: datetime) -> None:
        """A new price forecast from the price sensor."""
        self.last_parse = parsed
        self.prices_seen = True
        if self.prices.merge(parsed.prices):
            self.history_version += 1
            if self.quarters.resolve(self.prices):
                self.negatives_version += 1
        self.tick(now)

    def price_gap(self, now: datetime) -> datetime | None:
        """Earliest quarter hour still waiting for a price, if any.

        Held-back energy, the counter's next quarter hour, the running one and
        quarter hours given up on (within the price retention) all count.
        """
        current = slot_start(now)
        waiting = [s for s in self.ledger.pending if self.prices.get(s) is None]
        if (slot := self.quarters.next_slot) is not None and slot < current:
            waiting.append(slot)
        waiting.append(current)
        cutoff = current - PRICE_RETENTION
        waiting.extend(s for s in self.quarters.missing if s >= cutoff)
        return min((s for s in waiting if self.prices.get(s) is None), default=None)

    def fill_prices(self, prices: Mapping[datetime, float], now: datetime) -> int:
        """Prices from another source (SMARD.de) for quarter hours the sensor left open.

        Prices the sensor delivered are kept. Returns how many were added.
        """
        added = {s: p for s, p in prices.items() if self.prices.get(s) is None}
        if not added:
            return 0
        self.prices.merge(added)
        self.history_version += 1
        if self.quarters.resolve(self.prices):
            self.negatives_version += 1
        self.prices_seen = True
        self.tick(now)
        return len(added)

    def tick(self, now: datetime) -> None:
        """Clock tick (every quarter hour) or after new prices."""
        if not self.prices_seen:
            return
        self.ledger.retry_pending(self.prices, self.valuation, now)
        if self.quarters.advance(now, self.prices):
            self.history_version += 1
            self.negatives_version += 1
        # Prune about once a day, not every quarter hour (each prune is a write).
        cutoff = slot_start(now) - PRICE_RETENTION
        if self.prices.prices and min(self.prices.prices) < cutoff - timedelta(days=1):
            self.prices.prune(cutoff)
            self.history_version += 1

    def add_backfill(
        self, prices: dict[datetime, float], start: datetime, end: datetime
    ) -> int:
        """Historical prices before live counting; returns missing quarter hours."""
        missing = self.quarters.add_backfill(prices, start, end)
        self.history_version += 1
        self.negatives_version += 1
        return missing

    def paid_now(self, now: datetime) -> bool | None:
        """Whether feed-in is remunerated right now; None if the price is unknown."""
        slot = slot_start(now)
        price = self.prices.get(slot)
        return None if price is None else self.rule.is_paid(slot, price)

    def as_live_dict(self) -> dict[str, Any]:
        return {
            "meter": self.meter.as_dict(),
            "ledger": self.ledger.as_dict(),
            "quarters": self.quarters.as_dict(),
            "meter_events": dict(self.meter_events),
            "rule": rule_as_dict(self.rule),
            "rule_history": [
                [rule_as_dict(rule), end.isoformat()] for rule, end in self.rule_history
            ],
            "rule_change": self.rule_change,
        }

    def as_history_dict(self) -> dict[str, Any]:
        return {
            "prices": self.prices.as_dict(),
            "negatives": self.quarters.negatives_dict(),
        }

    def restore(
        self, live: dict[str, Any], history: dict[str, Any] | None = None
    ) -> None:
        if history is None:
            # Up to 0.1.0b4 everything was stored in one file.
            history = {
                "prices": live.get("prices", {}),
                "negatives": live.get("quarters", {}).get("negatives"),
            }
        self.meter.restore(live.get("meter", {}))
        self.prices.restore(history.get("prices", {}))
        self.ledger.restore(live.get("ledger", {}))
        self.valuation.reprice(self.ledger.totals)
        self.quarters.restore(live.get("quarters", {}), history.get("negatives"))
        self.meter_events = Counter(live.get("meter_events", {}))
        self._restore_rules(live)

    def _restore_rules(self, live: dict[str, Any]) -> None:
        """Which booked quarter hours an earlier rule judged unlike the current one."""
        self.rule_history = [
            (rule, datetime.fromisoformat(end))
            for data, end in live.get("rule_history", [])
            if (rule := rule_from_dict(data)) is not None
        ]
        booked = rule_from_dict(live.get("rule"))
        end = self.quarters.next_slot
        if booked is not None and booked != self.rule and end is not None:
            self.rule_history.append((booked, end))
        count, until = self.quarters.booked_unlike(self.rule_history, self.rule)
        if not count:
            # Everything booked agrees with the current rule (e.g. changed back).
            self.rule_history = []
            self.rule_change = None
            return
        self.rule_change = {
            "until": until.isoformat() if until else None,
            "quarter_hours": count,
        }
