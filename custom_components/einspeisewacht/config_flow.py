"""Config flow: plant, remuneration, data sources, derived rule. One entry per meter.

The same steps serve reconfiguration; the last step then updates the entry.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import voluptuous as vol
from homeassistant.components.sensor import ATTR_STATE_CLASS, SensorStateClass
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.helpers import selector
from homeassistant.helpers.translation import async_get_translations

from .const import (
    CONF_COMMISSIONED,
    CONF_FEED_IN_TYPE,
    CONF_METER,
    CONF_NAME,
    CONF_OVERRIDE,
    CONF_OVERRIDE_DATE,
    CONF_POWER,
    CONF_PRICE,
    CONF_RATE_MODE,
    CONF_RATES,
    CONF_SMART_METER,
    CONF_SMART_METER_DATE,
    DOMAIN,
    FEED_IN_FULL,
    FEED_IN_PARTIAL,
    OVERRIDE_AUTO,
    OVERRIDE_FROM_DATE,
    OVERRIDE_NEVER,
    RATE_SINGLE,
    RATE_TIERED,
)
from .meter import UNIT_FACTORS
from .regime import Derived
from .runtime import derived_from_config, parse_price_state, rate_from_config
from .tariff import bands

CONF_RATE = "rate"


def band_key(lower: float, upper: float) -> str:
    """Form field of a capacity band, e.g. "band_10_40"."""
    return f"band_{lower:g}_{upper:g}"


def _select(options: list[str], key: str) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options, translation_key=key, mode=selector.SelectSelectorMode.LIST
        )
    )


def _number(unit: str, step: float, maximum: float) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            max=maximum,
            step=step,
            unit_of_measurement=unit,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


RATE_NUMBER = _number("ct/kWh", 0.001, 100)


class EinspeisewachtConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a plant and its feed-in meter."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    @property
    def _full_feed_in(self) -> bool:
        return self._data.get(CONF_FEED_IN_TYPE) == FEED_IN_FULL

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: the plant."""
        return await self._async_plant_step("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change an existing plant: the same steps, prefilled."""
        if not self._data:
            self._data = dict(self._get_reconfigure_entry().data)
        return await self._async_plant_step("reconfigure", user_input)

    async def _async_plant_step(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            smart_meter = user_input.get(CONF_SMART_METER, False)
            if not name:
                errors[CONF_NAME] = "name_required"
            elif user_input[CONF_POWER] <= 0:
                errors[CONF_POWER] = "power_invalid"
            elif smart_meter and not user_input.get(CONF_SMART_METER_DATE):
                errors[CONF_SMART_METER_DATE] = "smart_meter_date_required"
            else:
                self._data.update(
                    {
                        CONF_NAME: name,
                        CONF_COMMISSIONED: user_input[CONF_COMMISSIONED],
                        CONF_POWER: float(user_input[CONF_POWER]),
                        CONF_SMART_METER: smart_meter,
                        CONF_SMART_METER_DATE: user_input.get(CONF_SMART_METER_DATE)
                        if smart_meter
                        else None,
                    }
                )
                return await self.async_step_rate()

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): selector.TextSelector(),
                vol.Required(CONF_COMMISSIONED): selector.DateSelector(),
                vol.Required(CONF_POWER): _number("kWp", 0.01, 100000),
                vol.Required(
                    CONF_SMART_METER, default=False
                ): selector.BooleanSelector(),
                vol.Optional(CONF_SMART_METER_DATE): selector.DateSelector(),
            }
        )
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input or self._data
            ),
            errors=errors,
        )

    async def async_step_rate(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: one rate, or one rate per capacity band."""
        errors: dict[str, str] = {}
        if user_input is not None:
            mode = user_input[CONF_RATE_MODE]
            self._data[CONF_RATE_MODE] = mode
            self._data[CONF_FEED_IN_TYPE] = user_input[CONF_FEED_IN_TYPE]
            if mode == RATE_TIERED:
                return await self.async_step_tier_rates()
            if user_input.get(CONF_RATE) is None:
                errors[CONF_RATE] = "rate_required"
            else:
                self._data[CONF_RATES] = [float(user_input[CONF_RATE])]
                return await self.async_step_sources()

        schema = vol.Schema(
            {
                vol.Required(CONF_RATE_MODE, default=RATE_SINGLE): _select(
                    [RATE_SINGLE, RATE_TIERED], CONF_RATE_MODE
                ),
                vol.Required(CONF_FEED_IN_TYPE, default=FEED_IN_PARTIAL): _select(
                    [FEED_IN_PARTIAL, FEED_IN_FULL], CONF_FEED_IN_TYPE
                ),
                vol.Optional(CONF_RATE): RATE_NUMBER,
            }
        )
        suggested = dict(self._data)
        if self._data.get(CONF_RATE_MODE) == RATE_SINGLE and self._data.get(CONF_RATES):
            suggested[CONF_RATE] = self._data[CONF_RATES][0]
        return self.async_show_form(
            step_id="rate",
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input or suggested
            ),
            errors=errors,
        )

    async def async_step_tier_rates(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2b: a rate for each capacity band the plant reaches (§ 23c)."""
        reached = bands(self._data[CONF_POWER], self._full_feed_in)
        keys = [band_key(lower, upper) for lower, upper in reached]
        if user_input is not None:
            self._data[CONF_RATES] = [float(user_input[k]) for k in keys]
            return await self.async_step_sources()

        suggested: dict[str, Any] = {}
        previous = self._data.get(CONF_RATES) or []
        if self._data.get(CONF_RATE_MODE) == RATE_TIERED and len(previous) == len(keys):
            suggested = dict(zip(keys, previous, strict=True))
        schema = vol.Schema({vol.Required(k): RATE_NUMBER for k in keys})
        return self.async_show_form(
            step_id="tier_rates",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
        )

    async def async_step_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3: feed-in meter and price sensor."""
        errors: dict[str, str] = {}
        if user_input is not None:
            meter, price = user_input[CONF_METER], user_input[CONF_PRICE]
            errors = self._validate_sources(meter, price)
            if not errors:
                self._data[CONF_METER] = meter
                self._data[CONF_PRICE] = price
                return await self.async_step_summary()

        schema = vol.Schema(
            {
                vol.Required(CONF_METER): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor", device_class="energy"
                    )
                ),
                vol.Required(CONF_PRICE): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
            }
        )
        return self.async_show_form(
            step_id="sources",
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input or self._data
            ),
            errors=errors,
        )

    def _validate_sources(self, meter: str, price: str) -> dict[str, str]:
        errors: dict[str, str] = {}
        current = (
            self._get_reconfigure_entry().entry_id
            if self.source == SOURCE_RECONFIGURE
            else None
        )
        meter_state = self.hass.states.get(meter)
        if any(
            e.unique_id == meter and e.entry_id != current
            for e in self._async_current_entries()
        ):
            errors[CONF_METER] = "meter_in_use"
        elif meter_state is None:
            errors[CONF_METER] = "entity_missing"
        elif meter_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) not in UNIT_FACTORS:
            errors[CONF_METER] = "meter_unit"
        elif meter_state.attributes.get(ATTR_STATE_CLASS) not in (
            SensorStateClass.TOTAL,
            SensorStateClass.TOTAL_INCREASING,
        ):
            errors[CONF_METER] = "meter_state_class"
        price_state = self.hass.states.get(price)
        if price_state is None:
            errors[CONF_PRICE] = "entity_missing"
        else:
            parsed = parse_price_state(price_state)
            if parsed is None or not parsed.prices:
                errors[CONF_PRICE] = "price_invalid"
        return errors

    async def async_step_summary(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 4: show the derived rule; allow a manual override."""
        errors: dict[str, str] = {}
        if user_input is not None:
            override = user_input[CONF_OVERRIDE]
            override_date = user_input.get(CONF_OVERRIDE_DATE)
            if override == OVERRIDE_FROM_DATE and not override_date:
                errors[CONF_OVERRIDE_DATE] = "override_date_required"
            else:
                self._data[CONF_OVERRIDE] = override
                self._data[CONF_OVERRIDE_DATE] = (
                    override_date if override == OVERRIDE_FROM_DATE else None
                )
                return await self._async_finish()

        auto = derived_from_config({**self._data, CONF_OVERRIDE: OVERRIDE_AUTO})
        schema = vol.Schema(
            {
                vol.Required(CONF_OVERRIDE, default=OVERRIDE_AUTO): _select(
                    [OVERRIDE_AUTO, OVERRIDE_FROM_DATE, OVERRIDE_NEVER], CONF_OVERRIDE
                ),
                vol.Optional(CONF_OVERRIDE_DATE): selector.DateSelector(),
            }
        )
        return self.async_show_form(
            step_id="summary",
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input or self._data
            ),
            errors=errors,
            description_placeholders=await self._rule_placeholders(auto),
        )

    async def _rule_placeholders(self, derived: Derived) -> dict[str, str]:
        language = self.hass.config.language
        translations = await async_get_translations(
            self.hass, language, "selector", [DOMAIN]
        )
        regime = derived.regime.value
        rule = translations.get(
            f"component.{DOMAIN}.selector.regime.options.{regime}", regime
        )
        rate = f"{rate_from_config(self._data):.3f}".rstrip("0").rstrip(".")
        if language.startswith("de"):
            rate = rate.replace(".", ",")
        return {
            "rule": rule,
            "applies_from": _format_date(derived.applies_from, language),
            "rate": rate,
        }

    async def _async_finish(self) -> ConfigFlowResult:
        meter = self._data[CONF_METER]
        if self.source == SOURCE_RECONFIGURE:
            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(),
                unique_id=meter,
                title=self._data[CONF_NAME],
                data=self._data,
            )
        await self.async_set_unique_id(meter)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)


def _format_date(day: date | None, language: str) -> str:
    if day is None:
        return "–"
    return day.strftime("%d.%m.%Y") if language.startswith("de") else day.isoformat()
