# Changelog

## Unveröffentlicht

- **Weniger Schreibzugriffe** (wichtig auf SD-Karten): Der laufende Stand (~1 KB) wird höchstens alle 10 Minuten gespeichert, Preise und negative Viertelstunden nur, wenn sie sich ändern. Bisher wurde der ganze Stand nach jeder Ruhepause neu geschrieben – und tagsüber bei laufender Einspeisung gar nicht. Ältere Speicherstände werden übernommen.
- **Lücken nach Sonnenstand:** War Home Assistant länger als eine Stunde aus, wird die Einspeisung der Lücke nach der Sonnenhöhe am Standort verteilt (nachts nichts) statt gleichmäßig. Die Diagnose zählt solche Lücken.
- **Hinweise unter Reparaturen**, wenn der Preissensor länger als eine Stunde keinen Preis für die laufende Viertelstunde liefert oder der Zähler eine nicht unterstützte Einheit meldet – statt still als vergütet zu buchen. Sie verschwinden von selbst.
- Ein fehlgeschlagener SMARD-Abruf wird jetzt auch ohne Neustart täglich wiederholt.

## 0.1.0b4 – 2026-10-26

- **Eigenes Icon und Logo** (Viertelstunden in Verkehrsgrün), sichtbar in Home Assistant und HACS.
- Ausführliches README auf Deutsch und Englisch, mit Beispielen, Datenschutz, Grenzen, Fehlerbehebung und Entfernen.
- **Fehler behoben:** Anlagen über 10 kWp mit einheitlichem Vergütungssatz ließen sich nicht einrichten bzw. starten (es wurde fälschlich ein Mischsatz über Leistungsstufen gebildet).
- Einrichtung: Hinweis für Anlagen über 100 kW – dort gibt es keine feste Einspeisevergütung (§ 21 EEG), Erlöse sind nur ein grober Anhaltspunkt. Die Stunden-Regeln älterer Großanlagen werden deshalb nicht umgesetzt.
- **Aktion „Bericht“ (`einspeisewacht.report`)** für einen frei wählbaren Zeitraum: Einspeisung vergütet/unvergütet, Erlös, entgangener Erlös und negative Viertelstunden, je Monat aufgeschlüsselt. Rechnet mit der Langzeitstatistik des Zählers – also auch für die Zeit vor der Einrichtung, soweit die Statistik zurückreicht (Stundenwerte, gleichmäßig auf die Viertelstunden verteilt). Viertelstunden ohne bekannten Preis werden als Lücke ausgewiesen.
- Einspeisewacht merkt sich die negativen Viertelstunden selbst. Ändert sich die Regel, stimmen die Zahlen sofort, ohne neuen Abruf. Nach dem Update wird einmal neu gezählt (mit SMARD-Option automatisch ab Inbetriebnahme).

## 0.1.0b3 – 2026-10-26

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
