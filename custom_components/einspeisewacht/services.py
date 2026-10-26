"""Actions: einspeisewacht.report (sums for any period) and
einspeisewacht.import_statistics (history of the total sensors before setup)."""

from __future__ import annotations

from typing import TYPE_CHECKING

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
from .statistics_import import StatisticsImportError, async_import_history

if TYPE_CHECKING:
    from . import EinspeisewachtConfigEntry

SERVICE_REPORT = "report"
SERVICE_IMPORT_STATISTICS = "import_statistics"
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
IMPORT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_START): cv.date,
    }
)


def _error(
    key: str, placeholders: dict[str, str] | None = None
) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders=placeholders,
    )


def _loaded_entry(call: ServiceCall) -> EinspeisewachtConfigEntry:
    entry = call.hass.config_entries.async_get_entry(call.data[ATTR_CONFIG_ENTRY_ID])
    if entry is None or entry.domain != DOMAIN:
        raise _error("entry_not_found")
    if entry.state is not ConfigEntryState.LOADED:
        raise _error("entry_not_loaded")
    return entry


async def _async_report(call: ServiceCall) -> ServiceResponse:
    entry = _loaded_entry(call)
    first = call.data[ATTR_START]
    last = call.data.get(ATTR_END) or dt_util.now(BERLIN).date()
    if last < first:
        raise _error("end_before_start")
    try:
        return await entry.runtime_data.async_report(first, last)
    except ValueError as err:
        raise _error("empty_period") from err


async def _async_import_statistics(call: ServiceCall) -> ServiceResponse:
    entry = _loaded_entry(call)
    try:
        result = await async_import_history(call.hass, entry, call.data[ATTR_START])
    except StatisticsImportError as err:
        raise _error(f"import_{err.key}", err.placeholders) from err
    return result if call.return_response else None


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
    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_STATISTICS,
        _async_import_statistics,
        schema=IMPORT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
