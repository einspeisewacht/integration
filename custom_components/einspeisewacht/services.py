"""Action einspeisewacht.report: sums for any period, with response data."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .const import BERLIN, DOMAIN

SERVICE_REPORT = "report"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_START = "start"
ATTR_END = "end"

REPORT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_START): cv.date,
        vol.Optional(ATTR_END): cv.date,
    }
)


def _error(key: str) -> ServiceValidationError:
    return ServiceValidationError(translation_domain=DOMAIN, translation_key=key)


async def _async_report(call: ServiceCall) -> ServiceResponse:
    entry = call.hass.config_entries.async_get_entry(call.data[ATTR_CONFIG_ENTRY_ID])
    if entry is None or entry.domain != DOMAIN:
        raise _error("entry_not_found")
    if entry.state is not ConfigEntryState.LOADED:
        raise _error("entry_not_loaded")
    first = call.data[ATTR_START]
    last = call.data.get(ATTR_END) or dt_util.now(BERLIN).date()
    if last < first:
        raise _error("end_before_start")
    try:
        return await entry.runtime_data.async_report(first, last)
    except ValueError as err:
        raise _error("empty_period") from err


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the actions of the integration (once, not per entry)."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_REPORT,
        _async_report,
        schema=REPORT_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
