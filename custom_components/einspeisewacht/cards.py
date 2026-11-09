"""The Lovelace card (frontend/einspeisewacht-card.js).

The integration serves the file itself and registers it with the frontend
as a dashboard resource (frontend_resource.py), so nobody has to add one; a
new version busts the cache by its query string. The card reads
Einspeisewacht's own entities through the entity registry (device and
translation key) and the months from the long-term statistics of the four
totals (recorder/statistics_during_period, once when the page opens). Only
the entry knows the windows without remuneration and its repair issues: the
websocket command "einspeisewacht/card" hands them out from memory.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

from .const import BERLIN, DOMAIN, VERSION
from .regime import local_midnight
from .windows import negative_windows

if TYPE_CHECKING:
    from .runtime import PlantRuntime

CARD_FILE = "einspeisewacht-card.js"
CARD_URL = f"/{DOMAIN}/{CARD_FILE}"
# The URL the frontend loads: a new version is a new URL (no stale cache).
CARD_RESOURCE_URL = f"{CARD_URL}?v={VERSION}"


async def async_setup_cards(hass: HomeAssistant) -> None:
    """Serve the card and register the websocket command; without http
    (tests) only the command. The frontend learns of the card per entry
    (frontend_resource.async_register_card)."""
    websocket_api.async_register_command(hass, ws_card)
    if getattr(hass, "http", None) is None:
        return
    from homeassistant.components.http import StaticPathConfig

    path = Path(__file__).parent / "frontend" / CARD_FILE
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(path), True)]
    )


def device_runtime(hass: HomeAssistant, device_id: str) -> PlantRuntime | None:
    """The runtime of an Einspeisewacht device; None if the device is no
    loaded entry of Einspeisewacht."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return None
    # Since HA 2026.11 a device belongs to one entry (`config_entry_id`);
    # `config_entries` warns and goes in 2027.10. Older versions only have it.
    if hasattr(device, "config_entry_id"):
        entry_ids = [device.config_entry_id] if device.config_entry_id else []
    else:
        entry_ids = list(device.config_entries)
    for entry_id in entry_ids:
        entry = hass.config_entries.async_get_entry(entry_id)
        if (
            entry is not None
            and entry.domain == DOMAIN
            and entry.state is ConfigEntryState.LOADED
        ):
            return entry.runtime_data
    return None


def card_days(runtime: PlantRuntime, now: datetime) -> list[dict[str, Any]]:
    """Today and tomorrow (German days): whether prices are known for the
    day (tomorrow's come with the day-ahead auction, about 13:00) and the
    windows with negative prices, as the calendar shows them."""
    engine = runtime.engine
    prices = engine.prices.prices
    windows = negative_windows(prices, engine.rule)
    today = now.astimezone(BERLIN).date()
    days = []
    for offset in (0, 1):
        day = today + timedelta(days=offset)
        start = local_midnight(day)
        end = local_midnight(day + timedelta(days=1))
        days.append(
            {
                "day": day.isoformat(),
                "known": any(start <= slot < end for slot in prices),
                "windows": [
                    {
                        "start": window.start.isoformat(),
                        "end": window.end.isoformat(),
                        "paid": window.paid,
                    }
                    for window in windows
                    if window.end > start and window.start < end
                ],
            }
        )
    return days


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/card", vol.Required("device_id"): str}
)
@websocket_api.callback
def ws_card(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Windows without remuneration and repair issues of an Einspeisewacht
    device for the card."""
    runtime = device_runtime(hass, msg["device_id"])
    if runtime is None:
        connection.send_error(msg["id"], "not_found", "No Einspeisewacht device")
        return
    connection.send_result(
        msg["id"],
        {
            "days": card_days(runtime, dt_util.utcnow()),
            "issues": runtime.active_issues(),
        },
    )
