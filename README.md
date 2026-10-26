# Einspeisewacht

**Wie viel deiner PV-Einspeisung wird wegen negativer Strompreise nicht vergütet?**
Einspeisewacht ist eine Home-Assistant-Integration für PV-Anlagen mit fester Einspeisevergütung. Sie bucht jede Viertelstunde Einspeisung gegen den Day-Ahead-Preis genau dieser Viertelstunde und zeigt, was vergütet wurde, was nicht – und was das kostet.

> **Beta.** Einspeisewacht ist neu und wird gerade auf echten Anlagen erprobt. Rückmeldungen gern als [Issue](https://github.com/einspeisewacht/integration/issues).

> **Keine Rechts- oder Abrechnungsberatung.** Die Werte sind eine Orientierung. Maßgeblich ist die Abrechnung deines Netzbetreibers – er rechnet mit den Messwerten deines Zählers, Home Assistant meist mit Wechselrichter- oder Lesekopfwerten.

## Was Einspeisewacht kann

- **Einspeisung vergütet / unvergütet** (kWh) und **Erlös / entgangener Erlös** (€) – für Energie-Dashboard und Langzeitstatistik.
- **Viertelstunden ohne Vergütung** im laufenden Jahr und die daraus folgende **Nachholung** nach § 51a EEG: Volllast-Viertelstunden und das Datum, bis zu dem die Vergütung dann läuft.
- **Kalender „Negative Preise“** mit den Zeitfenstern ohne Vergütung – heute und, sobald die Prognose da ist, morgen.
- **Vergütung aktiv** – Binärsensor für Automationen (Speicher laden, Wallbox, Abregeln).
- Leitet die **geltende Regel** aus Inbetriebnahme, Leistung und Smart Meter ab – mit manueller Übersteuerung.
- Bucht an Viertelstundengrenzen exakt: Ein Zählerdelta wird zeitanteilig auf die Viertelstunden verteilt, jede mit ihrem eigenen Preis. Ein Preis von genau 0 gilt nicht als negativ.
- Erkennt Zähler-Resets und unplausible Sprünge und bucht sie nicht. Der Stand übersteht Neustarts.
- Lokal: liest nur vorhandene Entitäten. Einzige Ausnahme, nur auf Wunsch: einmaliger Abruf früherer Preise von SMARD.de, damit die Nachholung auch die Zeit vor der Einrichtung enthält.

## Welche Regel gilt (§ 51 EEG)

| Inbetriebnahme | Leistung | Keine Vergütung, wenn … |
|---|---|---|
| ab 25.02.2025 | ab 100 kW | jede Viertelstunde mit negativem Preis |
| ab 25.02.2025 | 2 bis unter 100 kW | wie oben, aber erst ab dem 1. Januar des Jahres **nach** dem Einbau eines intelligenten Messsystems (iMSys) |
| ab 25.02.2025 | unter 2 kW | nicht betroffen |
| 2016 bis 24.02.2025 | ab 400 bzw. 500 kW | zusammenhängend negative Stunden – nicht unterstützt (siehe unten) |
| sonst | | nicht betroffen |

**Einspeisewacht ist für die feste Einspeisevergütung gebaut – die gibt es nur bis 100 kW** (§ 21 EEG). Größere Anlagen vermarkten direkt; bei negativen Preisen entfällt dort die Marktprämie, nicht ein fester Satz. Einspeisewacht zählt für sie Energie und Viertelstunden richtig, Erlös und entgangener Erlös sind dann nur ein grober Anhaltspunkt. Die Stunden-Regeln älterer Großanlagen betreffen deshalb nie eine Anlage mit fester Vergütung und sind nicht umgesetzt.

Greift die Regel für deine Anlage noch nicht (z. B. ohne iMSys), zeigt Einspeisewacht zusätzlich, was dann entgangen wäre. Details und Fundstellen: [docs/ENTWICKLUNG.md](docs/ENTWICKLUNG.md).

## Voraussetzungen

- Home Assistant 2026.3 oder neuer.
- Ein **Einspeisezähler**: fortlaufender Energiesensor (Wh, kWh oder MWh), am besten der Zähler am Netzanschlusspunkt.
- Ein **Preissensor** mit Day-Ahead-Prognose je Viertelstunde, z. B. aus der Integration [EPEX Spot](https://github.com/mampfes/ha_epex_spot) (Quelle SMARD.de, Markt DE-LU).

## Installation

1. HACS → ⋮ → *Benutzerdefinierte Repositories* → `https://github.com/einspeisewacht/integration`, Typ *Integration*.
2. Einspeisewacht suchen und herunterladen. Home Assistant neu starten.
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen → Einspeisewacht*.

## Einrichtung

1. **Anlage:** Name, Inbetriebnahme, installierte Leistung (kWp), iMSys und Einbaudatum.
2. **Vergütung:** Satz aus der Abrechnung des Netzbetreibers (ct/kWh) – einheitlich oder gestaffelt nach Leistungsstufen (Mischsatz nach § 23c EEG).
3. **Datenquellen:** Einspeisezähler und Preissensor.
4. **Regel:** zeigt die abgeleitete Regel; bei abweichender Abrechnung übersteuerbar.

Mehrere Anlagen oder Zähler: je einen Eintrag anlegen. Ändern: *Einspeisewacht → ⋮ → Neu konfigurieren*.

## Bericht für einen Zeitraum

*Entwicklerwerkzeuge → Aktionen →* **Einspeisewacht: Bericht**, Anlage und Zeitraum wählen, „Antwort anzeigen“. Beispiel:

```yaml
action: einspeisewacht.report
data:
  config_entry_id: <Eintrag auswählen>
  start: "2026-01-01"
  end: "2026-12-31"
```

Die Antwort enthält kWh vergütet und unvergütet, Erlös, entgangenen Erlös und die negativen Viertelstunden, je Monat aufgeschlüsselt. Grundlage ist die Langzeitstatistik deines Einspeisezählers (Stundenwerte) – damit auch die Zeit vor der Einrichtung, wenn die SMARD-Option aktiv ist. Fehlende Preise oder Zählerwerte stehen unter `gaps`.

## Lizenz und Quellen

MIT. Historische Day-Ahead-Preise (optional): Bundesnetzagentur | [SMARD.de](https://www.smard.de), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); Einspeisewacht zählt daraus nur negative Viertelstunden.
