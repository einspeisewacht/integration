"""Quarter-hour time slots in UTC.

All German offsets are whole hours, so flooring in UTC gives the same slot
boundaries as local time, also on DST changeover days (92 or 100 slots).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

QUARTER = timedelta(minutes=15)
_QUARTER_SECONDS = 900


def slot_start(moment: datetime) -> datetime:
    """Return the UTC start of the quarter hour containing `moment`."""
    if moment.tzinfo is None:
        raise ValueError("naive datetime")
    seconds = int(moment.timestamp()) // _QUARTER_SECONDS * _QUARTER_SECONDS
    return datetime.fromtimestamp(seconds, UTC)


def split_interval(
    start: datetime,
    end: datetime,
    energy: float,
    weight: Callable[[datetime], float] | None = None,
) -> list[tuple[datetime, float]]:
    """Distribute `energy` over the quarter hours between start and end.

    Linearly by time, or by time x `weight(middle of the piece)` (e.g. the sun's
    height) when given; a weight of zero everywhere falls back to linear.
    Returns (slot start in UTC, energy) pairs in chronological order. An empty or
    negative interval puts everything into the slot of `end`.
    """
    if end <= start:
        return [(slot_start(end), energy)]
    spans: list[tuple[datetime, float]] = []
    cursor = start
    slot = slot_start(start)
    while cursor < end:
        slot_end = slot + QUARTER
        piece_end = min(slot_end, end)
        spans.append((slot, (piece_end - cursor).total_seconds()))
        if weight is not None:
            middle = cursor + (piece_end - cursor) / 2
            spans[-1] = (slot, spans[-1][1] * max(weight(middle), 0.0))
        cursor = piece_end
        slot = slot_end
    total = sum(share for _, share in spans)
    if total <= 0:
        return split_interval(start, end, energy)
    return [(slot, energy * share / total) for slot, share in spans]
