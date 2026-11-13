# Changelog

## Unveröffentlicht

### Neu

- **Blueprint „Hinweis am Vortag“.** Schickt dir einmal am Tag zur gewählten Uhrzeit (vorgegeben 18 Uhr) eine Nachricht aufs Handy mit allen Zeitfenstern ohne Vergütung von morgen, etwa „Einspeisewacht · Dach: Negative Strompreise morgen“ und „11:00–14:30 und 15:00–15:45 Uhr ohne Vergütung.“ – und keine, wenn es morgen keine gibt. Er fragt nur nach dem Kalender „Negative Preise“, dem Handy und der Uhrzeit; die Nachricht gibt es auf Deutsch oder Englisch, und unter „Weitere Aktionen“ geht sie auch an Telegram oder andere Dienste. Der Import-Knopf steht im README. Er ersetzt das bisherige YAML-Beispiel, das sich zwölf Stunden vor jedem Zeitfenster einzeln meldete, bei Mittagsfenstern also mitten in der Nacht, frühe Fenster oft verpasste und nur mit deutscher Oberfläche funktionierte.

### Behoben

- **Hinweis „Vorbelegt aus Tarifwacht“ stimmt jetzt.** Lieferte Tarifwacht beim Einrichten nur eines der beiden Felder und kam das andere aus dem Energie-Dashboard oder von EPEX Spot, nannte der Hinweis Tarifwacht für beide. Jetzt steht da, woher welches Feld kommt, etwa „Day-Ahead-Preis aus Tarifwacht „Haus“ vorbelegt, Einspeisezähler aus dem Energie-Dashboard – bitte prüfen.“

### Geändert

- **Blueprint „Bei negativem Preis umschalten“ zweisprachig.** Name, Beschreibung und Felder stehen jetzt auf Deutsch und Englisch. Bestehende Automationen laufen unverändert; die neuen Texte gibt es nach einem erneuten Import des Blueprints.

## 0.2.3 – 2026-11-11

### Neu

- **Zähler und Preissensor auch ohne Tarifwacht vorgeschlagen.** Beim Einrichten steht im Feld „Einspeisezähler“ die Netzeinspeisung aus dem Energie-Dashboard, sofern sie noch keine Anlage liest, und im Feld „Day-Ahead-Preis“ der Marktpreis von EPEX Spot (nie dessen Gesamtpreis). Was Tarifwacht vorschlägt, geht weiter vor. Jeder Vorschlag lässt sich ändern.

### Geändert

- **Klare Meldung bei einem nicht verfügbaren Preissensor.** Läuft die Integration des Preissensors gerade nicht (etwa EPEX Spot), meldete das Formular „Kein Preis gefunden …“. Jetzt heißt es: „Der Preissensor ist gerade nicht verfügbar. Läuft die Integration, die ihn liefert (z. B. EPEX Spot)?“

## 0.2.2 – 2026-11-10

### Behoben

- **Einspeisung nach einem Neustart verloren.** Nach einem Neustart von Home Assistant schreibt die Integration des Zählers oft ihren alten Stand mit neuer Uhrzeit. Kam der echte Stand Sekunden danach, rechnete Einspeisewacht die Zunahme auf diese Sekunden, hielt sie für mehr, als die Anlage leisten kann, und buchte sie als Sprung nicht. Jetzt zählt die Plausibilitätsgrenze ab der letzten Änderung des Zählerstands; ein echter Zählerwechsel gilt weiter als Sprung.

## 0.2.1 – 2026-11-09

- **Karte, Feinschliff nach dem ersten Blick mit echten Daten:** „Vergütung bis“ steht als Datum da („30. April 2046“ statt „2046-04-30“). Lange Werte in den Kacheln brechen zwischen Zahl und Einheit um statt mitten im Wort („1.860 Viertelstun-den“). Ein Monat mit sehr wenig unvergüteter Einspeisung zeigt im Diagramm „<1“ statt „0“.

## 0.2.0 – 2026-11-09

