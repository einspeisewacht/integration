# Einspeisewacht – Marke & Bilddateien

## Idee

Vier Viertelstunden als Balken auf der Null-Linie; einer fällt darunter, und das Wachlicht mit Halo markiert ihn: Jede Viertelstunde wird einzeln bewertet, und die negativen fallen auf. Kachel, Schutzzone, Amber-Wachlicht, Off-White und Schrift sind dieselben wie bei Streckenwacht und Eilwacht – so bleiben die Integrationen als Geschwister erkennbar. Die Kachelfarbe ist **RAL 6024 Verkehrsgrün**.

**Slogan:** „Jede Viertelstunde im Blick.“

## Farben

| Rolle | Hex | Hinweis |
| --- | --- | --- |
| Kachel, Wortmarke | `#008351` | RAL 6024 Verkehrsgrün |
| Wachlicht | `#F5A623` | Amber, wie bei Streckenwacht und Eilwacht |
| Balken, Null-Linie | `#FBF7EE` | warmes Off-White |
| Heller Hintergrund | `#FAF7F2` | README-Kopf, Social Preview |
| Dunkler Hintergrund | `#14181D` | README-Kopf (Dark Mode) |
| Tagline hell / dunkel | `#6B6357` / `#B9B2A6` | |

Halo: Amber mit 35 % Deckkraft.

## Schrift

**Space Grotesk** (Google Fonts, SIL Open Font License), Bold 700 für die Wortmarke, Medium 500 für Tagline und Zusatzzeilen. In allen SVGs ist der Text in Pfade umgewandelt.

## Dateien

| Ort | Inhalt |
| --- | --- |
| `custom_components/einspeisewacht/brand/` | `icon(@2x)`, `dark_icon(@2x)`, `logo(@2x)`, `dark_logo(@2x)` – lädt Home Assistant ab 2026.3 aus der Integration |
| `assets/github/` | README-Kopf hell/dunkel (960×220, @2x), Social Preview 1280×640, Profilbild der Organisation 500/1024 |
| `assets/brand/svg/` | Vektor-Master: Icon, Mini-Icon, vollflächiges Icon, Motiv, Logo, README-Kopf, Social Preview |
| `assets/brand/png/` | Icon 16–2048 px, Motiv ohne Kachel, Logo hell/dunkel |
| `assets/brand/favicon/` | `favicon.ico` (16/32/48), `favicon.svg`, PNG, Apple-Touch- und Android-Icons |

Profilbild der Organisation und Social Preview lassen sich nicht per API setzen: von Hand hochladen (Organisation → Settings → Profile; Repo → Settings → General → Social preview).

## Regeln

- **≤ 32 px immer die Mini-Variante**: drei breitere Balken, größeres Wachlicht, keine Null-Linie, kein Halo.
- Motiv ohne Kachel: auf hellem Grund Balken in Verkehrsgrün (`mark-on-light`), auf dunklem in Off-White (`mark-on-dark`).
- Farben nicht verändern, Motiv nicht verzerren, keine Schatten oder Verläufe.
- Um Logo und Icon mindestens ¼ der Kachelbreite frei lassen.

## Neu erzeugen

```bash
cd tools/brand
npm install
node build.mjs
```

Das Skript (von Eilwacht übernommen) schreibt direkt an die Plätze oben; vorher werden diese Ordner geleert. Farben, Name, Slogan und Unterzeile stehen als Konstanten oben in `build.mjs`.

## Entstehung

Drei Motive verglichen (für Eingeladene: `https://claude.ai/artifact/3iMPSVJY1dnDr16pZHT5eL`): Preisdelle (Kurve unter der Null-Linie), Paneel und Sonne, Viertelstunden. Gewählt am 2026-10-26: Viertelstunden in Verkehrsgrün – erklärt das Prinzip der Integration. Verworfene Farben: Smaragdgrün RAL 6001, Wasserblau RAL 5021, Kieferngrün RAL 6028.
