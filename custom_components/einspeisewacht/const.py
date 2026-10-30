"""Constants for Einspeisewacht. Pure Python, no Home Assistant imports."""

from __future__ import annotations

from typing import Final
from zoneinfo import ZoneInfo

DOMAIN: Final = "einspeisewacht"
VERSION: Final = "0.1.4"
USER_AGENT: Final = (
    f"Einspeisewacht/{VERSION} (+https://github.com/einspeisewacht/integration)"
)

# Calendar years (rule start, § 51a counting) follow German local time.
BERLIN: Final = ZoneInfo("Europe/Berlin")

CONF_NAME: Final = "name"
CONF_COMMISSIONED: Final = "commissioned"
CONF_POWER: Final = "power_kw"
CONF_SMART_METER: Final = "smart_meter"
CONF_SMART_METER_DATE: Final = "smart_meter_date"
CONF_RATE_MODE: Final = "rate_mode"
CONF_FEED_IN_TYPE: Final = "feed_in_type"
CONF_RATES: Final = "rates"  # ct/kWh, one per capacity band
CONF_METER: Final = "meter_entity"
CONF_PRICE: Final = "price_entity"
# Earlier ids of the meter, renamed in the entity registry (rename.py): the
# stored last reading still names one of them and stays the baseline.
CONF_METER_PREVIOUS: Final = "meter_previous"
CONF_OVERRIDE: Final = "override"
CONF_OVERRIDE_DATE: Final = "override_date"
CONF_BACKFILL: Final = (
    "backfill_smard"  # opt-in: count earlier quarter hours from SMARD.de
)

RATE_SINGLE: Final = "single"
RATE_TIERED: Final = "tiered"
FEED_IN_PARTIAL: Final = "partial"
FEED_IN_FULL: Final = "full"
OVERRIDE_AUTO: Final = "auto"
OVERRIDE_FROM_DATE: Final = "from_date"
OVERRIDE_NEVER: Final = "never"
