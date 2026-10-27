# Einspeisewacht – Projektkontext für Claude

Home-Assistant-Custom-Integration (HACS), Domain `einspeisewacht`. Berechnet für PV-Anlagen mit fester Einspeisevergütung, wie viel Einspeisung wegen negativer Day-Ahead-Preise unvergütet bleibt (§ 51 EEG), den Erlös, den entgangenen Erlös und die Nachholung (§ 51a EEG). Schwesterprojekt von Streckenwacht (`../streckenwacht`) und Eilwacht (`../eilwacht`) – deren Muster übernehmen, wo es passt.

## Dokumentation

- **`docs/ENTWICKLUNG.md`** – Umfang, Rechtsregeln mit Quellen, verifizierte Eigenheiten der Datenquellen, Entscheidungen, offene Fragen. Vor größeren Arbeiten lesen.
- **`CHANGELOG.md`** – Versionsgeschichte und was auf `dev` unveröffentlicht liegt (Abschnitt „Unveröffentlicht“). Hier stehen keine Statusberichte.
- **`NOTES.md`** (lokal, nicht im Repo) – Arbeitsstand, offene Punkte, Beobachtungen. Nach jeder Sitzung fortschreiben. Interna (Zahlen, Einschätzungen, Werte der Testanlage) gehören nur dorthin – das Repo ist öffentlich.
- **`docs/BRAND.md`** – Farben, Schrift, Bilddateien, Regenerierung. Brand-Bilder nicht verändern oder neu erzeugen, außer auf ausdrücklichen Wunsch.
- Konzept (Claude Docs): https://claude.ai/artifact/DLtTLdGpmePqYRZ1BT1GB7 – Stand 2026-10-22, bei Widersprüchen gilt `docs/ENTWICKLUNG.md`.

## Verbindliche Entscheidungen

- **Liest vorhandene Entitäten** (Einspeisezähler, Preissensor), keine `requirements`. Erscheint als Integration (`integration_type: service`), nicht als Helfer (Entscheidung 2026-10-26).
- **Einziger HTTP-Abruf: SMARD.de, nur als Opt-in** (Entscheidung 2026-10-26), um negative Viertelstunden vor der Einrichtung für die Nachholung nachzuzählen. User-Agent `Einspeisewacht/<version> (+https://github.com/einspeisewacht/integration)`, Quellenangabe „Bundesnetzagentur | SMARD.de“ (CC BY 4.0). Ein SMARD-Fehler darf nie Setup oder Buchung blockieren. Die Schnittstelle (`/app/chart_data/…`) ist nicht offiziell dokumentiert.
- Nur UI-Config-Flow, kein YAML. Ein Config-Entry je Anlage und Zähler.
- **Buchungskern ohne HA-Importe** und wiederverwendbar für einen späteren Tarifvergleich (Bezug fest vs. dynamisch): Viertelstunden-Delta des Zählers × Preis dieser Viertelstunde, dauerhaft gespeichert. Einspeisung und Bezug unterscheiden sich nur in der Bewertungsregel.
- **Rechtsregeln als austauschbare Bausteine** je Inbetriebnahme-Zeitraum, jede mit Paragraphen-Verweis im Code. „Negativ“ heißt `< 0`; exakt 0 ist vergütet.
- Intern UTC, Raster 15 Minuten (Umstellungstage: 92 bzw. 100 Viertelstunden).
- Greift eine Regel rechtlich noch nicht (z. B. kein iMSys), bleibt „unvergütet“ bei 0; ein Schattenwert zeigt, was entgangen wäre.
- Lizenz MIT. Repo: `github.com/einspeisewacht/integration` (öffentlich seit 2026-10-26). `codeowners`: `@n42net`.

## Arbeitsregeln

1. **Formate nie raten.** Die Dateien in `tests/fixtures/` sind die Wahrheit über Formate der Preissensoren und von SMARD.de (Herkunft in `tests/fixtures/_index.json`). Neue Preisquellen erst mit echtem Fixture.
2. **Rechtsregeln nie aus dem Gedächtnis.** Jede Regel mit Fundstelle (§, Absatz, Satz) aus dem Gesetzestext in `docs/ENTWICKLUNG.md` belegen; Abweichungen von Sekundärquellen dort vermerken.
3. **Keine personenbezogenen Daten ins Repo:** keine Zählerstände, Verläufe oder Anlagendaten des Nutzers. Preis-Fixtures (Marktdaten, SMARD.de, CC BY 4.0) sind erlaubt; Rohdaten nur in `raw/`.
4. Entwickelt wird gegen eine produktive Home-Assistant-Instanz. Logik (Buchung, Regeln, Preisquellen, Nachholung) erst als reines Python ohne HA-Importe testen. Ein Fehler (Preis fehlt, Zähler unavailable) darf nie die Integration oder HA blockieren und nie still falsch buchen.
5. Code, Kommentare, Entity-IDs auf Englisch; UI-Texte über `strings.json` + `translations/de.json` und `en.json`. Doku auf Deutsch.
6. Tests gegen Fixtures. HA-Tests (`tests/ha/`, `pytest-homeassistant-custom-component`) nur in GitHub Actions.
7. **Branches:** Entwickelt wird auf `dev`; `main` erhält nur freigegebene Stände (Ablauf unter „Release“), weil die HACS-Installationen daran hängen. Ein Ruleset erzwingt grüne CI (`test`, `hassfest`, `compat`) für `main`. Kein Force-Push, Tags `v*` sind unveränderlich.
8. **Werkzeuge:** `uv run pytest`, `uv run ruff check .`, `uv run ruff format .`. `homeassistant` (dev) und `pytest-homeassistant-custom-component` (ha-tests) immer gemeinsam anheben. Rechnerspezifisches und die Testanlage stehen in `CLAUDE.local.md`.

