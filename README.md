<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/einspeisewacht/integration/main/assets/github/readme-header-dark@2x.png">
  <img alt="Einspeisewacht – Jede Viertelstunde im Blick." src="https://raw.githubusercontent.com/einspeisewacht/integration/main/assets/github/readme-header-light@2x.png" width="640">
</picture>

[![Release](https://img.shields.io/github/v/release/einspeisewacht/integration?color=008351)](https://github.com/einspeisewacht/integration/releases)
[![CI](https://github.com/einspeisewacht/integration/actions/workflows/ci.yml/badge.svg)](https://github.com/einspeisewacht/integration/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-F5A623.svg)](LICENSE)

🇩🇪 **Deutsch** · 🇬🇧 [English](https://github.com/einspeisewacht/integration/blob/main/README.en.md)

> ℹ️ **Neu.** Einspeisewacht läuft seit Oktober 2026 auf echten Anlagen. Die EEG-Novelle 2027 ist noch im Bundestag; was sich für bestehende Anlagen ändert, kommt mit einem Update. Rückmeldungen sind sehr willkommen – siehe [Fehler melden](#fehler-melden).

**Wie viel deiner PV-Einspeisung wird wegen negativer Strompreise nicht vergütet?** Seit dem Solarspitzengesetz verlieren neue PV-Anlagen die Einspeisevergütung in jeder Viertelstunde mit negativem Börsenpreis. Einspeisewacht rechnet das in Home Assistant für dich mit: Viertelstunde für Viertelstunde, mit dem Preis genau dieser Viertelstunde – und zeigt, was dich das kostet und wie viel Förderzeit dafür am Ende angehängt wird.

> **Keine Rechts- oder Abrechnungsberatung.** Die Werte sind eine Orientierung. Maßgeblich ist die Abrechnung deines Netzbetreibers – er rechnet mit den Messwerten seines Zählers, Home Assistant meist mit Wechselrichter- oder Lesekopfwerten.

Die Oberfläche gibt es auf Deutsch und Englisch; sie folgt der Sprache deines Home Assistant.

## Was Einspeisewacht kann

- **Einspeisung vergütet / unvergütet** (kWh) und **Erlös / entgangener Erlös** (€) – mit Langzeitstatistik, also auch für Tag, Monat und Jahr.
- **Viertelstunden ohne Vergütung** im laufenden Jahr und die daraus folgende **Nachholung** nach § 51a EEG: Volllast-Viertelstunden und das Datum, bis zu dem deine Vergütung dann läuft.
- **Vergütung aktiv**: Binärsensor für Automationen – Speicher laden, Wallbox, Abregeln.
- **Kalender „Negative Preise“** mit den Zeitfenstern ohne Vergütung – heute und, sobald die Day-Ahead-Prognose da ist (meist ab etwa 13 Uhr), morgen.
- **Aktion „Bericht“** für einen frei wählbaren Zeitraum, je Monat aufgeschlüsselt – auch für die Zeit vor der Einrichtung, soweit die Statistik deines Zählers zurückreicht.
- Leitet die **geltende Regel** aus Inbetriebnahme, Leistung und Smart Meter ab – mit manueller Übersteuerung, falls dein Netzbetreiber anders abrechnet.
- **Genau an den Viertelstundengrenzen:** Jedes Zählerdelta wird zeitanteilig auf die Viertelstunden verteilt, jede mit ihrem eigenen Preis. Ein Preis von genau 0 gilt nicht als negativ.
- **Robust:** erkennt Zähler-Resets und unplausible Sprünge und bucht sie nicht; der Stand übersteht Neustarts; die Zeitumstellung (92 bzw. 100 Viertelstunden) ist berücksichtigt.

<img src="https://raw.githubusercontent.com/einspeisewacht/integration/main/assets/screenshots/geraet.png" alt="Geräteseite einer Anlage mit allen Sensoren" width="720">

## Welche Regel gilt (§ 51 EEG)

| Inbetriebnahme | Installierte Leistung | Keine Vergütung, wenn … |
|---|---|---|
| ab 25.02.2025 | ab 100 kW | jede Viertelstunde mit negativem Day-Ahead-Preis |
| ab 25.02.2025 | 2 bis unter 100 kW | wie oben, aber erst ab dem 1. Januar des Jahres **nach** dem Einbau eines intelligenten Messsystems (iMSys) |
| ab 25.02.2025 | unter 2 kW | nicht betroffen |
| 2016 bis 24.02.2025 | ab 400 bzw. 500 kW | zusammenhängend negative Stunden – nicht umgesetzt (siehe unten) |
| sonst | | nicht betroffen |

Ein iMSys ist ein Smart Meter **Gateway** des Messstellenbetreibers; ein digitaler Zähler ohne Gateway zählt nicht. Greift die Regel für deine Anlage noch nicht, legt Einspeisewacht zusätzliche Sensoren an, die zeigen, was dann entgangen wäre.

**Feste Einspeisevergütung gibt es nur bis 100 kW** (§ 21 EEG). Größere Anlagen vermarkten direkt; bei negativen Preisen entfällt dort die Marktprämie, nicht ein fester Satz. Einspeisewacht zählt für sie Energie und Viertelstunden richtig, Erlös und entgangener Erlös sind dann nur ein grober Anhaltspunkt. Die Stunden-Regeln älterer Großanlagen betreffen deshalb nie eine Anlage mit fester Vergütung und sind nicht umgesetzt.

Fundstellen und Details: [docs/ENTWICKLUNG.md](docs/ENTWICKLUNG.md), Abschnitt 2.

## Voraussetzungen

- Home Assistant 2026.3 oder neuer.
- Ein **Einspeisezähler**: fortlaufender Energiesensor (Wh, kWh oder MWh, `state_class` `total` oder `total_increasing`) – am besten der Zähler am Netzanschlusspunkt, z. B. ein Smart Meter des Wechselrichterherstellers.
- Ein **Preissensor** mit Day-Ahead-Prognose je Viertelstunde, z. B. aus der Integration [EPEX Spot](https://github.com/mampfes/ha_epex_spot) (Quelle SMARD.de, Markt DE-LU). Getestet ist das Attribut `data` von EPEX Spot. Ohne Prognose-Attribut gilt der aktuelle Zustand als Preis der laufenden Viertelstunde – dann fehlen Preise für Zeiten, in denen Home Assistant aus war, und aktualisiert sich der Sensor erst einige Minuten nach der Viertelstundengrenze, gilt so lange noch der alte Wert.

<img src="https://raw.githubusercontent.com/einspeisewacht/integration/main/assets/screenshots/integration.png" alt="Einspeisewacht mit zwei Einträgen" width="620">

## Installation (HACS)

**Mit einem Klick:** [![In HACS öffnen](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=einspeisewacht&repository=integration&category=integration) → herunterladen, Home Assistant neu starten → [![Integration hinzufügen](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=einspeisewacht)

Oder von Hand:

1. HACS → ⋮ → *Benutzerdefinierte Repositories* → `https://github.com/einspeisewacht/integration`, Typ *Integration*.
2. Einspeisewacht suchen und herunterladen. Home Assistant neu starten.
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen → Einspeisewacht*.

## Einrichtung

1. **Anlage:** Name, Inbetriebnahme, installierte Leistung (kWp), iMSys und Einbaudatum.
2. **Vergütung:** der Satz aus der Abrechnung deines Netzbetreibers in ct/kWh (nach Abzug der 0,4 ct) – einheitlich oder gestaffelt nach Leistungsstufen. Bei gestaffelter Vergütung bildet Einspeisewacht den Mischsatz nach § 23c EEG.
3. **Datenquellen:** Einspeisezähler und Preissensor.
4. **Regel:** zeigt die abgeleitete Regel, ab wann sie gilt, und den Vergütungssatz. Rechnet dein Netzbetreiber anders ab, kannst du sie übersteuern („jede negative Viertelstunde ab …“ oder „nicht betroffen“). Optional: **frühere negative Viertelstunden von SMARD.de nachzählen** – dann enthält die Nachholung auch die Zeit vor der Einrichtung, und fällt dein Preissensor aus, holt Einspeisewacht die fehlenden Preise ebenfalls von dort (öffentliche Preisdaten, siehe [Datenschutz](#datenschutz)).

<img src="https://raw.githubusercontent.com/einspeisewacht/integration/main/assets/screenshots/einrichtung_regel.png" alt="Letzter Einrichtungsschritt mit der abgeleiteten Regel" width="420">

Mehrere Anlagen oder Zähler: je einen Eintrag anlegen. Ändern: *Einspeisewacht → Eintrag → ⋮ → Neu konfigurieren*.

Was eine Änderung für die Zeit davor bedeutet:

- **Vergütungssatz:** gilt rückwirkend ab der Einrichtung – Erlös und entgangener Erlös werden aus den gebuchten kWh neu berechnet. In der Langzeitstatistik erscheint die Korrektur in der Stunde der Änderung; schon [nachgetragene Statistik](#statistik-nachtragen) bleibt beim alten Satz.
- **Regel** (Inbetriebnahme, Leistung, Smart-Meter-Datum, Übersteuerung): Viertelstunden ohne Vergütung, Nachholung, „Vergütung bis“ und der [Bericht](#bericht-für-einen-zeitraum) folgen sofort der neuen Regel, auch rückwirkend. Die Summen „Einspeisung vergütet/unvergütet“, „Erlös“ und „Entgangener Erlös“ behalten für die Zeit vor der Änderung aber ihre Aufteilung: Eine sinkende kWh-Summe hielte Home Assistant für einen Zählerwechsel und verfälschte die Statistik. Die Werte nach neuer Regel liefert der Bericht. Betrifft die Änderung schon gebuchte Viertelstunden, steht das im Protokoll und in der Diagnose (`rule_change`).
- **Einspeisezähler:** Der neue Zähler beginnt mit eigenem Ausgangswert; die Einspeisung zwischen dem letzten Wert des alten und dem ersten Wert des neuen Zählers wird nicht gebucht.

## Entitäten

| Entität | Typ | Bedeutung |
|---|---|---|
| Einspeisung vergütet | kWh | Netzeinspeisung in Viertelstunden mit Vergütung, seit Einrichtung |
| Einspeisung unvergütet | kWh | Netzeinspeisung in Viertelstunden ohne Vergütung |
| Erlös | € | vergütete Einspeisung × Satz |
| Entgangener Erlös | € | unvergütete Einspeisung × Satz |
| Viertelstunden ohne Vergütung | Anzahl | im laufenden Kalenderjahr, auch ohne Einspeisung (zählt für § 51a); Attribut `years` je Jahr |
| Nachholung | Volllast-Viertelstunden | Viertelstunden × 0,5, aufgerundet; Attribut `months` mit den Verlängerungsmonaten |
| Vergütung bis | Datum | Ende der Förderung einschließlich Nachholung |
| Vergütung aktiv | vergütet/unvergütet | ob die laufende Viertelstunde vergütet wird; unbekannt ohne Preis |
| Negative Preise | Kalender | Zeitfenster mit negativem Preis |
| Regel | Diagnose | die angewandte Regel, Attribute `applies_from` und `rate_ct_per_kwh` |

Solange die Regel noch nicht greift (z. B. ohne iMSys), kommen „Unvergütet bei greifender Regel“, „Entgangener Erlös bei greifender Regel“ und „Viertelstunden ohne Vergütung bei greifender Regel“ dazu; Nachholung und „Vergütung bis“ entfallen dann.

Tages-, Monats- und Jahreswerte: Die Summen-Sensoren haben Langzeitstatistik – z. B. mit der Statistik-Karte (Zeitraum „Monat“, Statistik „Änderung“); eine fertige Karte steht unter [Dashboard-Karte](#dashboard-karte-mit-tages--und-jahreswerten).

## Bericht für einen Zeitraum

*Entwicklerwerkzeuge → Aktionen →* **Einspeisewacht: Bericht**, Anlage und Zeitraum wählen, „Antwort anzeigen“:

```yaml
action: einspeisewacht.report
data:
  config_entry_id: <Eintrag auswählen>
  start: "2026-01-01"
  end: "2026-12-31"
```

Beispielantwort (gekürzt, Werte erfunden):

```yaml
plant: Dach
rule: quarter_hour
rate_ct_per_kwh: 7.94
energy_paid_kwh: 1800.0
energy_unpaid_kwh: 900.0
revenue_eur: 142.92
revenue_lost_eur: 71.46
negative_quarter_hours: 1860
months:
  - month: 2026-04
    energy_paid_kwh: 120.0
    energy_unpaid_kwh: 210.0
    ...
gaps:
  quarter_hours_without_price: 0
```

Die Antwort enthält kWh vergütet und unvergütet, Erlös, entgangenen Erlös und die negativen Viertelstunden – gesamt und je Monat. Grundlage ist die Langzeitstatistik deines Einspeisezählers (Stundenwerte, gleichmäßig auf die vier Viertelstunden verteilt – exakt, wenn alle vier gleich ausgehen, sonst eine gute Näherung). Viertelstunden ohne bekannten Preis zählen als vergütet und stehen unter `gaps` – auch die Zeit, in der Home Assistant länger als 14 Tage aus war; mit der SMARD-Option reichen die Preise bis zur Inbetriebnahme zurück.

## Statistik nachtragen

Die Summen-Sensoren beginnen mit der Einrichtung. Damit Statistik-Karten und Verlauf auch die Zeit davor zeigen, gibt es die Aktion **Einspeisewacht: Statistik nachtragen** (*Entwicklerwerkzeuge → Aktionen*), z. B. ab dem 1. Januar oder ab der Inbetriebnahme:

```yaml
action: einspeisewacht.import_statistics
data:
  config_entry_id: <Eintrag auswählen>
  start: "2026-01-01"
```

Sie rechnet wie der Bericht (Stundenwerte des Zählers gegen die negativen Viertelstunden) und schreibt die Stunden **vor** dem ersten vorhandenen Statistikwert in die Langzeitstatistik von „Einspeisung vergütet/unvergütet“, „Erlös“ und „Entgangener Erlös“; die späteren Summen werden passend verschoben. Voraussetzungen: die SMARD-Option ist an und ihr Abruf fertig (sonst fehlen Preise), und die Sensoren haben schon mindestens eine Stunde Statistik. **Das greift in die Statistik-Datenbank ein – vorher ein Backup anlegen.** Ein zweiter Aufruf findet nichts mehr nachzutragen.

## Was du damit bauen kannst

Der Kalender „Negative Preise“ zeigt die Zeitfenster ohne Vergütung – hier der Tag der Zeitumstellung 2026:

<img src="https://raw.githubusercontent.com/einspeisewacht/integration/main/assets/screenshots/kalender.png" alt="Kalender mit fünf Zeitfenstern ohne Vergütung am 25.10.2026" width="620">

### Dashboard-Karte mit Tages- und Jahreswerten

Die Summen-Sensoren zählen ab der Einrichtung; Tages-, Monats- und Jahreswerte kommen aus ihrer Langzeitstatistik – nach [Statistik nachtragen](#statistik-nachtragen) auch für die Zeit davor. Diese Karte nutzt nur Bordmittel (Werte erfunden):

<img src="https://raw.githubusercontent.com/einspeisewacht/integration/main/assets/screenshots/dashboard.png" alt="Karte mit Balken vergütet/unvergütet je Tag, Erlös und entgangenem Erlös für heute und das Jahr, negativen Viertelstunden, Nachholung und Vergütungsende" width="400">

<details>
<summary>YAML der Karte (Entitäten der Anlage „Dach“ anpassen)</summary>

```yaml
type: vertical-stack
cards:
  - type: statistics-graph
    title: Einspeisung je Tag
    entities:
      - entity: sensor.dach_einspeisung_vergutet
        name: Vergütet
        color: "#27ae60"
      - entity: sensor.dach_einspeisung_unvergutet
        name: Unvergütet (0 ct)
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
        entity: sensor.dach_erlos
        name: Erlös heute
        stat_type: change
        period:
          calendar:
            period: day
      - type: statistic
        entity: sensor.dach_entgangener_erlos
        name: Entgangen heute
        stat_type: change
        period:
          calendar:
            period: day
      - type: statistic
        entity: sensor.dach_erlos
        name: Erlös Jahr
        stat_type: change
        period:
          calendar:
            period: year
      - type: statistic
        entity: sensor.dach_entgangener_erlos
        name: Entgangen Jahr
        stat_type: change
        period:
          calendar:
            period: year
  - type: entities
    title: Negative Preise in diesem Jahr
    entities:
      - entity: sensor.dach_viertelstunden_ohne_vergutung
        name: Ohne Vergütung
      - entity: sensor.dach_nachholung
        name: Nachholung
      - entity: sensor.dach_vergutung_bis
        name: Vergütung bis
  - type: tile
    entity: binary_sensor.dach_vergutung_aktiv
    name: Jetzt
```

</details>

### Fertiger Blueprint

| Blueprint | Was er tut | |
|---|---|---|
| **Bei negativem Preis umschalten** | führt eigene Aktionen aus, sobald die Vergütung entfällt (z. B. Speicher laden, Wallbox an, abregeln), und andere, sobald sie wieder gezahlt wird | [![Blueprint importieren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Feinspeisewacht%2Fintegration%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Feinspeisewacht%2Fvergutung_aus_an.yaml) |

### Speicher laden, solange es keine Vergütung gibt (als eigene Automation)

```yaml
alias: Speicher bei negativem Preis laden
triggers:
  - trigger: state
    entity_id: binary_sensor.dach_vergutung_aktiv
    to: "off"
actions:
  - action: select.select_option
    target:
      entity_id: select.wechselrichter_speichermodus   # deine Entität
    data:
      option: "Laden aus PV"
mode: single
```

### Hinweis am Vortag

```yaml
alias: Morgen gibt es Viertelstunden ohne Vergütung
triggers:
  - trigger: calendar
    event: start
    offset: "-12:00:00"
    entity_id: calendar.dach_negative_preise
conditions:
  - condition: template
    value_template: "{{ trigger.calendar_event.summary == 'Keine Einspeisevergütung' }}"
actions:
  - action: notify.mobile_app_mein_handy   # dein Gerät
    data:
      title: Negative Strompreise
      message: >-
        {{ as_timestamp(trigger.calendar_event.start) | timestamp_custom('%H:%M') }}–{{
        as_timestamp(trigger.calendar_event.end) | timestamp_custom('%H:%M') }} Uhr ohne Vergütung.
mode: queued
```

Die Entitäts-IDs hängen vom Namen deiner Anlage ab (hier „Dach“).

## Datenschutz

Einspeisewacht rechnet lokal und liest nur die Entitäten, die du auswählst. Einzige Ausnahme, nur wenn du sie einschaltest: Die SMARD-Option lädt öffentliche Day-Ahead-Preise von smard.de (Bundesnetzagentur) – einmalig für die Zeit vor der Einrichtung und danach nur, wenn dein Preissensor länger als eine Stunde keine Preise liefert (höchstens einmal je Stunde). Dabei wird nichts über dich oder deine Anlage übertragen – nur der Abruf der Preisdateien mit der Kennung `Einspeisewacht/<Version>`. Die Diagnose-Datei enthält weder den Anlagennamen noch Zählerstände, Energie- oder Erlössummen.

## Was Einspeisewacht nicht kann

- **Keine Abrechnung:** Abweichungen zur Abrechnung des Netzbetreibers sind normal (andere Messung, Rundung).
- **Keine Direktvermarktung:** Marktprämie und Ausfallvergütung bildet Einspeisewacht nicht ab (siehe oben, über 100 kW).
- **Keine Altregeln** für Großanlagen (Stunden-Blöcke 2016 bis 24.02.2025).
- **Freiwilliger Wechsel ins neue Regime** (§ 100 Abs. 47 EEG, +0,6 ct/kWh) wird nicht angeboten, solange die beihilferechtliche Genehmigung der EU fehlt.
- **Der Zähler muss die Netzeinspeisung messen.** Ein Erzeugungszähler (PV-Ertrag) zählt auch Eigenverbrauch und Speicherladung mit – die sind von der Regel nicht betroffen.
- Die Summen-Sensoren beginnen bei der Einrichtung; für die Zeit davor gibt es die Aktionen „Bericht“ und „Statistik nachtragen“.

## Fehlerbehebung

- **Werte bleiben bei 0:** Prüfe, ob der Einspeisezähler Werte liefert und ob die Regel schon greift (Sensor „Regel“, Attribut `applies_from`).
- **„Vergütung aktiv“ ist unbekannt:** Der Preissensor liefert für die laufende Viertelstunde keinen Preis.
- **Hinweis „SMARD.de nicht erreichbar“ unter Reparaturen:** Der Abruf früherer Preise ist fehlgeschlagen; beim nächsten Start von Home Assistant wird es erneut versucht. Die laufende Buchung ist nicht betroffen.
- **Diagnose:** *Einspeisewacht → Eintrag → ⋮ → Diagnose herunterladen*. **Debug-Protokoll:** *Einspeisewacht → ⋮ → Debug-Protokollierung aktivieren*.

## Entfernen

1. *Einstellungen → Geräte & Dienste → Einspeisewacht* → bei jedem Eintrag ⋮ → *Löschen*. Die gespeicherten Buchungen dieses Eintrags werden mit gelöscht.
2. Optional: HACS → Einspeisewacht → ⋮ → *Entfernen*, dann Home Assistant neu starten.

Die Langzeitstatistik der gelöschten Sensoren bleibt in Home Assistant erhalten, bis du sie unter *Entwicklerwerkzeuge → Statistik* entfernst.

## Fehler melden

Bitte als [Issue](https://github.com/einspeisewacht/integration/issues) – am besten mit Diagnose-Datei und den Versionen von Home Assistant und Einspeisewacht. Sicherheitslücken bitte vertraulich, siehe [SECURITY.md](SECURITY.md).

## Lizenz und Quellen

MIT. Historische Day-Ahead-Preise (optional): Bundesnetzagentur | [SMARD.de](https://www.smard.de), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); Einspeisewacht zählt daraus nur die negativen Viertelstunden.
