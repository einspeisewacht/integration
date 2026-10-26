# Einspeisewacht – Entwicklerdokumentation

Stand: 2026-10-26 (Projektstart). Vor größeren Arbeiten lesen.

## 1. Ziel und Umfang

Einspeisewacht zeigt PV-Betreibern mit fester Einspeisevergütung, wie viel Netzeinspeisung wegen negativer Day-Ahead-Preise unvergütet bleibt, was das kostet und wie viel Förderzeit dadurch ans Ende angehängt wird. Sie ersetzt Eigenbau-Lösungen aus Utility Meter, Tarifwechsel-Automation und Template-Sensoren.

Abgrenzung (geprüft 2026-10-22/24, keine vergleichbare Integration):

| Projekt | Was es tut | Warum keine Lösung |
|---|---|---|
| [hacs-einspeiseverguetung](https://github.com/Hoffis-Welt/hacs-einspeiseverguetung) | Karte: Vergütung gegen Abschläge | Kennt keine Nullvergütung und keine Nachholung |
| [pv_curtailment](https://github.com/milanhin/pv_curtailment) | Regelt den Wechselrichter ab | Steuert, wertet nicht aus |
| [EEGEnergyOptimizer2](https://github.com/RobertHell82/EEGEnergyOptimizer2) | Batterie-Fahrplan | Österreichisch, „EEG“ = Energiegemeinschaft |
| [evcc PR #33635](https://github.com/evcc-io/evcc/pull/33635) | Tarif ohne Vergütung bei negativem Preis | Nur Ladeplanung, keine Auswertung |

Fahrplan:

1. **MVP:** Config Flow, Regel „jede negative Viertelstunde“ inkl. Smart-Meter-Weiche, Sensoren vergütet/unvergütet, Erlös, entgangener Erlös, Binärsensor „Vergütung aktiv“. Parallel zur Eigenbau-Lösung laufen lassen und vergleichen.
2. Altregeln für Großanlagen, freiwilliger Wechsel, Nachholung, Kalender.
3. Nachberechnung aus der Statistik, Service `einspeisewacht.report`, Diagnose, Übersetzungen.
4. Veröffentlichung: README mit Rechtshinweis, Release, simon42- und HA-Community-Forum, Hinweis im evcc-PR #33635.

## 2. Rechtliche Regeln (keine Rechtsberatung)

Geprüft am 2026-10-26 am Wortlaut. Geltender Text: [gesetze-im-internet.de](https://www.gesetze-im-internet.de/eeg_2014/) (Stand: zuletzt geändert 18.12.2025) und Solarspitzengesetz [BGBl. 2025 I Nr. 51](https://www.recht.bund.de/bgbl/1/2025/51/regelungstext.pdf). Alte Fassungen über die Versionshistorie von [buzer.de](https://www.buzer.de/gesetz/11230/) (nicht amtlich). Maßgeblich ist die Abrechnung des Netzbetreibers.

### Welche Regel gilt

| Inbetriebnahme | Installierte Leistung (§ 3 Nr. 31, zusammengefasst nach § 24) | Keine Vergütung, wenn … | Nachholung (§ 51a) |
|---|---|---|---|
| ab 25.02.2025 | ≥ 100 kW | jede Viertelstunde mit Spotmarktpreis < 0 | ja; PV: Viertelstunden × 0,5 → Monatskontingente |
| ab 25.02.2025 | 2 bis < 100 kW | wie oben, aber erst ab 1.1. des Jahres **nach** dem iMSys-Einbau (§ 51 Abs. 2 Satz 1 Nr. 1) | ja, ab dann |
| ab 25.02.2025 | < 2 kW | nicht betroffen bis Ende des Jahres einer BNetzA-Festlegung nach § 85 Abs. 2 Nr. 12 (keine bekannt) | – |
| 01.01.2023–24.02.2025 | ≥ 400 kW | zusammenhängend negative Stunden: 2023 ≥ 4 h, 2024/2025 ≥ 3 h, 2026 ≥ 2 h, ab 2027 ≥ 1 h → **ganzer Block** null (§ 51 a. F. über § 100 Abs. 46) | nur bei Ausschreibungszuschlag; Stunden → volle Tage |
| 2021–2022 | ≥ 500 kW | ≥ 4 h zusammenhängend → ganzer Block null (EEG 2021) | nur bei Ausschreibungszuschlag |
| 2016–2020 | Wind ≥ 3 MW, sonstige ≥ 500 kW | ≥ 6 h zusammenhängend → ganzer Block null (EEG 2021 § 100 Abs. 2 Nr. 13) | keine |
| vor 2016, und alles unterhalb der Schwellen bis 24.02.2025 | – | nicht betroffen | – |

- **§ 51 Abs. 1:** „Für Zeiträume, in denen der Spotmarktpreis negativ ist, verringert sich der anzulegende Wert auf null.“ „Negativ“ = strikt < 0 (das Gesetz schreibt „oder weniger“, wenn es 0 mitmeint, vgl. § 51b).
- **Spotmarktpreis (§ 3 Nr. 42a):** Day-Ahead, Preiszone Deutschland, Viertelstundenkontrakte (seit Lieferung 01.10.2025).
- **Stunden-Regime seit der Viertelstunden-Umstellung (§ 100 Abs. 45 Satz 2):** eine Kalenderstunde ist negativ, wenn das arithmetische Mittel ihrer vier Viertelstundenpreise negativ ist.
- **Einspeisevergütung:** Anspruch wird null, nie negativ (§ 23 Abs. 3 Nr. 2). Unvergütete Menge = eigene Netzeinspeisung in den betroffenen Viertelstunden.
- **Schwellen** sind „weniger als“: genau 2,0 kW bzw. 100 kW sind betroffen. Das Gesetz sagt kW installierte Leistung; bei PV gilt praktisch die Modulleistung (kWp) – nicht am Primärtext geprüft.
- **60-%-Grenze (§ 9 Abs. 2):** Neuanlagen < 100 kW in Einspeisevergütung bis iMSys + Steuerung. Betrifft die Menge, nicht die Vergütung – höchstens ein Hinweis.

### Freiwilliger Wechsel (§ 100 Abs. 47)

Nur für Anlagen, deren Wert bei negativen Preisen bisher **gar nicht** sinkt. Erklärung in Textform an den Netzbetreiber, wirksam frühestens zum Ablauf des Jahres des iMSys-Einbaus; danach +0,6 ct/kWh auf den anzulegenden Wert. **Derzeit nicht anwendbar:** § 101 Abs. 1 stellt die Regel unter Beihilfevorbehalt, die EU-Genehmigung fehlt (BT-Drs. 21/7867, Begründung S. 251, Stand 07.09.2026).

### Nachholung (§ 51a)

- Gilt für Anlagen unter dem geltenden § 51 (ab 25.02.2025 oder gewechselt). Gezählt werden die Viertelstunden mit Nullstellung im Inbetriebnahmejahr und den 19 Folgejahren – **unabhängig von der eigenen Einspeisung** (auch nachts), aber nicht vor Greifen der iMSys-Ausnahme.
- PV (§ 51a Abs. 2): Anzahl × 0,5, auf volle Viertelstunde aufgerundet = Volllastviertelstunden. Verbrauch gegen Monatskontingente ab dem 1.1. nach Ende des regulären Zeitraums (§ 25 Abs. 1 Satz 2: 31.12. des 20. Zahlungsjahres; das Inbetriebnahmejahr ist ein Rumpfjahr davor – Inbetriebnahme 2025 → Ende 31.12.2045, gezählt wird 2025–2044); Verlängerung bis zum Ende des Monats, in den die letzte Volllastviertelstunde fällt (Satz 6). Untermonatliches Ende: anteilig (Satz 4).
- Monatskontingente (§ 51a Abs. 2 Satz 3): Jan 87, Feb 189, Mär 340, Apr 442, Mai 490, Jun 508, Jul 498, Aug 453, Sep 371, Okt 231, Nov 118, Dez 73 (Summe 3.800).
- Beispiel: 600 negative Viertelstunden → 300 Volllastviertelstunden → Jan + Feb = 276, Rest 24 im März → Verlängerung bis 31. März.

### EEG 2027 (Regierungsentwurf, BT-Drs. 21/7867)

Nicht verabschiedet (2./3. Lesung voraussichtlich 9.–13.11.2026, Bundesrat 20.11.2026, Inkrafttreten geplant 01.01.2027). Nur für Neuanlagen ab 2027: Nullstellung von Zahlungsanspruch und Rückzahlungspflicht; die Ausnahme < 100 kW gilt nur noch bei Netzbetreiberabnahme/Mieterstrom; § 51a unverändert (Faktor 0,5, Kontingente); Wechsel (neuer § 102) auch für Stunden-Regime, unwiderruflich. Nach Verabschiedung neu prüfen.

### Ungeklärt (Auslegung)

- Zählfenster § 51a: Viertelstunden im 20. Zahlungsjahr und in der Verlängerung zählen nach dem Wortlaut nicht.
- Gewechselte PV-Altanlagen: § 100 Abs. 46 Satz 2 schließt § 51a Abs. 2 für PV vor 25.02.2025 aus – dann nur Abs. 1 (Tage statt Kontingente)?
- Negativ-Blöcke über den Jahreswechsel bei den Stunden-Regimen.

## 3. Datenquellen – verifizierte Eigenheiten (geprüft 2026-10-26)

### Preis: EPEX Spot (mampfes), Quelle SMARD.de

- Zustand: Preis der laufenden Viertelstunde in €/kWh, `state_class: measurement`. Wechselt ca. 0,1–0,4 s **nach** der Viertelstundengrenze. Wer bei Zustandsänderung umschaltet (Eigenbau), bucht deshalb an jeder Grenze kurz mit dem alten Preis.
- Attribut `data`: Liste `{start_time, end_time, price_per_kwh}`, Zeitstempel ISO mit Offset (Europe/Berlin), Preise in €/kWh. Enthielt am 26.10. um 09:22 die Einträge ab **25.10. 01:00** bis 27.10. 00:00 – also auch Vergangenes vom Vortag.
- Zeitumstellung (25.10.2026): ein Eintrag `02:45+02:00 → 02:00+01:00`, danach `02:00+01:00` usw. In UTC lückenlos.
- Preise exakt `0` sind häufig (25.10.: 48 von 100 Viertelstunden), minimal negativ `-0.00001`.
- **Der Recorder speichert das Attribut `data` nicht** (nur `price_per_kwh` usw.). Vergangene Prognosen sind also nicht aus der Historie abrufbar; Preise vergangener Viertelstunden aber aus dem Zustandsverlauf (Schrittfunktion, ~10 Tage) bzw. der Langzeitstatistik (`measurement` → nur Stundenmittel!).
- Fixture: `tests/fixtures/epex_spot_2026-10-25.json` (Attribut wörtlich, 25.10. 00:00–01:00 aus dem Zustandsverlauf ergänzt; alle 138 Viertelstunden gegen den Verlauf geprüft).

### SMARD.de (optional, geprüft 2026-10-26)

- Index: `https://www.smard.de/app/chart_data/4169/DE-LU/index_quarterhour.json` → `{"timestamps": [ms, …]}`, je ein Wochenbeginn (Montag 00:00 Ortszeit), seit Oktober 2018.
- Woche: `…/4169_DE-LU_quarterhour_<ms>.json` → `{"meta_data": …, "series": [[ms, €/MWh], …]}`; Zeitumstellungswoche 676 Werte. Fehlende Werte wären `null`.
- **Vor dem 01.10.2025 wiederholt die Viertelstundenreihe jeden Stundenpreis viermal** (Woche 29.09.2025: bis 30.09. stündlich, ab 01.10. echte Viertelstunden). Eine negative Stunde zählt damit als vier Viertelstunden.
- Der 25.10.2026 stimmt in allen 100 Viertelstunden mit dem EPEX-Spot-Fixture überein.
- Lizenz: Marktdaten CC BY 4.0, Quellenangabe „Bundesnetzagentur | SMARD.de“ mit Lizenzlink ([Datennutzung](https://www.smard.de/en/datennutzung)). Die `chart_data`-Endpunkte sind **nicht als API dokumentiert** – Risiko: Format oder Pfade können sich ändern.
- Fixtures: `tests/fixtures/smard_*.json`, Herkunft in `tests/fixtures/_index.json`.

### Einspeisezähler

- Fronius Smart Meter TS 65A-3 (Plattform `fronius`): Wh, `total_increasing`, ganze Wh. Neuer Zustand nur bei Wertänderung – bei wenig Einspeisung vergehen Minuten zwischen zwei Werten. Ein Delta kann also über eine Viertelstundengrenze reichen und muss anteilig verteilt werden.
- Riemann-Integral (z. B. SolarNet): kWh, `state_class: total`. Beide Klassen und beide Einheiten (Wh, kWh, ggf. MWh) unterstützen.

## 4. Entscheidungen

- Helfer-Integration ohne Cloud; ein Config-Entry je Anlage und Zähler (die Testanlage läuft mit zwei Einträgen: Smart Meter und SolarNet, letzterer für den 1:1-Vergleich mit dem Eigenbau).
- Preis einer Viertelstunde immer aus der Prognose (`data`), nie aus dem Live-Zustand im Moment der Buchung.
- **Buchung sofort und anteilig** (`ledger.py`): Jedes Zählerdelta wird zeitlinear auf die berührten Viertelstunden verteilt und jedes Teilstück sofort mit dem Preis seiner Viertelstunde gebucht. Keine Wartezeit an der Grenze; spätere Energie für eine Viertelstunde wird mit deren Preis nachgebucht.
- **Preis fehlt:** Teilstück bis zu 24 h zurückhalten (Preis aus Prognose oder Zustandsverlauf nachholen), danach als vergütet buchen und in der Diagnose zählen.
- **Zähler:** Rücksprung = Reset (neue Basis, nichts buchen); Sprung über 1,5 × Anlagenleistung × Zeit (+ 2 Wh Rundung) = unplausibel (neue Basis, nichts buchen, zählen).
- **Negative Viertelstunden werden gespeichert, nicht Zählstände** (`quarters.py`): Zeitpunkt und Preis jeder negativen Viertelstunde seit Inbetriebnahme plus „bekannt von–bis“. Die Zahl ohne Vergütung entsteht bei jeder Abfrage aus der aktuellen Regel – ein Regelwechsel braucht keinen neuen Abruf. Ändert sich das Inbetriebnahmedatum, wird die SMARD-Nachzählung für den neuen Zeitraum wiederholt.
- **Bericht** (`report.py`, Aktion `einspeisewacht.report`): Stundenwerte der Langzeitstatistik des Zählers (`change`, kWh) je Stunde gleichmäßig auf vier Viertelstunden verteilt – exakt, wenn alle vier gleich ausgehen, sonst Näherung. Unbekannte Preise zählen als vergütet und werden als Lücke ausgewiesen (Entscheidung 2026-10-26).
- **SMARD-Abruf (Opt-in):** einmal je Regel, im Hintergrund nach dem Setup, je Woche eine Anfrage mit 0,5 s Pause. Fehler → Hinweis unter *Reparaturen*, neuer Versuch beim nächsten Start.
- Kalender zeigt negative Preisfenster aus der gespeicherten Preistabelle (~15 Tage zurück, Prognose voraus); Termintexte deutsch/englisch nach Instanzsprache (Kalendertermine haben keine Übersetzungsschlüssel).
- Freiwilliger Wechsel (§ 100 Abs. 47, +0,6 ct) **vorerst nicht** anbieten – erst nach EU-Genehmigung bzw. EEG 2027 (§ 102).
- **Altregeln (Stunden-Regime 2016–2025) werden nicht umgesetzt** (Entscheidung 2026-10-26): Feste Einspeisevergütung gibt es nur bis 100 kW (§ 21 Abs. 1 Nr. 1 EEG: „Strom aus Anlagen mit einer installierten Leistung von bis zu 100 Kilowatt, deren anzulegender Wert gesetzlich bestimmt worden ist“); die Altregeln greifen erst ab 400/500 kW, also nur in der Direktvermarktung, wo die Marktprämie entfällt. Sie bleiben als „nicht unterstützt“ erkannt. Über 100 kW zeigt die Einrichtung einen Hinweis (Erlöse nur grober Anhaltspunkt).
- Greift eine Regel rechtlich noch nicht, bleibt „unvergütet“ 0; ein Schattenwert zeigt, was bei greifender Regel entgangen wäre. Manuelle Übersteuerung im Config Flow.
- Zeiträume (Tag/Monat/Jahr) über die Langzeitstatistik, nicht über eigene Sensoren.

## 5. Arbeitsweise

- GitHub: Organisation `einspeisewacht`, Repo `integration` (öffentlich seit 2026-10-26, damit die HA-Tests in CI laufen und HACS installieren kann). Brand-Bilder seit 2026-10-26 (`docs/BRAND.md`).
- **Releases, auch Betas, als reguläre GitHub-Releases** (nicht „Pre-release“): Ohne reguläres Release nimmt HACS den letzten Commit und sucht wegen `zip_release` eine ZIP unter `releases/download/<commit>/` – 404 (erlebt mit 0.1.0b2, 2026-10-26).

### GitHub-Einstellungen (Stand 2026-10-26, wie Eilwacht)

- **Organisation:** Zwei-Faktor-Pflicht für alle Mitglieder; Profilbild, Beschreibung und Website gesetzt. Actions: alle erlaubt (Einschränkung im Repo), Token standardmäßig nur lesend, Freigabe für Erst-Mitwirkende, Actions dürfen keine Pull-Requests erstellen. „Nur sichere 2FA-Methoden“ ist nicht gesetzt (würde SMS-2FA aussperren).
- **Repo:** Rulesets „main schützen“ (kein Löschen, kein Force-Push, CI `test`/`hassfest`/`compat` muss grün sein) und „Release-Tags schützen“ (`v*` unveränderlich); Secret Scanning mit Push-Schutz; Dependabot-Alerts und -Sicherheitsupdates; vertrauliches Melden von Sicherheitslücken (SECURITY.md); Actions nur GitHub-eigene plus `astral-sh/setup-uv@*`, `home-assistant/actions/*`, `hacs/action@*` – neue Actions vorher dort freigeben; Branches nach Merge löschen; kein Wiki, keine Projekte; Social Preview gesetzt. **„Release immutability“ bewusst aus:** der Release-Workflow hängt die ZIP erst nach der Veröffentlichung an.

## 6. Offene Fragen

- EEG 2027 nach Verabschiedung (voraussichtlich November 2026) prüfen.
- Quelle für historische Viertelstundenpreise zur Nachberechnung (SMARD.de?) und deren Nutzungsbedingungen.

Kein `categories` im Manifest: hassfest lehnt das Feld für Custom-Integrationen ab („not a valid option“, geprüft 2026-10-26 mit `energy` und Unterkategorien).

## 7. Integration Quality Scale (Stand 2026-10-26)

Ziel Bronze. Für Custom-Integrationen vergibt Home Assistant keine Stufe; die Liste dient als Selbstprüfung.

| Bronze-Regel | Stand |
|---|---|
| action-setup | ✅ Aktion `report` in `async_setup` (`services.py`) |
| appropriate-polling | ➖ kein Polling – reagiert auf Zustandsänderungen und Viertelstundentakt |
| brands | ✅ `custom_components/einspeisewacht/brand/` |
| common-modules | ✅ `entity.py`, `runtime.py` |
| config-flow-test-coverage | ✅ `tests/ha/test_config_flow.py` (alle Schritte, Fehler, Abbruch, Neu konfigurieren) |
| config-flow | ✅ mit `data_description` |
| dependency-transparency | ✅ keine `requirements` |
| docs-actions | ✅ README „Bericht für einen Zeitraum“ |
| docs-high-level-description | ✅ README |
| docs-installation-instructions | ✅ README |
| docs-removal-instructions | ✅ README „Entfernen“ |
| entity-event-setup | ✅ Abo in `async_added_to_hass`, Abmeldung über `async_on_remove` |
| entity-unique-id | ✅ `<entry_id>_<key>` |
| has-entity-name | ✅ |
| runtime-data | ✅ `entry.runtime_data` |
| test-before-configure | ✅ Einrichtung prüft Zähler (Einheit, `state_class`) und Preissensor |
| test-before-setup | ➖ bewusst nicht: Zähler und Preissensor stammen aus anderen Integrationen und sind beim Start oft noch nicht da; Einspeisewacht wartet auf sie, statt das Setup scheitern zu lassen |
| unique-config-entry | ✅ `unique_id` = Zähler-Entität |

Darüber hinaus erfüllt (Silber/Gold): `action-exceptions`, `config-entry-unloading`, `diagnostics`, `entity-translations`, `exception-translations`, `icon-translations` (Aktion), `reconfiguration-flow`, `repair-issues`, `entity-category`, `entity-device-class`.

