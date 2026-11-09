"""The card: the websocket command hands it the windows of today and
tomorrow and the repair issues, and the integration serves the card file
itself."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component

from custom_components.einspeisewacht.const import DOMAIN

from .test_init import setup

# Morning of the day the price fixture starts with (25 and 26 October 2026).
MORNING = datetime(2026, 10, 25, 6, 0, tzinfo=UTC)


# Frozen from the start: the access token of the client is issued at the
# frozen time, not later (it would be invalid then).
@pytest.mark.freeze_time(MORNING)
async def test_windows_and_issues_for_the_card(
    hass: HomeAssistant, hass_ws_client
) -> None:
    assert await async_setup_component(hass, "websocket_api", {})
    # The entry first: the client starts the web server, whose router takes
    # no new paths (the card file) afterwards.
    entry = await setup(hass)
    client = await hass_ws_client(hass)
    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)

    await client.send_json(
        {"id": 1, "type": "einspeisewacht/card", "device_id": device.id}
    )
    reply = await client.receive_json()
    assert reply["success"]
    today, tomorrow = reply["result"]["days"]
    assert (today["day"], tomorrow["day"]) == ("2026-10-25", "2026-10-26")
    assert today["known"] and tomorrow["known"]
    # The fixture has negative prices early on the 25th.
    assert today["windows"]
    first = today["windows"][0]
    assert set(first) == {"start", "end", "paid"}
    assert first["start"] < first["end"]
    assert reply["result"]["issues"] == []

    ir.async_create_issue(
        hass,
        DOMAIN,
        f"rule_changed_{entry.entry_id}",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="rule_changed",
    )
    await client.send_json(
        {"id": 2, "type": "einspeisewacht/card", "device_id": device.id}
    )
    reply = await client.receive_json()
    assert reply["result"]["issues"] == ["rule_changed"]

    # An ignored issue is left out.
    ir.async_ignore_issue(hass, DOMAIN, f"rule_changed_{entry.entry_id}", True)
    await client.send_json(
        {"id": 3, "type": "einspeisewacht/card", "device_id": device.id}
    )
    reply = await client.receive_json()
    assert reply["result"]["issues"] == []

    await client.send_json(
        {"id": 4, "type": "einspeisewacht/card", "device_id": "nope"}
    )
    reply = await client.receive_json()
    assert not reply["success"]
    assert reply["error"]["code"] == "not_found"


async def test_card_file_is_served(hass: HomeAssistant, hass_client) -> None:
    """The integration serves its card file itself."""
    assert await async_setup_component(hass, "http", {})
    await setup(hass)
    client = await hass_client()
    response = await client.get("/einspeisewacht/einspeisewacht-card.js")
    assert response.status == 200
    assert "einspeisewacht-card-editor" in await response.text()
