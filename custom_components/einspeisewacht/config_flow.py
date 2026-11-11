"""Config flow: plant, remuneration, data sources and rule. One entry per meter.

The same steps serve reconfiguration; the last step then updates the entry.
Reconfiguration starts with an overview of what is set up and what is missing.
Rare settings sit in sections that start collapsed (08.11.2026: forms should
ask only the essentials): the rates per capacity band (plants above 10 kWp)
and a manual rule. They are stored flat in the entry data as ever.
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
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import dt as dt_util

from . import overview
from .const import (
    BERLIN,
    CONF_BACKFILL,
    CONF_COMMISSIONED,
    CONF_FEED_IN_TYPE,
    CONF_METER,
    CONF_METER_PREVIOUS,
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
from .entity import own_entities
from .meter import UNIT_FACTORS
from .regime import Derived
from .runtime import derived_from_config, parse_price_state, rate_from_config
from .sisters import TARIFWACHT, TARIFWACHT_URL, tarifwacht_sources
from .suggest import async_suggested_meter, suggested_price
from .tariff import PARTIAL_BANDS, bands

CONF_RATE = "rate"
# Sections of the forms (collapsed unless in use).
SECTION_TIERS = "tiers"
SECTION_RULE = "rule"
# § 21 Abs. 1 Nr. 1 EEG: the fixed feed-in tariff exists up to 100 kW; larger
# plants sell directly, and negative prices cost them the market premium.
FEED_IN_TARIFF_LIMIT_KW = 100
# Up to the first band limit (10 kW, § 48 Abs. 2) a plant has a single rate:
# no section for capacity bands.
SINGLE_BAND_KW = PARTIAL_BANDS[0]
# Hint of the sources step at setup: values taken from Tarifwacht, or a tip
# when it has none (own step ids, own texts).
HINT_TARIFWACHT = "tarifwacht"
HINT_TARIFWACHT_TIP = "tarifwacht_tip"
# Selector translations that the flow uses as texts (overview, rule, notes),
# under the names `overview.build` expects.
TEXT_PREFIXES = {
    "overview": "",
    "regime": "regime_",
    "feed_in_type": "feed_in_",
    "notice": "notice_",
}


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


def _section(fields: dict[Any, Any], collapsed: bool) -> section:
    """A section of a form. Its key is optional and has no default: with a
    default the frontend takes it over the suggested values of the fields
    (Wärmewacht 9c7e722); a section left out of the input keeps what is
    stored."""
    return section(vol.Schema(fields), {"collapsed": collapsed})


RATE_NUMBER = _number("ct/kWh", 0.001, 100)


class EinspeisewachtConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a plant and its feed-in meter."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        # The entry data when a reconfigure flow started.
        self._initial: dict[str, Any] = {}
        # Sources suggested from Tarifwacht at setup (read once), the hint
        # of the sources step and the Tarifwacht entry they came from.
        self._suggested: dict[str, str] | None = None
        self._hint: str | None = None
        self._tarifwacht_title = ""

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
        """Change an existing plant: an overview, then the same steps, prefilled."""
        if not self._data:
            self._initial = dict(self._get_reconfigure_entry().data)
            self._data = dict(self._initial)
        return await self._async_plant_step("reconfigure", user_input)

    async def _async_plant_step(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            smart_meter = user_input.get(CONF_SMART_METER, False)
            smart_meter_date = user_input.get(CONF_SMART_METER_DATE)
            today = dt_util.now().date()
            if not name:
                errors[CONF_NAME] = "name_required"
            elif user_input[CONF_POWER] <= 0:
                errors[CONF_POWER] = "power_invalid"
            elif date.fromisoformat(user_input[CONF_COMMISSIONED]) > today:
                errors[CONF_COMMISSIONED] = "date_in_future"
            elif smart_meter and not smart_meter_date:
                errors[CONF_SMART_METER_DATE] = "smart_meter_date_required"
            elif smart_meter and date.fromisoformat(smart_meter_date) > today:
                errors[CONF_SMART_METER_DATE] = "date_in_future"
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
        placeholders: dict[str, str] = {}
        if step_id == "reconfigure":
            placeholders["overview"] = await self._async_overview()
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input or self._data
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_rate(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: the rate; per capacity band in a section (above 10 kWp)."""
        errors: dict[str, str] = {}
        stored_mode = self._data.get(CONF_RATE_MODE, RATE_SINGLE)
        stored_type = self._data.get(CONF_FEED_IN_TYPE, FEED_IN_PARTIAL)
        # A plant up to 10 kWp has one band; an entry tiered before keeps
        # the section to switch back.
        offer_tiers = (
            self._data[CONF_POWER] > SINGLE_BAND_KW or stored_mode == RATE_TIERED
        )
        if user_input is not None:
            # Section not shown or not sent: what is stored stays.
            tiers = user_input.get(SECTION_TIERS) or {}
            mode = tiers.get(CONF_RATE_MODE, stored_mode)
            self._data[CONF_RATE_MODE] = mode
            self._data[CONF_FEED_IN_TYPE] = tiers.get(CONF_FEED_IN_TYPE, stored_type)
            if mode == RATE_TIERED:
                return await self.async_step_tier_rates()
            if user_input.get(CONF_RATE) is None:
                errors[CONF_RATE] = "rate_required"
            else:
                self._data[CONF_RATES] = [float(user_input[CONF_RATE])]
                return await self.async_step_sources()

        fields: dict[Any, Any] = {vol.Optional(CONF_RATE): RATE_NUMBER}
        suggested: dict[str, Any] = {}
        if stored_mode == RATE_SINGLE and self._data.get(CONF_RATES):
            suggested[CONF_RATE] = self._data[CONF_RATES][0]
        if offer_tiers:
            fields[vol.Optional(SECTION_TIERS)] = _section(
                {
                    vol.Required(CONF_RATE_MODE, default=RATE_SINGLE): _select(
                        [RATE_SINGLE, RATE_TIERED], CONF_RATE_MODE
                    ),
                    vol.Required(CONF_FEED_IN_TYPE, default=FEED_IN_PARTIAL): _select(
                        [FEED_IN_PARTIAL, FEED_IN_FULL], CONF_FEED_IN_TYPE
                    ),
                },
                collapsed=stored_mode != RATE_TIERED,
            )
            suggested[SECTION_TIERS] = {
                CONF_RATE_MODE: stored_mode,
                CONF_FEED_IN_TYPE: stored_type,
            }
        return self.async_show_form(
            step_id="rate",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(fields), user_input or suggested
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
        """Step 3, the last: meter, price sensor, SMARD.de; the derived rule
        on top, a manual rule in a section."""
        errors: dict[str, str] = {}
        stored_override = self._data.get(CONF_OVERRIDE) or OVERRIDE_AUTO
        stored_date = self._data.get(CONF_OVERRIDE_DATE)
        if user_input is not None:
            meter, price = self._follow_renames(
                user_input[CONF_METER], user_input[CONF_PRICE]
            )
            errors = self._validate_sources(meter, price)
            # Section not sent: the stored rule stays.
            override, override_date = stored_override, stored_date
            if (rule := user_input.get(SECTION_RULE)) is not None:
                override = rule.get(CONF_OVERRIDE, OVERRIDE_AUTO)
                override_date = rule.get(CONF_OVERRIDE_DATE)
            if override == OVERRIDE_FROM_DATE and not override_date:
                errors["base"] = "override_date_required"
            if not errors:
                self._data[CONF_METER] = meter
                self._data[CONF_PRICE] = price
                self._data[CONF_OVERRIDE] = override
                self._data[CONF_OVERRIDE_DATE] = (
                    override_date if override == OVERRIDE_FROM_DATE else None
                )
                self._data[CONF_BACKFILL] = user_input.get(CONF_BACKFILL, False)
                return await self._async_finish()

        if self.source != SOURCE_RECONFIGURE and self._suggested is None:
            self._suggest_from_tarifwacht()
            await self._async_suggest_others()
        expanded = stored_override != OVERRIDE_AUTO or "base" in errors
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
                vol.Required(CONF_BACKFILL, default=False): selector.BooleanSelector(),
                vol.Optional(SECTION_RULE): _section(
                    {
                        vol.Required(CONF_OVERRIDE, default=OVERRIDE_AUTO): _select(
                            [OVERRIDE_AUTO, OVERRIDE_FROM_DATE, OVERRIDE_NEVER],
                            CONF_OVERRIDE,
                        ),
                        vol.Optional(CONF_OVERRIDE_DATE): selector.DateSelector(),
                    },
                    collapsed=not expanded,
                ),
            }
        )
        auto = derived_from_config({**self._data, CONF_OVERRIDE: OVERRIDE_AUTO})
        placeholders = await self._rule_placeholders(auto)
        if self._hint == HINT_TARIFWACHT:
            placeholders["tarifwacht"] = self._tarifwacht_title
        elif self._hint == HINT_TARIFWACHT_TIP:
            placeholders["tarifwacht_url"] = TARIFWACHT_URL
        suggested = {
            **(self._suggested or {}),
            **self._data,
            SECTION_RULE: {
                CONF_OVERRIDE: stored_override,
                CONF_OVERRIDE_DATE: stored_date,
            },
        }
        return self.async_show_form(
            step_id=f"sources_{self._hint}" if self._hint else "sources",
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input or suggested
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_sources_tarifwacht(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3, with the sources taken from Tarifwacht."""
        return await self.async_step_sources(user_input)

    async def async_step_sources_tarifwacht_tip(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3, with the tip on Tarifwacht."""
        return await self.async_step_sources(user_input)

    def _suggest_from_tarifwacht(self) -> None:
        """Feed-in meter and exchange price sensor of a Tarifwacht entry as
        suggestions; copied once, no dependency at runtime. A meter that
        already belongs to an entry is not suggested."""
        self._suggested = {}
        found = tarifwacht_sources(
            self.hass.config_entries.async_entries(TARIFWACHT, include_ignore=False)
        )
        if found is None:
            self._hint = HINT_TARIFWACHT_TIP
            return
        title, values = found
        meter = values.get(CONF_METER)
        if meter and any(e.unique_id == meter for e in self._async_current_entries()):
            values.pop(CONF_METER)
        if values:
            self._suggested = values
            self._hint = HINT_TARIFWACHT
            self._tarifwacht_title = title

    async def _async_suggest_others(self) -> None:
        """What Tarifwacht did not give: the grid export of the energy
        dashboard as meter, EPEX Spot's market price as price sensor."""
        suggested = self._suggested if self._suggested is not None else {}
        if CONF_METER not in suggested and (
            meter := await async_suggested_meter(
                self.hass, {e.unique_id for e in self._async_current_entries()}
            )
        ):
            suggested[CONF_METER] = meter
        if CONF_PRICE not in suggested and (price := suggested_price(self.hass)):
            suggested[CONF_PRICE] = price
        self._suggested = suggested

    def _follow_renames(self, meter: str, price: str) -> tuple[str, str]:
        """Renamed while the flow was open: the form still holds the old id;
        keep the new one (__init__.py followed the rename)."""
        if self.source != SOURCE_RECONFIGURE:
            return meter, price
        current = self._get_reconfigure_entry().data
        values = {CONF_METER: meter, CONF_PRICE: price}
        for key, value in values.items():
            if value == self._initial.get(key) != current.get(key):
                values[key] = current[key]
        return values[CONF_METER], values[CONF_PRICE]

    def _validate_sources(self, meter: str, price: str) -> dict[str, str]:
        errors: dict[str, str] = {}
        current = (
            self._get_reconfigure_entry().entry_id
            if self.source == SOURCE_RECONFIGURE
            else None
        )
        meter_state = self.hass.states.get(meter)
        # Einspeisewacht's own energy totals pass the meter checks, any
        # numeric sensor of it the price check.
        own = own_entities(self.hass, (meter, price))
        if meter in own:
            errors[CONF_METER] = "own_entity"
        elif any(
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
        if price in own:
            errors[CONF_PRICE] = "own_entity"
        elif price_state is None:
            errors[CONF_PRICE] = "entity_missing"
        elif price_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            # The sensor of an integration that is not loaded (it keeps its
            # attributes from the registry): "no price found" would mislead.
            errors[CONF_PRICE] = "price_unavailable"
        else:
            parsed = parse_price_state(price_state)
            if parsed is None or not parsed.prices:
                errors[CONF_PRICE] = "price_invalid"
        return errors

    async def _async_texts(self) -> dict[str, str]:
        """Selector translations used as texts, by their short names."""
        translations = await async_get_translations(
            self.hass, self.hass.config.language, "selector", [DOMAIN]
        )
        texts: dict[str, str] = {}
        for selector_key, prefix in TEXT_PREFIXES.items():
            start = f"component.{DOMAIN}.selector.{selector_key}.options."
            texts.update(
                {
                    prefix + key.removeprefix(start): value
                    for key, value in translations.items()
                    if key.startswith(start)
                }
            )
        return texts

    async def _rule_placeholders(self, derived: Derived) -> dict[str, str]:
        language = self.hass.config.language
        texts = await self._async_texts()
        regime = derived.regime.value
        rate = overview.format_number(rate_from_config(self._data), language)
        # A rule that starts in a later year is usually a mistyped year. The
        # warning text lives with the selector translations, the only place a
        # flow can look up a translated string for a placeholder.
        notices = []
        if derived.applies_from and derived.applies_from > dt_util.now().date():
            notices.append("future_start")
        if self._data[CONF_POWER] > FEED_IN_TARIFF_LIMIT_KW:
            notices.append("direct_marketing")
        rule = texts.get(f"regime_{regime}", regime)
        applies_from = overview.format_date(derived.applies_from, language)
        if derived.applies_from is not None:
            start = texts.get("rule_start", "{date}").format(date=applies_from)
            rule = f"{rule}, {start}"
        return {
            "rule": rule,
            "applies_from": applies_from,
            "rate": rate,
            "note": "\n\n".join(texts.get(f"notice_{key}", "") for key in notices),
        }

    async def _async_overview(self) -> str:
        """What the entry has set up and what is missing (reconfigure)."""
        entry = self._get_reconfigure_entry()
        config = self._initial
        try:
            rate: float | None = rate_from_config(config)
        except KeyError, IndexError, ValueError:
            rate = None
        meter, price = config[CONF_METER], config[CONF_PRICE]
        own = own_entities(self.hass, (meter, price))
        return overview.build(
            config,
            derived_from_config(config),
            rate,
            self._meter_source(meter, own),
            self._price_source(price, own),
            today=dt_util.now(BERLIN).date(),
            setup_day=entry.created_at.astimezone(BERLIN).date(),
            texts=await self._async_texts(),
            language=self.hass.config.language,
        )

    def _meter_source(self, entity_id: str, own: list[str]) -> overview.Source:
        state = self.hass.states.get(entity_id)
        name = state.name if state else entity_id
        if entity_id in own:
            return overview.Source(name, overview.OWN)
        if state is None:
            return overview.Source(name, overview.MISSING)
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        # Unavailable for a moment: the next value books the gap.
        if state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN) and (
            unit not in UNIT_FACTORS
        ):
            return overview.Source(name, overview.UNIT, unit)
        return overview.Source(name)

    def _price_source(self, entity_id: str, own: list[str]) -> overview.Source:
        state = self.hass.states.get(entity_id)
        name = state.name if state else entity_id
        if entity_id in own:
            return overview.Source(name, overview.OWN)
        if state is None:
            return overview.Source(name, overview.MISSING)
        parsed = parse_price_state(state)
        if parsed is None or not parsed.prices:
            return overview.Source(name, overview.INVALID)
        return overview.Source(name)

    async def _async_finish(self) -> ConfigFlowResult:
        if self.source == SOURCE_RECONFIGURE:
            entry = self._get_reconfigure_entry()
            current = entry.data
            meter = self._data[CONF_METER]
            if meter == current[CONF_METER] and CONF_METER_PREVIOUS in current:
                self._data[CONF_METER_PREVIOUS] = current[CONF_METER_PREVIOUS]
            elif meter != current[CONF_METER]:
                # Another meter: earlier names of the old one keep nothing.
                self._data.pop(CONF_METER_PREVIOUS, None)
            return self.async_update_reload_and_abort(
                entry,
                unique_id=meter,
                title=self._data[CONF_NAME],
                data=self._data,
            )
        meter = self._data[CONF_METER]
        await self.async_set_unique_id(meter)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)
