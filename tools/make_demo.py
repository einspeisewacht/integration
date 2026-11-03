#!/usr/bin/env python3
"""Build the data of the demo (docs/demo/): made-up plants and prices, real logic.

Usage (from the repo root):
    uv run tools/make_demo.py

Everything here is invented: the weather, two 9.8 kWp plants, their feed-in
and the day-ahead prices. The integration's own code books them quarter hour
by quarter hour from 1 January 2026 (`Engine`, `derive`/`rule_for`,
`extension`, `negative_windows`, `build_report`), as in Home Assistant.

The page shows two moments (a sunny Sunday in May, a grey day in January) and
the year so far; for each moment the files hold what the dashboard card, the
devices, the calendar and the README's "day before" automation would show.
"""

from __future__ import annotations

import json
import math
import random
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from custom_components.einspeisewacht.catchup import extension  # noqa: E402
from custom_components.einspeisewacht.const import BERLIN  # noqa: E402
from custom_components.einspeisewacht.engine import Engine  # noqa: E402
from custom_components.einspeisewacht.ledger import FeedInValuation  # noqa: E402
from custom_components.einspeisewacht.meter import MeterTracker  # noqa: E402
from custom_components.einspeisewacht.prices import ParsedPrices  # noqa: E402
from custom_components.einspeisewacht.regime import (  # noqa: E402
    Plant,
    derive,
    local_midnight,
    rule_for,
    shadow_needed,
)
from custom_components.einspeisewacht.report import build_report  # noqa: E402
from custom_components.einspeisewacht.rules import NegativeQuarterHour  # noqa: E402
from custom_components.einspeisewacht.timeslots import QUARTER  # noqa: E402
from custom_components.einspeisewacht.windows import negative_windows  # noqa: E402

OUT = ROOT / "docs" / "demo" / "data"

START = datetime(2026, 1, 1, tzinfo=BERLIN)
END = datetime(2026, 11, 1, tzinfo=BERLIN)
MOMENTS = {
    "mai": datetime(2026, 5, 17, 14, 0, tzinfo=BERLIN),  # a sunny Sunday
    "januar": datetime(2026, 1, 28, 12, 0, tzinfo=BERLIN),  # a grey Wednesday
}
SUNNY = {date(2026, 5, 16), date(2026, 5, 17)}
GREY = {date(2026, 1, 27), date(2026, 1, 28)}

RATE_CT = 7.86  # example rate, ct/kWh
KWP = 9.8
# key: (device name, plant)
PLANTS = {
    "dach": ("Dach", Plant(date(2025, 9, 15), KWP, date(2025, 9, 15))),
    "garage": ("Garage", Plant(date(2025, 6, 20), KWP, None)),
}
LEAD = timedelta(hours=12)  # README "Hinweis am Vortag": offset -12:00:00


# ---- Made-up weather, prices and feed-in -----------------------------------------------


def _winter(day: date) -> float:
    """1 in mid January, -1 in mid July."""
    return math.cos(2 * math.pi * (day.timetuple().tm_yday - 15) / 365)


def _bump(hour: float, centre: float, width: float) -> float:
    return math.exp(-((hour - centre) ** 2) / width)


def weather(rng: random.Random) -> dict[date, float]:
    """Sunshine per day, 0 (overcast) to 1 (clear); sunnier in summer."""
    sun: dict[date, float] = {}
    day = START.date()
    level = 0.5
    while day < END.date():
        summer = (1 - _winter(day)) / 2
        level = 0.55 * level + 0.45 * rng.betavariate(1 + 3 * summer, 2.5 - summer)
        sun[day] = 0.97 if day in SUNNY else 0.12 if day in GREY else level
        day += timedelta(days=1)
    return sun


def _solar(local: datetime, sun: float) -> float:
    """Clear-sky share 0..1 at this time, times the day's sunshine."""
    day = local.date()
    hour_utc = local.astimezone(UTC).hour + local.minute / 60
    half = 6.0 - 2.1 * _winter(day)  # half day length: 3.9 h in Jan, 8.1 h in Jun
    x = (hour_utc - 11.3) / half
    if abs(x) >= 1:
        return 0.0
    season = 0.4 + 0.6 * (1 - _winter(day)) / 2
    return math.cos(x * math.pi / 2) ** 1.4 * season * (0.12 + 0.88 * sun)