- **Neu: eigene Dashboard-Karte**, ohne Zusatzkarten aus HACS: *Dashboard bearbeiten → Karte hinzufügen* und nach „Einspeisewacht“ suchen. Oben steht, ob die laufende Viertelstunde vergütet wird und wann heute und morgen nicht (sobald die Day-Ahead-Preise da sind). Darunter das Kalenderjahr: entgangener Erlös groß, Erlös und Anteil unvergütet daneben, Viertelstunden ohne Vergütung, Nachholung und „Vergütung bis“. Unten die eingespeiste Energie der letzten zwölf Monate, vergütet und unvergütet gestapelt, darüber der Anteil unvergütet. Greift die Regel noch nicht (ohne iMSys), zeigt die Karte, was bei greifender Regel unvergütet wäre. Offene Reparaturhinweise stehen orange darüber. Jahr und Monate kommen aus der Langzeitstatistik der Summen-Sensoren, also auch für nachgetragene Zeit vor der Einrichtung; die Karte fragt sie einmal beim Öffnen der Seite ab, danach höchstens stündlich. Die Dashboard-Ressource trägt Einspeisewacht selbst ein und mit dem letzten Eintrag wieder aus. Der „Bericht für Fehlermeldung“ nennt, ob die Karte eingetragen ist.
- **Übersicht in „Neu konfigurieren“ mit Überschriften wie in den anderen Wachten:** oben „Eingerichtet“, darunter „Was fehlt“ (ohne Doppelpunkt), nur wenn etwas fehlt. Inhalt unverändert.

## 0.1.9 – 2026-11-08

- **Übersicht oben in „Neu konfigurieren“:** Der erste Schritt zeigt jetzt kurz, was eingerichtet ist – Anlage (kWp, Inbetriebnahme), Vergütungssatz (bei Staffel der Mischsatz mit den Sätzen je Stufe und der Einspeiseart), welche Regel **heute** gilt und seit wann (z. B. „Viertelstunden-Regel seit 01.01.2026 (iMSys eingebaut am …)“ oder „noch keine – ab 01.01.2027“), Einspeisezähler, Preissensor und ob SMARD.de genutzt wird. Darunter steht unter **„Was fehlt“** nur, was etwas kostet, mit der Folge: Zähler nicht gefunden oder in falscher Einheit (es wird nichts gebucht), Preissensor ohne Preis (die Einspeisung zählt nach 24 Stunden als vergütet, mit SMARD.de springt SMARD.de ein), kein iMSys eingetragen, SMARD.de aus bei einer Anlage, die schon vor der Einrichtung lief (die Nachholung zählt dann erst ab der Einrichtung).
- **Einrichtung in drei statt vier Schritten, weniger Felder auf einmal** (9 statt 13 sichtbare Felder): Der Schritt „Vergütung“ fragt nur den Satz; mehrere Sätze nach Leistungsstufe stehen eingeklappt darunter und erscheinen nur bei Anlagen über 10 kWp. Der frühere letzte Schritt „Regel“ ist in „Datenquellen und Regel“ aufgegangen: oben die abgeleitete Regel und der Satz, darunter Zähler, Preis und die Option **„SMARD.de nutzen: frühere Viertelstunden nachzählen, fehlende Preise ersetzen“**; eine abweichende Regel steht eingeklappt unter „Rechnet dein Netzbetreiber anders ab?“. Ein eingeklappter Abschnitt öffnet sich, wenn er benutzt wird oder ein Fehler ihn betrifft. Bestehende Einträge bleiben, wie sie sind; gespeichert wird wie bisher.
- **Neues Attribut `applies_today`** am Sensor „Regel“: ob die Regel heute greift (`false` z. B. vor dem 1. Januar nach dem iMSys-Einbau oder ohne iMSys). Die Attribute des Sensors haben jetzt auch übersetzte Namen.
- **Neu: Schaltfläche „Statistik neu berechnen“** am Gerät der Anlage (unter *Konfiguration*). Korrigierst du den Vergütungssatz (auch über Staffelung, Leistung oder Voll-/Teileinspeisung), zeigen Erlös und entgangener Erlös sofort die neuen Summen, die Langzeitstatistik vergangener Stunden (Statistik-Diagramme, Werte je Tag und Monat, die Dashboard-Karte) behielt aber den alten Satz, auch nachgetragene – den ganzen Unterschied buchte Home Assistant in die Stunde der Änderung. Die Schaltfläche berechnet die Statistik von Erlös, entgangenem Erlös und dem Schattenwert „Entgangener Erlös bei greifender Regel“ von ihrem ersten Wert an mit dem aktuellen Satz neu, exakt aus der Statistik der Energie-Sensoren; die Statistik danach schließt ohne Sprung an. Geschrieben werden nur Zeilen, deren Wert sich ändert (Abweichung über 0,0005 €): Sensoren ohne Änderung – etwa der entgangene Erlös, solange nichts unvergütet ist – bleiben unberührt, ein zweites Drücken schreibt nichts. Das schont die SD-Karte eines Raspberry Pi. Das Ergebnis erscheint als Benachrichtigung (Zeitraum, Satz, Zahl der geschriebenen Zeilen, Änderung der Summe je geändertem Sensor). Nach einer Änderung des Satzes erinnert der Reparaturhinweis **„Statistik mit altem Satz“** daran; er verschwindet nach dem Neuberechnen oder wenn der Satz zurückgeändert wird. Die Aufteilung vergütet/unvergütet nach einer Regeländerung bleibt wie bisher, wie sie gebucht ist.
- **Statistik nachtragen:** neues Feld **„Vorhandene Statistik ersetzen“** (`replace`): berechnet auch die vorhandene Statistik von Erlös und entgangenem Erlös ab dem gewählten Tag neu, wie die Schaltfläche; liegt der Tag vor der Einrichtung, wird die Zeit davor zuerst nachgetragen.
- **Unplausible Stunden werden ausgelassen:** Meldet ein Zähler kurz Wh als kWh, stehen in seiner Langzeitstatistik Sprünge von über 100.000 kWh, und das Zurückfallen danach zählt Home Assistant als neuen Zyklus mit dem ganzen Zählerstand. „Bericht“ und „Statistik nachtragen“ lassen jetzt jede Stunde mit mehr Einspeisung als Anlagenleistung × 1,5 (dieselbe Grenze wie für Ablesungen im laufenden Betrieb, nach einer Pause von Home Assistant entsprechend mehr), jede negative Stunde und das Zurückfallen nach so einem Sprung aus (auch wenn der falsche Wert ein paar Stunden stand) und nennen sie unter `hours_implausible` (Anzahl und die ersten fünf Stunden). Eine sonnige Stunde bleibt drin.

