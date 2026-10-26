# Changelog

## Unveröffentlicht

- **Nachholung (§ 51a EEG):** Sensor „Nachholung“ in Volllast-Viertelstunden (negative Viertelstunden × 0,5, aufgerundet) mit den Verlängerungsmonaten, und „Vergütung bis“ mit dem Ende der Förderung einschließlich Verlängerung (reguläres Ende: 31.12. des 20. Jahres nach dem Inbetriebnahmejahr).
- **Kalender „Negative Preise“:** zusammenhängende Viertelstunden mit negativem Preis als Termine – „Keine Einspeisevergütung“ oder, solange die Regel noch nicht greift, „Negativer Preis (noch vergütet)“. Heute, morgen (sobald die Prognose da ist) und die letzten zwei Wochen.
- **Optional: frühere Viertelstunden von SMARD.de nachzählen.** Einmaliger Abruf der Day-Ahead-Preise seit Inbetriebnahme (Bundesnetzagentur | SMARD.de, CC BY 4.0), damit die Nachholung auch die Zeit vor der Einrichtung enthält. Fehler blockieren nichts und erscheinen unter *Reparaturen*.
- Ändert sich die Regel (z. B. nach „Neu konfigurieren“), beginnt die Zählung der Viertelstunden neu – mit SMARD-Option wieder ab Inbetriebnahme.

## 0.1.0b2 – 2026-10-26

- Erscheint jetzt unter **Integrationen** statt unter Helfer.
- Einrichtung: Inbetriebnahme und iMSys-Einbau dürfen nicht in der Zukunft liegen; greift die Regel erst in einem künftigen Jahr, weist der letzte Schritt darauf hin (häufig ein vertipptes Jahr).

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
