# Einspeisewacht – Projektkontext für Claude

Home-Assistant-Custom-Integration (HACS), Domain `einspeisewacht`. Berechnet für PV-Anlagen mit fester Einspeisevergütung, wie viel Einspeisung wegen negativer Day-Ahead-Preise unvergütet bleibt (§ 51 EEG), den Erlös, den entgangenen Erlös und die Nachholung (§ 51a EEG). Schwesterprojekt von Streckenwacht (`../streckenwacht`) und Eilwacht (`../eilwacht`) – deren Muster übernehmen, wo es passt.

## Dokumentation

- **`docs/ENTWICKLUNG.md`** – Umfang, Rechtsregeln mit Quellen, verifizierte Eigenheiten der Datenquellen, Entscheidungen, offene Fragen. Vor größeren Arbeiten lesen.
- **`CHANGELOG.md`** – Projektstand und Versionsgeschichte. Hier stehen keine Statusberichte.
- Konzept (Claude Docs): https://claude.ai/artifact/DLtTLdGpmePqYRZ1BT1GB7 – Stand 2026-10-22, bei Widersprüchen gilt `docs/ENTWICKLUNG.md`.

## Verbindliche Entscheidungen

- **Helfer-Integration:** liest nur vorhandene Entitäten (Einspeisezähler, Preissensor). Keine Cloud, keine HTTP-Abrufe, keine `requirements`.
- Nur UI-Config-Flow, kein YAML. Ein Config-Entry je Anlage und Zähler.
- **Buchungskern ohne HA-Importe** und wiederverwendbar für einen späteren Tarifvergleich (Bezug fest vs. dynamisch): Viertelstunden-Delta des Zählers × Preis dieser Viertelstunde, dauerhaft gespeichert. Einspeisung und Bezug unterscheiden sich nur in der Bewertungsregel.
- **Rechtsregeln als austauschbare Bausteine** je Inbetriebnahme-Zeitraum, jede mit Paragraphen-Verweis im Code. „Negativ“ heißt `< 0`; exakt 0 ist vergütet.
- Intern UTC, Raster 15 Minuten (Umstellungstage: 92 bzw. 100 Viertelstunden).
- Greift eine Regel rechtlich noch nicht (z. B. kein iMSys), bleibt „unvergütet“ bei 0; ein Schattenwert zeigt, was entgangen wäre.
- Lizenz MIT. Repo: `github.com/einspeisewacht/integration` (öffentlich seit 2026-10-26). `codeowners`: `@n42net`.

## Arbeitsregeln

1. **Formate nie raten.** Die Dateien in `tests/fixtures/` sind die Wahrheit über Formate der Preissensoren. Neue Preisquellen erst mit echtem Fixture.
2. **Rechtsregeln nie aus dem Gedächtnis.** Jede Regel mit Fundstelle (§, Absatz, Satz) aus dem Gesetzestext in `docs/ENTWICKLUNG.md` belegen; Abweichungen von Sekundärquellen dort vermerken.
3. **Keine personenbezogenen Daten ins Repo:** keine Zählerstände, Verläufe oder Anlagendaten des Nutzers. Preis-Fixtures (Marktdaten, SMARD.de, CC BY 4.0) sind erlaubt; Rohdaten nur in `raw/`.
4. Entwickelt wird gegen eine produktive Home-Assistant-Instanz. Logik (Buchung, Regeln, Preisquellen, Nachholung) erst als reines Python ohne HA-Importe testen. Ein Fehler (Preis fehlt, Zähler unavailable) darf nie die Integration oder HA blockieren und nie still falsch buchen.
5. Code, Kommentare, Entity-IDs auf Englisch; UI-Texte über `strings.json` + `translations/de.json` und `en.json`. Doku auf Deutsch.
6. Tests gegen Fixtures. HA-Tests (`tests/ha/`, `pytest-homeassistant-custom-component`) nur in GitHub Actions.
7. **Branches:** Entwickelt wird auf `dev`; `main` erhält nur freigegebene Stände (Versions-Bump in `manifest.json`, `const.py` und `pyproject.toml` + GitHub-Release). Kein Force-Push, Tags `v*` sind unveränderlich.
8. **Werkzeuge:** `uv run pytest`, `uv run ruff check .`, `uv run ruff format .`. `homeassistant` (dev) und `pytest-homeassistant-custom-component` (ha-tests) immer gemeinsam anheben. Rechnerspezifisches und die Testanlage stehen in `CLAUDE.local.md`.
