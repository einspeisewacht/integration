"""The sun's height as a rough PV profile, for spreading energy over gaps."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from math import radians, sin

from astral import Observer
from astral.sun import elevation


def daylight_weight(latitude: float, longitude: float) -> Callable[[datetime], float]:
    """Weight of a moment: sine of the sun's elevation, 0 at night."""
    observer = Observer(latitude=latitude, longitude=longitude)

    def weight(moment: datetime) -> float:
        return max(0.0, sin(radians(elevation(observer, moment))))

    return weight
