# Wohnungsradar – Engine

Zustand und Werkzeuge des Wohnungsradars: Makler-Verzeichnis (`data/brokers.json`), Inserate (`data/listings.json`),
Suchkriterien (`config/`), Handbücher der Agents (`agents/`), Skripte (`tools/`). Ablauf eines Scans:
`agents/cloud-run.md`. Der Browser-Dienst (Zweig `browser-service`) schreibt nach `inbox/browser/latest.json`.