## Release

Gleicher Ablauf in allen Schwesterprojekten (Eilwacht, Einspeisewacht, Streckenwacht, Tarifwacht). Neue Erkenntnisse zum Ablauf hier eintragen und für die Schwestern melden.

1. Version in `manifest.json`, `const.py` und `pyproject.toml` anheben, `uv lock`; `tests/test_manifest.py` prüft die Gleichheit. „Unveröffentlicht“ in `CHANGELOG.md` zur Version machen. **Nach Betas `0.x.0bN` nie `0.x.0` veröffentlichen, sondern `0.x.1`:** GitHub listet `0.1.0b11` vor `0.1.0`, HACS nimmt den ersten Eintrag und bietet die Endversion nicht an (erlebt 2026-10-27, behoben mit 0.1.1).
2. `dev` pushen und auf den CI-Lauf **genau dieses Commits** warten (`gh run list --commit <sha>`): Push-CI startet manchmal Minuten verspätet, ein älterer grüner Lauf täuscht.
3. `main` vorspulen mit `git push origin dev:main` – **ohne Branch-Wechsel** im Arbeitsverzeichnis (auf dem Netzlaufwerk hat `git switch` schon Dateien verloren, ein Release entstand so auf altem Stand). Danach prüfen, dass `origin/main` auf dem Versions-Commit steht.
4. `gh release create vX --target main --latest --notes-file …` (Text aus dem Changelog). Ziel `main`, kein Kurz-SHA (gibt 422). Immer ein **reguläres** Release, auch für Betas, nie `--prerelease`: Sonst nimmt HACS den letzten Commit und sucht dort vergeblich die ZIP. Blockiert der Auto-Modus das Veröffentlichen: Befehl nennen, der Inhaber führt ihn aus – nie umgehen.
5. Workflow „Release-ZIP“ prüfen: `einspeisewacht.zip` muss am Release hängen. Der Workflow bricht ab, wenn Tag und `manifest.json` nicht passen; fehlt die ZIP, ihn per Hand mit dem Tag starten. Ohne ZIP scheitern HACS-Installationen.
6. Prüfen, dass HACS die neue Version sieht: `gh api repos/einspeisewacht/integration/releases --jq '.[0].tag_name'` muss das neue Tag sein – HACS nimmt den **ersten** Eintrag dieser Liste, nicht „Latest“. GitHub sortiert sie offenbar nach der Basisversion; innerhalb derselben Basis (`0.1.0b1` … `0.1.0b10`, `0.1.0`) ist die Reihenfolge willkürlich (Tarifwacht 2026-10-27: b10 und 0.1.0 landeten hinter b6, HACS bot keine von beiden an). **Regel:** Nach Vorabversionen die nächste Version mit **höherer Basis** veröffentlichen (`0.1.1` statt `0.1.0` nach `0.1.0b…`), und Vorabnummern zweistellig gar nicht erst erreichen.
7. Bricht eine Sitzung mitten im Release ab: erst den Stand prüfen (`git log origin/dev origin/main`, CI des Commits, `gh release list`), dann weitermachen.

„Unveränderliche Releases“ bleibt in GitHub aus, weil der Workflow die ZIP erst nach dem Veröffentlichen anhängt; die Tags `v*` schützt das Ruleset.

## Fallstricke (dauerhaft)

- **Zeitrechnung nur in UTC**, auch in Tests und Hilfsfunktionen: Schritte in Ortszeit verlieren oder verdoppeln am Umstellungstag Viertelstunden (zweimal passiert: Bericht und Test-Helfer).
- **HA-Tests mit Recorder:** `auto_enable_custom_integrations` im Testmodul überschreiben und `recorder_mock` vor `enable_custom_integrations` anfordern (siehe `tests/ha/test_statistics_import.py`), sonst Fixture-Reihenfolgefehler.
- **Schreiblast:** `Store.async_delay_save` verschiebt den Termin bei jeder Änderung – für häufig geänderte Daten eigene Intervalle (siehe `docs/ENTWICKLUNG.md`, Speichern in zwei Dateien). Schätzungen zur Schreiblast messen, nicht hochrechnen.
- **Screenshots und Forentexte:** keine echten Werte der Testanlage in Repo-Bildern. Forenentwürfe liegen in `raw/forum/`; posten macht der Inhaber selbst.
