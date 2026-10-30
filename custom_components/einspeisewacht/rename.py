"""Follow a source entity renamed in the entity registry. Pure Python.

An entry keeps meter and price sensor as entity ids, and the meter is its
unique id. Home Assistant moves the statistics along with a renamed entity;
only these references have to follow (__init__.py). The stored last reading
names the meter too (MeterTracker.source): the earlier ids are kept, so the
reading stays the baseline instead of counting as a swapped meter.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .const import CONF_METER, CONF_METER_PREVIOUS, CONF_PRICE

# Earlier meter ids kept; only the first start after a rename needs them.
PREVIOUS_KEPT = 5


def sources(data: Mapping[str, Any]) -> set[str]:
    """Every entity id the entry reads."""
    return {e for e in (data.get(CONF_METER), data.get(CONF_PRICE)) if e}


def renamed_data(data: Mapping[str, Any], old: str, new: str) -> dict[str, Any]:
    """The entry data with `old` replaced by `new`."""
    result = dict(data)
    if data.get(CONF_PRICE) == old:
        result[CONF_PRICE] = new
    if data.get(CONF_METER) == old:
        result[CONF_METER] = new
        previous = [
            e for e in data.get(CONF_METER_PREVIOUS) or [] if e not in (old, new)
        ]
        result[CONF_METER_PREVIOUS] = [*previous, old][-PREVIOUS_KEPT:]
    return result


def renamed_unique_id(unique_id: str | None, old: str, new: str) -> str | None:
    """The unique id after the rename; None if it does not name `old`."""
    return new if unique_id == old else None
