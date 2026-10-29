<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/einspeisewacht/integration/main/assets/github/readme-header-dark@2x.png">
  <img alt="Einspeisewacht – every quarter hour in view." src="https://raw.githubusercontent.com/einspeisewacht/integration/main/assets/github/readme-header-light@2x.png" width="640">
</picture>

[![Release](https://img.shields.io/github/v/release/einspeisewacht/integration?color=008351)](https://github.com/einspeisewacht/integration/releases)
[![CI](https://github.com/einspeisewacht/integration/actions/workflows/ci.yml/badge.svg)](https://github.com/einspeisewacht/integration/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-F5A623.svg)](LICENSE)

🇩🇪 [Deutsch](https://github.com/einspeisewacht/integration/blob/main/README.md) · 🇬🇧 **English**

> ℹ️ **New.** Einspeisewacht ("feed-in watch") has been running on real plants since October 2026. The EEG amendment for 2027 is still in parliament; any changes for existing plants will follow in an update. Feedback is very welcome – see [Reporting issues](#reporting-issues).

**How much of your PV feed-in goes unpaid because of negative electricity prices?** Under Germany's Solarspitzengesetz, new PV plants lose their feed-in tariff in every quarter hour with a negative day-ahead price. Einspeisewacht tracks this in Home Assistant, quarter hour by quarter hour, with the price of exactly that quarter hour – and shows what it costs you and how much remuneration time is added at the end in return.

> **Not legal or billing advice.** The values are a guide. What counts is your grid operator's statement – it uses its meter's readings, Home Assistant usually inverter or optical-reader values.

The integration's UI is available in German and English and follows your Home Assistant language. It is built for German law (EEG) and the German-Luxembourg bidding zone.

## What Einspeisewacht does

- **Feed-in remunerated / not remunerated** (kWh) and **revenue / lost revenue** (€), with long-term statistics for day, month and year.
- **Quarter hours without remuneration** in the current year and the resulting **extension** under § 51a EEG: full-load quarter hours and the date your remuneration then runs until.
- **Remunerated**: binary sensor for automations – charge the battery, the car, or curtail.
- **Calendar "Negative prices"** with the windows without remuneration – today and, once the day-ahead forecast is out (usually around 1 pm), tomorrow.
- **Action "Report"** for any period, by month – also for the time before setup, as far back as your meter's statistics reach.
- Derives the **applicable rule** from commissioning date, capacity and smart meter, with a manual override if your grid operator settles differently.
- **Exact at quarter-hour boundaries:** each meter delta is split over the quarter hours by time, each with its own price. A price of exactly 0 is not negative.
- **Robust:** ignores meter resets and implausible jumps, survives restarts, handles daylight saving changes (92 or 100 quarter hours).

<img src="https://raw.githubusercontent.com/einspeisewacht/integration/main/assets/screenshots/geraet.png" alt="Device page of a plant with all sensors (German UI)" width="720">

## Which rule applies (§ 51 EEG)

| Commissioned | Installed capacity | No remuneration when … |
|---|---|---|
| from 25 Feb 2025 | 100 kW and more | every quarter hour with a negative day-ahead price |
| from 25 Feb 2025 | 2 to below 100 kW | as above, but only from 1 January of the year **after** a smart metering system (iMSys) was installed |
| from 25 Feb 2025 | below 2 kW | not affected |
| 2016 to 24 Feb 2025 | 400 or 500 kW and more | consecutive negative hours – not implemented (see below) |
| otherwise | | not affected |

An iMSys is a smart meter **gateway** installed by the metering point operator; a digital meter without gateway does not count. While the rule does not apply to your plant yet, Einspeisewacht adds sensors showing what you would have lost.

**A fixed feed-in tariff only exists up to 100 kW** (§ 21 EEG). Larger plants sell directly; negative prices cost them the market premium, not a fixed rate. Einspeisewacht counts energy and quarter hours correctly for them, but revenue and lost revenue are only a rough guide. The hour-block rules of older large plants therefore never affect a plant with a fixed tariff and are not implemented.

Sources and details (German): [docs/ENTWICKLUNG.md](docs/ENTWICKLUNG.md), section 2.

## Requirements

- Home Assistant 2026.3 or newer.
- A **feed-in meter**: cumulative energy sensor (Wh, kWh or MWh, `state_class` `total` or `total_increasing`) – ideally the meter at the grid connection point.
- A **price sensor** with a day-ahead forecast per quarter hour, e.g. from the [EPEX Spot](https://github.com/mampfes/ha_epex_spot) integration (source SMARD.de, market DE-LU). The `data` attribute of EPEX Spot is tested. Without a forecast attribute the current state counts as the price of the running quarter hour – prices are then missing for times Home Assistant was off, and if the sensor updates only minutes after the quarter-hour boundary, the old value applies until then.

## Installation (HACS)

**One click:** [![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=einspeisewacht&repository=integration&category=integration) → download, restart Home Assistant → [![Add integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=einspeisewacht)

Or by hand:

1. HACS → ⋮ → *Custom repositories* → `https://github.com/einspeisewacht/integration`, type *Integration*.
2. Search for Einspeisewacht and download it. Restart Home Assistant.
3. *Settings → Devices & services → Add integration → Einspeisewacht*.

## Setup

1. **Plant:** name, commissioning date, installed capacity (kWp), iMSys and its installation date.
2. **Remuneration:** the rate from your grid operator's statement in ct/kWh (after the 0.4 ct deduction) – single or tiered by capacity band; for tiered rates Einspeisewacht forms the blended rate (§ 23c EEG).
3. **Data sources:** feed-in meter and price sensor.
4. **Rule:** shows the derived rule, when it starts and the rate; override it if your grid operator settles differently. Optional: **count earlier negative quarter hours from SMARD.de**, so the extension covers the time before setup too; if your price sensor fails, Einspeisewacht also fetches the missing prices from there (public price data, see [Privacy](#privacy)).

<img src="https://raw.githubusercontent.com/einspeisewacht/integration/main/assets/screenshots/einrichtung_regel.png" alt="Last setup step with the derived rule (German UI)" width="420">

Several plants or meters: one entry each. To change: *Einspeisewacht → entry → ⋮ → Reconfigure*.

What a change means for the time before it:

- **Rate:** applies retroactively from setup – revenue and lost revenue are recalculated from the booked kWh. In the long-term statistics the correction shows up in the hour of the change; statistics already added with [Import statistics](#import-statistics) keep the old rate.
- **Rule** (commissioning, capacity, smart meter date, override): quarter hours without remuneration, extension, "Remunerated until" and the [report](#report-for-a-period) follow the new rule at once, retroactively too. The totals "Feed-in remunerated/not remunerated", "Revenue" and "Lost revenue" keep their split for the time before the change, though: Home Assistant would take a falling kWh total for a meter replacement and distort the statistics. The report gives the values under the new rule. If the change affects quarter hours already booked, the log and the diagnostics (`rule_change`) say so.
- **Feed-in meter:** the new meter starts from its own baseline; feed-in between the old meter's last reading and the new one's first is not booked.

## Entities

| Entity | Type | Meaning |
|---|---|---|
| Feed-in remunerated | kWh | grid feed-in in remunerated quarter hours, since setup |
| Feed-in not remunerated | kWh | grid feed-in in quarter hours without remuneration |
| Revenue | € | remunerated feed-in × rate |
| Lost revenue | € | unremunerated feed-in × rate |
| Quarter hours without remuneration | count | current calendar year, with or without feed-in (counts for § 51a); attribute `years` |
| Extension | full-load quarter hours | quarter hours × 0.5, rounded up; attribute `months` with the extension months |
| Remunerated until | date | end of remuneration including the extension |
| Remunerated | paid/unpaid | whether the running quarter hour is remunerated; unknown without a price |
| Negative prices | calendar | windows with a negative price |
| Rule | diagnostic | the rule applied, attributes `applies_from` and `rate_ct_per_kwh` |

While the rule does not apply yet (e.g. no iMSys), "… if the rule applied" sensors are added and the extension sensors are left out.

## Report for a period

*Developer tools → Actions →* **Einspeisewacht: Report**, choose plant and period, "Show response":

```yaml
action: einspeisewacht.report
data:
  config_entry_id: <choose entry>
  start: "2026-01-01"
  end: "2026-12-31"
```

The response holds kWh remunerated and not, revenue, lost revenue and the negative quarter hours – in total and by month. It is based on your feed-in meter's long-term statistics (hourly values spread evenly over the four quarter hours – exact when all four end the same way, a close estimate otherwise). Quarter hours without a known price count as remunerated and are listed under `gaps` – including time Home Assistant was off for more than 14 days; with the SMARD option, prices reach back to commissioning.

## Import statistics

The total sensors start at setup. To make statistics cards and history cover the time before, use the action **Einspeisewacht: Import statistics** (*Developer tools → Actions*), e.g. from 1 January or from commissioning:

```yaml
action: einspeisewacht.import_statistics
data:
  config_entry_id: <choose entry>
  start: "2026-01-01"
```

It computes like the report and writes the hours **before** the first existing statistic into the long-term statistics of the four total sensors; later sums are shifted to match. Requires the SMARD option (its download finished) and at least one hour of statistics for the sensors. **This changes the statistics database – make a backup first.** A second call finds nothing left to import.

## Examples

The calendar "Negative prices" shows the windows without remuneration – here the day of the 2026 clock change (German UI):

<img src="https://raw.githubusercontent.com/einspeisewacht/integration/main/assets/screenshots/kalender.png" alt="Calendar with five windows without remuneration on 25 Oct 2026" width="620">

### Dashboard card with daily and yearly values

The total sensors count from setup; daily, monthly and yearly values come from their long-term statistics – after [Import statistics](#import-statistics) also for the time before. This card uses built-in cards only (German UI, values made up):

<img src="https://raw.githubusercontent.com/einspeisewacht/integration/main/assets/screenshots/dashboard.png" alt="Card with daily bars remunerated/not remunerated, revenue and lost revenue for today and the year, negative quarter hours, extension and end of remuneration" width="400">

<details>
<summary>YAML of the card (adjust the entities of plant "Roof")</summary>

```yaml
type: vertical-stack
cards:
  - type: statistics-graph
    title: Feed-in per day
    entities:
      - entity: sensor.roof_feed_in_remunerated
        name: Remunerated
        color: "#27ae60"
      - entity: sensor.roof_feed_in_not_remunerated
        name: Not remunerated
        color: "#e6007e"
    period: day
    days_to_show: 30
    chart_type: bar-stack
    stat_types:
      - change
  - type: grid
    columns: 2
    square: false
    cards:
      - type: statistic
        entity: sensor.roof_revenue
        name: Revenue today
        stat_type: change
        period:
          calendar:
            period: day
      - type: statistic
        entity: sensor.roof_lost_revenue
        name: Lost today
        stat_type: change
        period:
          calendar:
            period: day
      - type: statistic
        entity: sensor.roof_revenue
        name: Revenue year
        stat_type: change
        period:
          calendar:
            period: year
      - type: statistic
        entity: sensor.roof_lost_revenue
        name: Lost year
        stat_type: change
        period:
          calendar:
            period: year
  - type: entities
    title: Negative prices this year
    entities:
      - entity: sensor.roof_quarter_hours_without_remuneration
        name: Without remuneration
      - entity: sensor.roof_extension
        name: Extension
      - entity: sensor.roof_remunerated_until
        name: Remunerated until
  - type: tile
    entity: binary_sensor.roof_remunerated
    name: Now
```

</details>


**Blueprint "switch on negative prices":** runs your own actions when remuneration stops (charge the battery, switch on the wallbox, curtail) and others when it resumes. [![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Feinspeisewacht%2Fintegration%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Feinspeisewacht%2Fvergutung_aus_an.yaml)

```yaml
alias: Charge the battery while there is no remuneration
triggers:
  - trigger: state
    entity_id: binary_sensor.roof_remunerated
    to: "off"
actions:
  - action: select.select_option
    target:
      entity_id: select.inverter_battery_mode   # your entity
    data:
      option: "Charge from PV"
mode: single
```

Entity IDs depend on your plant's name and Home Assistant language.

## Privacy

Einspeisewacht computes locally and reads only the entities you choose. The single exception, only if you turn it on: the SMARD option downloads public day-ahead prices from smard.de (German Federal Network Agency) – once for the time before setup, and afterwards only while your price sensor delivers no prices for more than an hour (at most once an hour). Nothing about you or your plant is sent – only requests for the price files, identified as `Einspeisewacht/<version>`. The diagnostics file contains neither the plant's name nor meter readings, energy or revenue totals.

## What Einspeisewacht does not do

- **No billing:** differences to your grid operator's statement are normal.
- **No direct marketing:** market premium and fallback remuneration are not modelled (above 100 kW).
- **No old rules** for large plants (hour blocks, 2016 to 24 Feb 2025).
- **Voluntary switch to the new rules** (§ 100 (47) EEG, +0.6 ct/kWh) is not offered while EU state-aid approval is missing.
- **The meter must measure grid feed-in.** A production meter also counts self-consumption and battery charging, which the rule does not affect.
- The total sensors start at setup; for earlier periods use the Report and Import statistics actions.

## Troubleshooting

- **Values stay at 0:** check that the feed-in meter reports values and whether the rule applies yet (sensor "Rule", attribute `applies_from`).
- **"Remunerated" is unknown:** the price sensor has no price for the running quarter hour.
- **Repair "SMARD.de unreachable":** downloading earlier prices failed; it is retried at the next Home Assistant start. Live booking is not affected.
- **Diagnostics:** *Einspeisewacht → entry → ⋮ → Download diagnostics*. **Debug log:** *Einspeisewacht → ⋮ → Enable debug logging*.

## Removal

1. *Settings → Devices & services → Einspeisewacht* → ⋮ on each entry → *Delete*. The entry's stored bookings are deleted with it.
2. Optional: HACS → Einspeisewacht → ⋮ → *Remove*, then restart Home Assistant.

Long-term statistics of the deleted sensors stay until you remove them under *Developer tools → Statistics*.

## Reporting issues

Please open an [issue](https://github.com/einspeisewacht/integration/issues), ideally with the diagnostics file and your Home Assistant and Einspeisewacht versions. Security issues privately, see [SECURITY.md](SECURITY.md).

## License and sources

MIT. Historical day-ahead prices (optional): Bundesnetzagentur | [SMARD.de](https://www.smard.de), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); Einspeisewacht only counts the negative quarter hours from them.