## 0.1.8 – 2026-11-08

- **Zähler und Preis aus Tarifwacht:** Hast du die Schwester [Tarifwacht](https://github.com/tarifwacht/integration) eingerichtet, schlägt der Schritt „Datenquellen“ beim Einrichten den Einspeisezähler aus „PV und Speicher“ und den Börsenpreis vor (aus „PV und Speicher“ oder einem Tarif „Börsenpreis plus Aufschläge“ – nie einen Gesamtpreis mit Aufschlägen). Ein Satz unter der Beschreibung sagt, aus welchem Eintrag sie stammen; ohne passende Werte in Tarifwacht steht dort ein kurzer Tipp. Nur ein Vorschlag, Einspeisewacht hängt danach nicht von Tarifwacht ab. Neu konfigurieren bleibt, wie es ist.
- **Bericht für Fehlermeldung lesbarer:** Einstellungen ohne Python-Schreibweise – `yes`/`no` statt `True`/`False`, `none` statt `None`, Listen ohne Klammern, Zeitpunkte als `2026-11-07 12:39 UTC`. Auch Zählerstand, Zählbeginn und Preise bis … stehen jetzt so (bisher ISO mit Mikrosekunden), die negativen Viertelstunden als `2026: 1860` statt `2026 1860`.

## 0.1.7 – 2026-11-07

- **Neu: Schaltfläche „Bericht für Fehlermeldung“** am Gerät (unter *Diagnose*). Sie zeigt einen kurzen Bericht als Benachrichtigung zum Kopieren in ein Issue: Versionen, Regel und Beginn, Vergütungssatz, Stand von Preisen, Zähler und Buchung, die Zuordnung nach Rolle (Integration, Einheit, Zustandsklasse, Zustand; beim Zähler ohne Zählerstand), die Einstellungen (Inbetriebnahme und Smart-Meter-Datum nur mit Monat), unbekannte Sensoren mit Grund und offene Reparaturhinweise – ohne Entity-IDs, Anlagennamen und Bereiche. Viele wollen die Diagnose-Datei nicht öffentlich teilen, weil Home Assistant ihr unter anderem die Liste aller installierten Integrationen voranstellt. Die README erklärt jetzt unter „Fehler melden“, was in der Diagnose-Datei steht und welche Teile man vor dem Teilen löschen darf; die Issue-Vorlage fragt nach dem Bericht.

## 0.1.6 – 2026-11-05

- **Demo zum Ausprobieren ohne Installation:** [einspeisewacht.github.io/integration](https://einspeisewacht.github.io/integration/) zeigt Dashboard-Karte, Tageskurve, Kalender „Negative Preise“, den Hinweis am Vortag, das Gerät und den Bericht – für eine Anlage mit und eine ohne Smart-Meter-Gateway, an einem sonnigen Maisonntag und einem grauen Januartag. Anlagen, Erträge und Preise sind erfunden und so gekennzeichnet; gebucht werden sie vom Code der Integration.
- **Eigene Sensoren sind als Quelle gesperrt:** Einrichten und „Neu konfigurieren“ lehnen jetzt einen Sensor von Einspeisewacht selbst als Einspeisezähler oder Preissensor ab. Bisher ging das durch – die eigenen Energie-Summen bestehen die Prüfung des Zählers, jeder Zahlenwert die des Preissensors –, und der Eintrag hätte seine eigenen Ergebnisse oder die einer anderen Anlage gelesen. Anlass war eine Rückmeldung aus der Schwester Wärmewacht, wo ein Nutzer genau das getan hatte.
- **Bestehende Einträge mit eigenem Sensor als Quelle** lesen ihn nicht mehr und zeigen unter *Reparaturen* den Hinweis **„Sensor von Einspeisewacht als Quelle“** mit den betroffenen Sensoren, bis unter „Neu konfigurieren“ der echte Zähler bzw. Preissensor gewählt ist. Bis dahin bucht ein solcher Eintrag nichts (Zähler) bzw. hat keine Preise (Preissensor): Die Einspeisung gilt dann wie bei einem ausgefallenen Preissensor nach 24 Stunden als vergütet, mit der SMARD-Option rechnet Einspeisewacht mit den Preisen von SMARD.de. Vorher hätte ein eigener Geld- oder Zählsensor als Preis nie einen negativen Preis geliefert – alles galt als vergütet, ohne Hinweis. Die Aktionen „Bericht“ und „Statistik nachtragen“ lehnen einen solchen Zähler ab. Schon Gebuchtes bleibt.
- Kategorien im Manifest für die neue Integrationsübersicht von Home Assistant 2026.11.
- Intern: `tools/make_demo.py` erzeugt die Daten der Demo, der Workflow „Demo“ veröffentlicht sie über GitHub Pages.

## 0.1.5 – 2026-11-02

- **Fehler behoben:** Lief beim Neuladen eines Eintrags (z. B. nach „Neu konfigurieren“) gerade ein Abruf von SMARD.de, konnte er danach noch fertig werden und Sekunden später einen alten Stand über die gespeicherten Daten des neu geladenen Eintrags schreiben. Abrufe im Hintergrund werden jetzt beim Entladen abgebrochen und abgewartet, bevor gespeichert wird.

## 0.1.4 – 2026-10-30

- **Umbenannte Entitäten:** Benennt man Einspeisezähler oder Preissensor in Home Assistant um (neue Entity-ID), zieht Einspeisewacht das jetzt selbst nach – Eintrag, eindeutige ID und gespeicherter Zählerstand. Bisher buchte Einspeisewacht nach dem Umbenennen des Zählers still nichts mehr; nach dem Umbenennen des Preissensors kam nach einer Stunde der Hinweis „Kein Preis“.
- Neuer Hinweis unter *Reparaturen*: **„Einspeisezähler fehlt“**, wenn die Zähler-Entität länger als 10 Minuten nicht existiert (z. B. gelöscht). Er verschwindet, sobald der Zähler wieder da ist.
- **Fehler behoben:** Ein in der Neukonfiguration korrigierter Vergütungssatz (oder eine geänderte Leistung bei gestaffelter Vergütung) galt nur für neue Buchungen; Erlös und entgangener Erlös blieben für die Zeit davor beim alten Satz. Jetzt rechnet Einspeisewacht sie beim Start aus den gebuchten kWh neu – der Satz gilt ab der Einrichtung. In der Langzeitstatistik erscheint die Korrektur in der Stunde der Änderung – wer den Satz schon unter 0.1.3 oder früher korrigiert hat, sieht den Sprung in der Stunde des Updates.
- Eine geänderte **Regel** (Inbetriebnahme, Leistung, Smart-Meter-Datum, Übersteuerung) bucht die kWh-Summen für die Zeit davor bewusst nicht um: Eine sinkende Summe hielte Home Assistant für einen Zählerwechsel. Betrifft die Änderung schon gebuchte negative Viertelstunden, erscheint jetzt ein Hinweis unter *Reparaturen* („Summen teils nach alter Regel“, mit Datum der Änderung und Zahl der betroffenen Viertelstunden), dazu eine Warnung im Protokoll und `rule_change` in der Diagnose; die Werte nach neuer Regel liefert der Bericht. Wird die Regel zurückgeändert, verschwindet der Hinweis wieder. README: neuer Abschnitt, was eine Änderung für die Zeit davor bedeutet.
- **Fehler behoben:** War Home Assistant länger als 14 Tage aus, galt die übersprungene Zeit als bekannt und ohne negative Preise. Jetzt führt der Bericht sie als Lücke ohne Preis (`gaps`).
- **Fehler behoben:** Nach einem Zählertausch in der Neukonfiguration wurde der erste Wert des neuen Zählers gegen den letzten Stand des alten gerechnet; lag er knapp darüber, entstand gebuchte Einspeisung, die es nicht gab. Jetzt beginnt der neue Zähler mit eigenem Ausgangswert.
- Weniger Schreiblast nach längerem Preisausfall: Viertelstunden ohne Preis stehen im gespeicherten Stand jetzt als Zeitbereiche statt einzeln (ein Tag ohne Preis war bisher 96 Einträge, die alle 10 Minuten mitgeschrieben wurden). Ältere gespeicherte Stände werden beim Start übernommen.
- Der Hinweis „Summen teils nach alter Regel“ zählt nur Viertelstunden, in denen die Sonne über dem Horizont steht: Nachts gibt es keine Einspeisung, beide Regeln haben dort dasselbe gebucht.
- Nach einer längeren Pause hielt die Buchung nachts Viertelstunden mit 0 kWh 24 Stunden lang zurück und schrieb sie in den gespeicherten Stand; sie entfallen jetzt.
- Wird ein Zähler umbenannt, während „Neu konfigurieren“ offen ist, stellt das Abschließen nicht mehr die alte ID her.
- Diagnose: `rule_change` (Abschnitt `ledger`) und `gaps` (Abschnitt `quarters`).
- **Zurück auf 0.1.3 oder älter:** Diese Versionen kennen die neuen Teile des gespeicherten Stands nicht und verwerfen sie beim nächsten Speichern – Viertelstunden ohne Preis, Lücken (`gaps`) und die gebuchte Regel samt Verlauf. Die Summen bleiben erhalten.

## 0.1.3 – 2026-10-29

- **Preise von SMARD.de, wenn der Preissensor ausfällt** (nur mit der SMARD-Option): Liefert der Preissensor für eine Viertelstunde länger als eine Stunde keinen Preis, holt Einspeisewacht die Day-Ahead-Preise von SMARD.de – höchstens einmal je Stunde und nur für Viertelstunden, die der Sensor offen gelassen hat. So bleiben Buchung und Nachholung auch bei einem tagelangen Ausfall der Preis-Integration richtig. Bisher galt die Einspeisung nach 24 Stunden ohne Preis als vergütet, und negative Viertelstunden fehlten in der Nachholung.
- Der Hinweis „Kein Preis für die laufende Viertelstunde“ richtet sich nach dem Preissensor selbst und bleibt, solange er ausfällt – auch wenn SMARD.de die Lücke füllt.
- **„Statistik nachtragen“** ergänzt jetzt auch den Teil der Einrichtungsstunde vor der Einrichtung, der bisher in der Statistik fehlte.
- Diagnose: Abschnitt `smard_fill` mit der Zahl der von SMARD.de ergänzten Viertelstunden.

## 0.1.2 – 2026-10-29

- **Fehler behoben:** War Home Assistant länger als einen Tag aus und lieferte der Preissensor beim Start noch keine Daten, buchte Einspeisewacht die zurückgehaltene Energie sofort als vergütet und legte die Viertelstunden als „ohne Preis“ ab – auch wenn die Preise Sekunden später kamen. Jetzt wartet die Buchung nach dem Start auf den ersten Preis.
- **Fehler behoben:** Kam der Preis einer schon als „ohne Preis“ abgelegten Viertelstunde später doch noch (EPEX Spot liefert den Vortag mit), wurde eine negative Viertelstunde nie mehr gezählt und fehlte in der Nachholung. Jetzt wird sie nachgezählt.
- **„Statistik nachtragen“** lehnt einen Beginn nach der Einrichtung des Eintrags ab. Ab da haben die Sensoren eigene Statistik; ein späterer Beginn hätte falsche Zeilen erzeugt.

## 0.1.1 – 2026-10-27

Keine funktionalen Änderungen. HACS bot 0.1.0 nicht als Update an: GitHub sortiert die Beta-Releases 0.1.0b10 und 0.1.0b11 vor 0.1.0, und HACS nimmt das erste. 0.1.1 steht wieder vorn.

## 0.1.0 – 2026-10-27

Erste Version ohne Beta-Zusatz. Gegenüber 0.1.0b11 nur Dokumentation:

- README (deutsch und englisch): Beta-Hinweis ersetzt, Hinweis auf die EEG-Novelle 2027; Dashboard-Karte jetzt auch im englischen README.

## 0.1.0b11 – 2026-10-27

- „Vergütung aktiv“ zeigt „Vergütet“ bzw. „Unvergütet“ statt „Ein“/„Aus“.
- README: fertige Dashboard-Karte (Einspeisung je Tag, Erlös und entgangener Erlös für heute und das Jahr, negative Viertelstunden, Nachholung, Vergütungsende) mit Screenshot.

## 0.1.0b10 – 2026-10-27

- **Keine verwaisten Entitäten mehr:** Sensoren, die eine Anlage nicht mehr braucht – etwa die Schattenwerte, nachdem in der Neukonfiguration ein Smart Meter eingetragen oder das Inbetriebnahmejahr korrigiert wurde, oder sobald die Viertelstundenregel greift –, entfernt die Integration jetzt beim Start selbst aus der Entitätenliste. Bisher blieben sie als „nicht mehr bereitgestellt“ zurück und mussten von Hand gelöscht werden.
- Intern: wöchentlicher Quellen-Check (`tools/source_check.py`, Workflow „Quellen-Check“, montags): lädt Index und die beiden neuesten Wochen von SMARD.de mit dem echten Parser und prüft Format, Aktualität, Viertelstundenraster (auch in Wochen mit Zeitumstellung) und Preisspanne – die Schnittstelle ist nicht offiziell dokumentiert. Bei Problemen öffnet er ein Issue mit Label `quellen-check` und schließt es wieder, sobald alles geht.
- Intern: Entwicklungs- und Testumgebung auf Home Assistant 2026.10.4 angehoben (Testbibliothek 0.13.375), wie bei Streckenwacht.
- Intern: `astral-sh/setup-uv` 10.3.2; Dependabot schlägt Aktualisierungen jetzt für `dev` vor statt für `main`.

## 0.1.0b9 – 2026-10-26

- **Fehler behoben:** Ein Preissensor ohne Prognose-Attribut lieferte nur für die Viertelstunde einen Preis, in der sich sein Wert änderte. Hielt er einen Wert eine Stunde lang, fehlten drei Viertelstunden: negative Stunden wurden zu wenig gezählt, „Vergütung aktiv“ war zeitweise unbekannt, und der Hinweis „Kein Preis“ erschien fälschlich. Jetzt gilt der aktuelle Wert für jede Viertelstunde, bis er sich ändert. EPEX Spot (mit Prognose) war nicht betroffen.
- README mit Screenshots (Geräteseite, Einrichtung, Kalender, Integration) und einer Beispielantwort des Berichts.

## 0.1.0b8 – 2026-10-26

(0.1.0b7 wurde versehentlich auf dem Stand von 0.1.0b6 und ohne ZIP veröffentlicht und zurückgezogen.)

- Eigene Symbole für alle Entitäten (z. B. Uhr mit Minus für Viertelstunden ohne Vergütung, Kalender mit Plus für die Nachholung, Geldschein mit Haken/Kreuz für „Vergütung aktiv“).

## 0.1.0b6 – 2026-10-26

- **Aktion „Statistik nachtragen“** (`einspeisewacht.import_statistics`): füllt die Langzeitstatistik der Summen-Sensoren für die Zeit vor der Einrichtung, ab einem wählbaren Tag – damit Statistik-Karten und Verlauf das ganze Jahr zeigen. Rechnet wie der Bericht, verschiebt die späteren Summen passend und schreibt nur, was noch fehlt. Setzt die SMARD-Option voraus.

## 0.1.0b5 – 2026-10-26

- **Blueprint „Bei negativem Preis umschalten“:** eigene Aktionen, wenn die Vergütung entfällt (Speicher laden, Wallbox, Abregeln), und andere, wenn sie wieder gezahlt wird – mit Import-Knopf im README.
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