def prices(sun: dict[date, float], rng: random.Random) -> dict[datetime, float]:
    """Day-ahead price per quarter hour (EUR/kWh): sunny middays go negative."""
    result: dict[datetime, float] = {}
    slot = START.astimezone(UTC)
    wind = 0.0
    day = None
    while slot < END.astimezone(UTC):
        local = slot.astimezone(BERLIN)
        if local.date() != day:
            day = local.date()
            wind = 0.6 * wind + rng.gauss(0, 0.018)
        hour = local.hour + local.minute / 60
        weekend = local.weekday() >= 5
        w = _winter(local.date())
        price = (
            0.098
            + 0.025 * w
            - (0.014 if weekend else 0.0)
            - 0.018 * _bump(hour, 3.5, 4.0)
            + (0.4 if weekend else 1.0) * 0.03 * _bump(hour, 7.8, 1.2)
            + 0.06 * _bump(hour, 19.2, 2.5)
            - 0.105 * _solar(local, sun[local.date()]) * (1.25 if weekend else 1.0)
            - wind
            + rng.gauss(0, 0.004)
        )
        result[slot] = round(price, 5)
        slot += QUARTER
    return result


def feed_in(sun: dict[date, float], rng: random.Random) -> dict[datetime, float]:
    """kWh fed into the grid per quarter hour: PV minus own use."""
    result: dict[datetime, float] = {}
    slot = START.astimezone(UTC)
    while slot < END.astimezone(UTC):
        local = slot.astimezone(BERLIN)
        pv = KWP * 0.82 * _solar(local, sun[local.date()]) * (0.9 + 0.2 * rng.random())
        own = 0.25 + 0.3 * rng.random()
        result[slot] = round(max(0.0, pv - own) * 0.25, 4)
        slot += QUARTER
    return result


# ---- Booking with the integration's engine ---------------------------------------------


def _day_prices(all_prices: dict[datetime, float], day: date) -> dict[datetime, float]:
    """The price sensor's forecast at midnight: today and tomorrow."""
    a = local_midnight(day).astimezone(UTC)
    b = local_midnight(day + timedelta(days=2)).astimezone(UTC)
    return {s: p for s, p in all_prices.items() if a <= s < b}


def _totals(engine: Engine) -> dict[str, float]:
    return dict(engine.ledger.totals)


def snapshot(
    name: str,
    plant: Plant,
    engine: Engine,
    now: datetime,
    midnights: dict[date, dict[str, float]],
    all_prices: dict[datetime, float],
    energy: dict[datetime, float],
) -> dict[str, Any]:
    """What Home Assistant shows at this moment."""
    derived = derive(plant)
    shadow = shadow_needed(derived, now.date())
    totals = _totals(engine)
    today = now.date()

    def since(day: date) -> dict[str, float]:
        start = midnights.get(day, {})
        return {
            k: round(totals.get(k, 0.0) - start.get(k, 0.0), 4)
            for k in (
                "energy_paid",
                "energy_unpaid",
                "revenue",
                "revenue_lost",
                "shadow_energy_unpaid",
                "shadow_revenue_lost",
            )
        }

    days = []
    for back in range(29, -1, -1):
        day = today - timedelta(days=back)
        start = midnights.get(day, {})
        end = midnights.get(day + timedelta(days=1), totals)
        days.append(
            {
                "date": day.isoformat(),
                "paid": round(end.get("energy_paid", 0) - start.get("energy_paid", 0), 3),
                "unpaid": round(end.get("energy_unpaid", 0) - start.get("energy_unpaid", 0), 3),
            }
        )  # fmt: skip
    utc_now = now.astimezone(UTC)
    curve = []
    slot = local_midnight(today).astimezone(UTC)
    while slot < local_midnight(today + timedelta(days=1)).astimezone(UTC):
        price = all_prices[slot]
        curve.append(
            {
                "t": slot.isoformat(),
                "ct": round(price * 100, 2),
                "kwh": round(energy[slot], 4) if slot < utc_now else None,
                "paid": engine.rule.is_paid(slot, price),
            }
        )
        slot += QUARTER
    windows = negative_windows(_day_prices(all_prices, today), engine.rule)
    calendar = [
        {
            "start": w.start.isoformat(),
            "end": w.end.isoformat(),
            "paid": w.paid,
            "lowest_ct": round(w.lowest_price * 100, 2),
        }
        for w in windows
    ]
    # README "Hinweis am Vortag": 12 h before each window without remuneration.
    pushes = []
    yesterday = _day_prices(all_prices, today - timedelta(days=1))
    for w in negative_windows(yesterday | _day_prices(all_prices, today), engine.rule):
        at = w.start - LEAD
        if not w.paid and utc_now - timedelta(hours=36) < at <= utc_now:
            pushes.append({"at": at.isoformat(), "start": w.start.isoformat(), "end": w.end.isoformat()})  # fmt: skip
    year = now.year
    result: dict[str, Any] = {
        "now": now.isoformat(),
        "device": name,
        "rule": derived.regime.value,
        "applies_from": derived.applies_from.isoformat() if derived.applies_from else None,
        "paid_now": engine.paid_now(utc_now),
        "totals": {k: round(v, 3) for k, v in totals.items()},
        "today": since(today),
        "year": since(date(year, 1, 1)),
        "negative_quarter_hours": engine.counts().get(year, 0),
        "shadow": shadow,
        "days": days,
        "curve": curve,
        "calendar": calendar,
        "pushes": sorted(pushes, key=lambda p: p["at"], reverse=True),
    }  # fmt: skip
    if shadow:
        result["shadow_negative_quarter_hours"] = engine.shadow_counts().get(year, 0)
    else:
        ext = extension(plant.commissioned, engine.counts())
        result["catch_up"] = {
            "full_load_quarter_hours": ext.full_load_quarter_hours,
            "regular_end": ext.regular_end.isoformat(),
            "extended_end": ext.extended_end.isoformat(),
            "months": [
                {"month": m.strftime("%Y-%m"), "quarter_hours": used}
                for m, used in ext.months
            ],
        }
    return result


