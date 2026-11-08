# Veranstaltungsscanner Steiermark

Findet öffentliche Termine in der Steiermark, taggt sie mit KI und schlägt jeder Rolle passende Termine vor.
Klick-Prototyp von Karim-Fabian Osman. Kein offizielles Produkt von NEOS.

- **Einrichtung:** [SETUP.md](SETUP.md), Schritt für Schritt, ohne Programmierkenntnisse.
- `web/` die App (PWA). `web/index.html` wird aus `src/app.html` gebaut: `python3 tools/build_web.py`.
- `supabase/` Datenbank (`schema.sql`) und Edge Functions (`ask`, `scan-now`, `fetch-link`, `ics`).
- `pipeline/` Suchlauf: `update.py` (Abruf, Prüfung, Zusammenführen), `run.py` (Ablauf, KI, Upload, Mitteilungen).
- `.github/workflows/` Suchlauf nach Zeitplan, App veröffentlichen, Edge Functions einrichten.
- `seed/` letzter Datenstand aus dem Prototyp für den Start.
