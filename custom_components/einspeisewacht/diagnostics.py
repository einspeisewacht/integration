"""Diagnostics download (Settings > Devices & services > Einspeisewacht > ⋮).

No personal data: no plant name, no meter readings, no energy or revenue totals.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import EinspeisewachtConfigEntry
from .const import CONF_NAME, VERSION


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: EinspeisewachtConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for the config entry."""
    runtime = entry.runtime_data
    engine = runtime.engine
    parsed = engine.last_parse
    return {
        "version": VERSION,
        "config": {k: v for k, v in entry.data.items() if k != CONF_NAME},
        "regime": runtime.derived.regime.value,
        "applies_from": runtime.derived.applies_from.isoformat()
        if runtime.derived.applies_from
        else None,
        "rate_ct_per_kwh": runtime.rate_ct,
        "prices": {
            "known_quarter_hours": len(engine.prices.prices),
            "first": min(engine.prices.prices).isoformat()
            if engine.prices.prices
            else None,
            "last": max(engine.prices.prices).isoformat()
            if engine.prices.prices
            else None,
            "resolution_minutes": parsed.resolution.total_seconds() / 60
            if parsed and parsed.resolution
            else None,
            "skipped_entries": parsed.skipped if parsed else None,
        },
        "meter": {
            "unknown_unit": runtime.unknown_unit,
            "events": dict(engine.meter_events),
            "last_reading": engine.meter.last_time.isoformat()
            if engine.meter.last_time
            else None,
        },
        "ledger": {
            "pending_quarter_hours": len(engine.ledger.pending),
            "booked_without_price": engine.ledger.booked_without_price,
        },
        "quarters": {
            "next_slot": engine.quarters.next_slot.isoformat()
            if engine.quarters.next_slot
            else None,
            "counts": {str(y): c for y, c in engine.counts().items()},
            "shadow_counts": {str(y): c for y, c in engine.shadow_counts().items()},
            "negative_quarter_hours_known": len(engine.quarters.negatives),
            "missing_prices": len(engine.quarters.missing),
            "started": engine.quarters.started.isoformat()
            if engine.quarters.started
            else None,
        },
        "backfill": {
            "enabled": runtime.backfill_enabled,
            "done": engine.quarters.backfilled,
            "error": runtime.backfill_error,
            "missing_prices": runtime.backfill_missing,
        },
        "smard_fill": {
            "filled_quarter_hours": runtime.smard_filled,
            "error": runtime.smard_fill_error,
        },
    }
