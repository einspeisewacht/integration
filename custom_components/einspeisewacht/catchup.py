"""Extension of the remuneration period for PV (§ 51a EEG).

§ 51a Abs. 1: the period is extended by the quarter hours in which the value
dropped to zero "im Jahr der Inbetriebnahme und in den darauffolgenden 19
Kalenderjahren". § 51a Abs. 2: for solar, multiply by 0.5 and round up to full
quarter hours ("Volllastviertelstunden"); this quota is used up against monthly
amounts (Satz 3), the period ends with the month of the last one (Satz 6).
§ 25 Abs. 1 Satz 2: for statutory values the regular period runs until
31 December of the twentieth year of payment. The commissioning year is a
partial year before the twenty full ones: plants from 2000 left the scheme at
the end of 2020. Counting (commissioning year + 19) thus stops one year
before the regular period ends.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import ceil

# § 51a Abs. 2 Satz 3: full-load quarter hours per month, January to December.
MONTHLY_QUOTA: tuple[int, ...] = (
    87,
    189,
    340,
    442,
    490,
    508,
    498,
    453,
    371,
    231,
    118,
    73,
)
SOLAR_FACTOR = 0.5  # § 51a Abs. 2 Satz 1
COUNTING_YEARS = 20  # year of commissioning plus 19 calendar years


@dataclass(frozen=True)
class Extension:
    """Result for one plant."""

    negative_quarter_hours: int
    full_load_quarter_hours: int
    regular_end: date
    extended_end: date
    # (first day of month, full-load quarter hours used in it)
    months: tuple[tuple[date, int], ...]


def counted_years(commissioned: date) -> range:
    return range(commissioned.year, commissioned.year + COUNTING_YEARS)


def regular_end(commissioned: date) -> date:
    """31 December of the 20th full year after the commissioning year."""
    return date(commissioned.year + 20, 12, 31)


def extension(commissioned: date, counts: dict[int, int]) -> Extension:
    """Extension from negative quarter hours per calendar year."""
    negative = sum(counts.get(year, 0) for year in counted_years(commissioned))
    full_load = ceil(negative * SOLAR_FACTOR)
    end = regular_end(commissioned)
    months: list[tuple[date, int]] = []
    remaining = full_load
    year, month = end.year + 1, 1
    while remaining > 0:
        used = min(remaining, MONTHLY_QUOTA[month - 1])
        months.append((date(year, month, 1), used))
        remaining -= used
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    extended_end = end
    if months:
        last = months[-1][0]
        next_month = (
            date(last.year + 1, 1, 1)
            if last.month == 12
            else date(last.year, last.month + 1, 1)
        )
        extended_end = date.fromordinal(next_month.toordinal() - 1)
    return Extension(negative, full_load, end, extended_end, tuple(months))
