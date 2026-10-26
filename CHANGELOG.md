# Changelog

## 0.1.0b1 – 2026-10-26

Erste Vorab-Version (MVP) zum Testen.

- **Einspeisung vergütet / unvergütet** (kWh) und **Erlös / entgangener Erlös** (€): jedes Zählerdelta wird zeitanteilig auf die Viertelstunden verteilt und mit dem Day-Ahead-Preis genau dieser Viertelstunde bewertet. Ein Preis von genau 0 ist nicht negativ.
- **Viertelstunden ohne Vergütung** im laufenden Jahr (§ 51a EEG; zählt auch ohne Einspeisung).
- **Vergütung aktiv**: Binärsensor für die laufende Viertelstunde.
- **Regel** aus Inbetriebnahme, Leistung und iMSys abgeleitet (§ 51 EEG i. d. F. des Solarspitzengesetzes), manuell übersteuerbar. Greift die Regel noch nicht, zeigen zusätzliche Sensoren, was entgangen wäre. Stunden-Regeln für Großanlagen (2016 bis 24.02.2025) werden erkannt, aber noch nicht berechnet.
- **Vergütungssatz** einheitlich oder gestaffelt nach Leistungsstufen (Mischsatz nach § 23c EEG).
- Preisquelle: Prognose-Attribut `data` (z. B. EPEX Spot), sonst der aktuelle Zustand.
- Zähler-Resets und unplausible Sprünge werden nicht gebucht; Stand übersteht Neustarts; Diagnose ohne personenbezogene Daten.
- Projektgerüst: CI (Tests, hassfest, HACS, Kompatibilität mit HA 2026.3), Release-ZIP-Workflow; Preis-Fixture 25.10.2026 (Zeitumstellung).