def main() -> None:
    rng = random.Random(51)  # § 51 EEG
    sun = weather(rng)
    all_prices = prices(sun, rng)
    energy = feed_in(sun, rng)
    OUT.mkdir(parents=True, exist_ok=True)
    for key, (name, plant) in PLANTS.items():
        derived = derive(plant)
        engine = Engine(
            meter=MeterTracker(max_power_kw=KWP),
            valuation=FeedInValuation(
                rate=RATE_CT / 100,
                rule=rule_for(derived),
                shadow_rule=NegativeQuarterHour(),
            ),
            since=local_midnight(plant.commissioned),
        )
        reading = 2_000.0
        midnights: dict[date, dict[str, float]] = {}
        moments: dict[str, Any] = {}
        pending = sorted(MOMENTS.items(), key=lambda kv: kv[1])
        start = START.astimezone(UTC)
        engine.on_prices(
            ParsedPrices(prices=_day_prices(all_prices, START.date())), start
        )
        engine.on_meter(reading, start, start)
        hourly: dict[datetime, float] = {}
        for slot in sorted(energy):
            local = slot.astimezone(BERLIN)
            if local.hour == 0 and local.minute == 0:
                midnights[local.date()] = _totals(engine)
                engine.on_prices(ParsedPrices(prices=_day_prices(all_prices, local.date())), slot)  # fmt: skip
            end = slot + QUARTER
            reading += energy[slot]
            engine.on_meter(reading, end, end)
            engine.tick(end)
            hour = slot.replace(minute=0)
            hourly[hour] = hourly.get(hour, 0.0) + energy[slot]
            while pending and end >= pending[0][1].astimezone(UTC):
                moment, now = pending.pop(0)
                moments[moment] = snapshot(name, plant, engine, now, midnights, all_prices, energy)  # fmt: skip
        report = build_report(
            sorted(hourly.items()), START, END, engine.quarters, engine.rule, RATE_CT / 100, BERLIN
        )  # fmt: skip
        result = {
            "name": name,
            "plant": {
                "commissioned": plant.commissioned.isoformat(),
                "power_kw": plant.power_kw,
                "smart_meter_installed": plant.smart_meter_installed.isoformat()
                if plant.smart_meter_installed
                else None,
                "rate_ct": RATE_CT,
                "rule": derived.regime.value,
            },
            "moments": moments,
            "report": {
                "plant": name,
                "rule": derived.regime.value,
                "rate_ct_per_kwh": RATE_CT,
                **report,
            },
        }
        path = OUT / f"{key}.json"
        with path.open("w", encoding="utf-8", newline="\n") as file:
            json.dump(result, file, ensure_ascii=False, separators=(",", ":"))
        print(
            f"{key}: {derived.regime.value}, {report['energy_paid_kwh']:.0f} kWh vergütet, "
            f"{report['energy_unpaid_kwh']:.0f} kWh unvergütet, "
            f"{report['negative_quarter_hours']} neg. Viertelstunden, "
            f"{path.stat().st_size // 1024} KB"
        )
        for moment, view in moments.items():
            print(
                f"  {moment}: heute {view['today']}, jetzt vergütet={view['paid_now']}, "
                f"Fenster {len(view['calendar'])}, Pushes {len(view['pushes'])}, "
                f"Nachholung {view.get('catch_up', {}).get('full_load_quarter_hours')}"
            )
    negative = sum(1 for p in all_prices.values() if p < 0)
    print(f"negative Viertelstunden gesamt: {negative}")


if __name__ == "__main__":
    main()
