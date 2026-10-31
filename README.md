# Wohnungsradar – Browser-Dienst

Liest die Makler-Websites, die ihre Inserate erst per JavaScript laden (EHL, OTTO, Betterhomes, JP Immobilien,
Birnleitner, Rustler), zweimal täglich in einem unsichtbaren Chromium und legt die Rohdaten in
`inbox/browser/latest.json` im Zweig `engine` ab. Der Cloud-Scan um 6:00 und 12:00 übernimmt sie.

Coolify: Dockerfile-Build aus diesem Zweig, Port 3000 (zeigt den Status als JSON).
Umgebungsvariablen: `GITHUB_TOKEN` (Pflicht), `RUN_TIMES` (Standard `05:25,11:25`), `RUN_ON_START=1` zum Testen.
