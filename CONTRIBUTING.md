# Mitmachen

Danke, dass du Einspeisewacht verbessern willst! Fehler und Ideen bitte als [Issue](https://github.com/einspeisewacht/integration/issues/new/choose). Sicherheitslücken bitte vertraulich melden, siehe [SECURITY.md](SECURITY.md).

## Pull Requests

- Kleine Änderungen (Fehlerbehebungen, Übersetzungen, Doku) gern direkt als Pull Request. Neue Funktionen, Preisquellen oder Umbauten bitte erst in einem Issue besprechen, damit niemand umsonst arbeitet.
- **Basis ist `dev`**, nicht `main`. `main` enthält nur veröffentlichte Stände, an denen die HACS-Installationen hängen.
- Vor dem Pull Request: `uv run pytest`, `uv run ruff check .` und `uv run ruff format .`. Die Home-Assistant-Tests (`tests/ha/`) laufen nur in GitHub Actions, unter Windows nicht. Bei Pull Requests aus Forks startet die CI erst, wenn ich sie freigebe.
- Code, Kommentare und Entity-IDs auf Englisch. UI-Texte stehen in `strings.json` und `translations/de.json` + `en.json`, immer in beiden Sprachen.
- `CHANGELOG.md` und Versionsnummer bitte nicht ändern. Den Eintrag und das Release übernehme ich.

## KI-Assistenten

Beiträge mit Hilfe von KI-Assistenten (z. B. Claude Code) sind willkommen, wenn du die Änderung selbst verstanden und getestet hast. Bitte im Pull Request kurz erwähnen; ein `Co-Authored-By`-Trailer im Commit genügt.

[`CLAUDE.md`](CLAUDE.md) und [`docs/ENTWICKLUNG.md`](docs/ENTWICKLUNG.md) enthalten die Projektregeln, die dein Assistent lesen sollte. Release, Veröffentlichen und alles an `main` mache nur ich.

## Besonderheiten von Einspeisewacht

- **EEG-Regeln nur mit Fundstelle** (§, Absatz, Satz) aus dem Gesetzestext, eingetragen in [`docs/ENTWICKLUNG.md`](docs/ENTWICKLUNG.md), nicht aus dem Gedächtnis oder aus Sekundärquellen.
- **Neue Preisquellen nur mit echtem Fixture** in `tests/fixtures/` (Herkunft in `_index.json`). Formate nie raten.
- **Keine personenbezogenen Daten ins Repo:** keine eigenen Zählerstände, Verläufe oder Anlagendaten, auch nicht als Testwerte. Marktdaten (z. B. SMARD.de) sind erlaubt.
- Änderungen an der Buchung nur mit Tests. Fehlt ein Preis oder ist ein Zähler `unavailable`, darf nie still falsch gebucht werden.

## English

Contributions are welcome. Small fixes, translations and docs can go straight to a pull request; for new features, price sources or larger changes please open an issue first. Target the **`dev`** branch, run `uv run pytest` and `uv run ruff check .` before opening the PR, and keep code and comments in English (UI texts in both German and English). Legal rules need a citation of the law, new price sources a real fixture, and no personal meter data goes into the repo. AI-assisted contributions are fine if you have reviewed and tested them yourself; please mention it in the PR. Issues and pull requests in English are welcome.
