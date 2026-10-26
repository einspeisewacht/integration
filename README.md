<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/einspeisewacht/integration/main/assets/github/readme-header-dark@2x.png">
  <img alt="Einspeisewacht – Jede Viertelstunde im Blick." src="https://raw.githubusercontent.com/einspeisewacht/integration/main/assets/github/readme-header-light@2x.png" width="640">
</picture>

[![Release](https://img.shields.io/github/v/release/einspeisewacht/integration?color=008351)](https://github.com/einspeisewacht/integration/releases)
[![CI](https://github.com/einspeisewacht/integration/actions/workflows/ci.yml/badge.svg)](https://github.com/einspeisewacht/integration/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-F5A623.svg)](LICENSE)

🇩🇪 **Deutsch** · 🇬🇧 [English](https://github.com/einspeisewacht/integration/blob/main/README.en.md)

> ℹ️ **Beta.** Einspeisewacht ist neu und wird gerade auf echten Anlagen erprobt. Rückmeldungen sind sehr willkommen – siehe [Fehler melden](#fehler-melden).

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
- Ein **Preissensor** mit Day-Ahead-Prognose je Viertelstunde, z. B. aus der Integration [EPEX Spot](https://github.com/mampfes/ha_epex_spot) (Quelle SMARD.de, Markt DE-LU). Getestet ist das Attribut `data` von EPEX Spot; ohne Prognose-Attribut nutzt Einspeisewacht den aktuellen Zustand.

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
4. **Regel:** zeigt die abgeleitete Regel, ab wann sie gilt, und den Vergütungssatz. Rechnet dein Netzbetreiber anders ab, kannst du sie übersteuern („jede negative Viertelstunde ab …“ oder „nicht betroffen“). Optional: **frühere negative Viertelstunden von SMARD.de nachzählen** – dann enthält die Nachholung auch die Zeit vor der Einrichtung (einmaliger Abruf öffentlicher Preisdaten, siehe [Datenschutz](#datenschutz)).

Mehrere Anlagen oder Zähler: je einen Eintrag anlegen. Ändern: *Einspeisewacht → Eintrag → ⋮ → Neu konfigurieren*.

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
| Vergütung aktiv | an/aus | ob die laufende Viertelstunde vergütet wird; unbekannt ohne Preis |
| Negative Preise | Kalender | Zeitfenster mit negativem Preis |
| Regel | Diagnose | die angewandte Regel, Attribute `applies_from` und `rate_ct_per_kwh` |

Solange die Regel noch nicht greift (z. B. ohne iMSys), kommen „Unvergütet bei greifender Regel“, „Entgangener Erlös bei greifender Regel“ und „Viertelstunden ohne Vergütung bei greifender Regel“ dazu; Nachholung und „Vergütung bis“ entfallen dann.

Tages-, Monats- und Jahreswerte: Die Summen-Sensoren haben Langzeitstatistik – z. B. mit der Statistik-Karte (Zeitraum „Monat“, Statistik „Änderung“).

## Bericht für einen Zeitraum

*Entwicklerwerkzeuge → Aktionen →* **Einspeisewacht: Bericht**, Anlage und Zeitraum wählen, „Antwort anzeigen“:

```yaml
action: einspeisewacht.report
data:
  config_entry_id: <Eintrag auswählen>
  start: "2026-01-01"
  end: "2026-12-31"
```

Die Antwort enthält kWh vergütet und unvergütet, Erlös, entgangenen Erlös und die negativen Viertelstunden – gesamt und je Monat. Grundlage ist die Langzeitstatistik deines Einspeisezählers (Stundenwerte, gleichmäßig auf die vier Viertelstunden verteilt – exakt, wenn alle vier gleich ausgehen, sonst eine gute Näherung). Viertelstunden ohne bekannten Preis zählen als vergütet und stehen unter `gaps`; mit der SMARD-Option reichen die Preise bis zur Inbetriebnahme zurück.

## Was du damit bauen kannst

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

Einspeisewacht rechnet lokal und liest nur die Entitäten, die du auswählst. Einzige Ausnahme, nur wenn du sie einschaltest: Die SMARD-Option lädt einmalig öffentliche Day-Ahead-Preise von smard.de (Bundesnetzagentur). Dabei wird nichts über dich oder deine Anlage übertragen – nur der Abruf der Preisdateien mit der Kennung `Einspeisewacht/<Version>`. Die Diagnose-Datei enthält weder den Anlagennamen noch Zählerstände, Energie- oder Erlössummen.

## Was Einspeisewacht nicht kann

- **Keine Abrechnung:** Abweichungen zur Abrechnung des Netzbetreibers sind normal (andere Messung, Rundung).
- **Keine Direktvermarktung:** Marktprämie und Ausfallvergütung bildet Einspeisewacht nicht ab (siehe oben, über 100 kW).
- **Keine Altregeln** für Großanlagen (Stunden-Blöcke 2016 bis 24.02.2025).
- **Freiwilliger Wechsel ins neue Regime** (§ 100 Abs. 47 EEG, +0,6 ct/kWh) wird nicht angeboten, solange die beihilferechtliche Genehmigung der EU fehlt.
- **Der Zähler muss die Netzeinspeisung messen.** Ein Erzeugungszähler (PV-Ertrag) zählt auch Eigenverbrauch und Speicherladung mit – die sind von der Regel nicht betroffen.
- Die Summen-Sensoren beginnen bei der Einrichtung; für die Zeit davor gibt es die Aktion „Bericht“.

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
