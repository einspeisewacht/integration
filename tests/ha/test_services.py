"""The report action."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.einspeisewacht.const import DOMAIN
from custom_components.einspeisewacht.runtime import PlantRuntime

from .conftest import PRICE, price_attributes
from .test_init import START, setup

DAY_START = datetime(2026, 10, 24, 22, tzinfo=UTC)  # 25.10.2026 00:00 local
DAY_END = datetime(2026, 10, 25, 23, tzinfo=UTC)


def hourly(kwh: float = 1.0) -> list[tuple[datetime, float]]:
    return [(DAY_START + timedelta(hours=h), kwh) for h in range(25)]


async def report(hass: HomeAssistant, **data) -> dict:
    return await hass.services.async_call(
        DOMAIN, "report", data, blocking=True, return_response=True
    )


@pytest.mark.freeze_time(START)
async def test_report(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    entry = await setup(hass)
    # The day goes by; live counting records 25.10. from 04:00 CET on.
    freezer.move_to(DAY_END)
    hass.states.async_set(PRICE, "0.0257", price_attributes())
    await hass.async_block_till_done()

    with patch.object(PlantRuntime, "_async_hourly_energy", return_value=hourly()):
        result = await report(
            hass, config_entry_id=entry.entry_id, start="2026-10-25", end="2026-10-25"
        )

    assert result["plant"] == "Dach"
    assert result["rule"] == "quarter_hour"
    assert result["energy_unpaid_kwh"] == pytest.approx(1.5)
    assert result["energy_paid_kwh"] == pytest.approx(23.5)
    assert result["negative_quarter_hours"] == 6
    assert [m["month"] for m in result["months"]] == ["2026-10"]
    assert datetime.fromisoformat(result["start"]) == DAY_START
    assert datetime.fromisoformat(result["end"]) == DAY_END
    # Before setup (00:00 CEST - 04:00 CET) prices are unknown without the SMARD option.
    quarters = entry.runtime_data.engine.quarters
    assert result["gaps"]["quarter_hours_without_price"] == 20, (
        result["gaps"],
        quarters.started,
        quarters.next_slot,
    )


@pytest.mark.freeze_time(START)
async def test_report_errors(hass: HomeAssistant) -> None:
    entry = await setup(hass)
    with pytest.raises(ServiceValidationError) as err:
        await report(hass, config_entry_id="unknown", start="2026-10-01")
    assert err.value.translation_key == "entry_not_found"

    with pytest.raises(ServiceValidationError) as err:
        await report(
            hass, config_entry_id=entry.entry_id, start="2026-10-20", end="2026-10-19"
        )
    assert err.value.translation_key == "end_before_start"

    # It is 04:00 CET on 25.10.: the 26th has no complete hour yet.
    with pytest.raises(ServiceValidationError) as err:
        await report(
            hass, config_entry_id=entry.entry_id, start="2026-10-26", end="2026-10-26"
        )
    assert err.value.translation_key == "empty_period"

    assert await hass.config_entries.async_unload(entry.entry_id)
    with pytest.raises(ServiceValidationError) as err:
        await report(hass, config_entry_id=entry.entry_id, start="2026-10-01")
    assert err.value.translation_key == "entry_not_loaded"
