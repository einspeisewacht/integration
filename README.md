# Einspeisewacht

**Wie viel deiner PV-Einspeisung wird wegen negativer Strompreise nicht vergütet?**
Einspeisewacht ist eine Home-Assistant-Integration für PV-Anlagen mit fester Einspeisevergütung. Sie bucht jede Viertelstunde Einspeisung gegen den Day-Ahead-Preis genau dieser Viertelstunde und zeigt, was vergütet wurde, was nicht – und was das kostet.

> **Beta.** Einspeisewacht ist neu und wird gerade auf echten Anlagen erprobt. Rückmeldungen gern als [Issue](https://github.com/einspeisewacht/integration/issues).

> **Keine Rechts- oder Abrechnungsberatung.** Die Werte sind eine Orientierung. Maßgeblich ist die Abrechnung deines Netzbetreibers – er rechnet mit den Messwerten deines Zählers, Home Assistant meist mit Wechselrichter- oder Lesekopfwerten.

## Was Einspeisewacht kann

- **Einspeisung vergütet / unvergütet** (kWh) und **Erlös / entgangener Erlös** (€) – für Energie-Dashboard und Langzeitstatistik.
- **Viertelstunden ohne Vergütung** im laufenden Jahr – Grundlage der Nachholung nach § 51a EEG.
- **Vergütung aktiv** – Binärsensor für Automationen (Speicher laden, Wallbox, Abregeln).
- Leitet die **geltende Regel** aus Inbetriebnahme, Leistung und Smart Meter ab – mit manueller Übersteuerung.
- Bucht an Viertelstundengrenzen exakt: Ein Zählerdelta wird zeitanteilig auf die Viertelstunden verteilt, jede mit ihrem eigenen Preis. Ein Preis von genau 0 gilt nicht als negativ.
- Erkennt Zähler-Resets und unplausible Sprünge und bucht sie nicht. Der Stand übersteht Neustarts.
- Rein lokal: liest nur vorhandene Entitäten, keine Cloud.

## Welche Regel gilt (§ 51 EEG)

| Inbetriebnahme | Leistung | Keine Vergütung, wenn … |
|---|---|---|
| ab 25.02.2025 | ab 100 kW | jede Viertelstunde mit negativem Preis |
| ab 25.02.2025 | 2 bis unter 100 kW | wie oben, aber erst ab dem 1. Januar des Jahres **nach** dem Einbau eines intelligenten Messsystems (iMSys) |
| ab 25.02.2025 | unter 2 kW | nicht betroffen |
| 2016 bis 24.02.2025 | ab 400 bzw. 500 kW | zusammenhängend negative Stunden – **noch nicht unterstützt** |
| sonst | | nicht betroffen |

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

## Lizenz

MIT
