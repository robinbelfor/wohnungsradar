# Handbuch: Browser-Agent (Wohnungsradar Wien)

Du liest Makler-Webseiten, die ihre Inserate erst per JavaScript laden, mit dem **Browser der Claude-App**
auf dem Mac des Nutzers. Die Websites sind vom Nutzer dauerhaft freigegeben. Ergebnis: eine Ergebnisdatei
im selben Format wie beim Makler-Agent (siehe unten).

## Werkzeuge
- Browser-Werkzeuge laden: ToolSearch mit `mcp__remote-devices__Claude_Browser__`, max_results 64.
- Pro Makler **eine eigene Registerkarte**: `tabs_create` → `tabId`, dann `navigate(tabId, start_url)`. Alle weiteren
  Aufrufe mit diesem `tabId` (nie ohne `tabId`, sonst triffst du die Registerkarte eines anderen Agents). Am Ende die
  eigene Registerkarte mit `tabs_close` schließen – **nie die letzte offene Registerkarte** (vorher `tabs_context`
  prüfen; ist es die letzte, offen lassen). Nur wenn `tabs_create` fehlt: `preview_start` mit der Start-URL.
- Code im Browser: `javascript_tool` (action `javascript_exec`). Top-level `await` funktioniert, der letzte
  Ausdruck ist das Ergebnis.
- **Hilfsbibliothek:** Lies `browser-lib.min.js` (liegt neben diesem Handbuch) und führe ihren gesamten Text
  einmal pro geladener Seite aus. Danach gibt es `window.WR`. Nach jeder Navigation erneut ausführen.
  Spartipp bei vielen Navigationen auf derselben Website: einmal `window.name = "WRLIB:" + <Bibliothekstext>`
  setzen (als String-Literal übergeben) und nach jeder Navigation nur `(0, eval)(window.name.slice(6))` ausführen.
- **Rezepte:** `browser/<datei>.list.js` (Liste) und ggf. `browser/<datei>.detail.js` liegen im Ordner `browser/`
  neben diesem Handbuch. Ihren Text unverändert ausführen (nach der Bibliothek).
- Verboten: Kontaktformulare, Logins, Newsletter, Suchaufträge. Erlaubt: das Suchformular, das ein Rezept
  verwendet, und das Ablehnen nicht notwendiger Cookies („Ablehnen“, „Nur notwendige“).
- Meldet ein Browser-Werkzeug, dass eine Website nicht freigegeben ist, oder ist der Browser nicht erreichbar:
  diesen Makler mit `ok: false, error: "Browser: <Grund>"` melden und weitermachen. Nicht `request_access` aufrufen.

## Ablauf je Makler
1. Registerkarte öffnen und `start_url` laden (siehe oben), 2–3 s warten (`computer` action `wait`). Cookie-Banner, der die Seite verdeckt:
   mit `find` „Ablehnen“ bzw. „Nur notwendige“ suchen und klicken.
2. Bibliothek ausführen, dann das Listen-Rezept → Array `{source_id, url, zip?, price?, rent_net?, area?, rooms?, title?}`
   oder ein Objekt `{rows: [...], complete: true/false}` (dann `rows` verwenden und `complete` übernehmen).
   Ist das Ergebnis leer, obwohl der Makler laut Auftrag aktive Wohnungen hatte, einmal nach 3 s wiederholen.
3. `seen_ids` = alle source_ids aus der Liste (nur Wien, nur Wohnungen zur Miete – das Rezept filtert vor;
   offensichtliche Nicht-Wohnungen wie Büro, Lager, Garage aussortieren).
4. Neue bzw. geänderte (Preis/Fläche anders als bekannt) Inserate bestimmen. Höchstens `detail_cap` pro Lauf
   (steht im Auftrag), Rest nur in `seen_ids`.
5. Details holen, je nach Modus (steht im Auftrag):
   - **fetch:** in Portionen zu 8 Stück
     `await WR.detailsNormalized(ITEMS, {include: new RegExp(INCLUDE), rawScan: RAW, scope: SCOPE})` – ITEMS ist ein
     JSON-Array `[{source_id, url}]`, INCLUDE/RAW/SCOPE stehen im Auftrag (SCOPE = CSS-Selektor der Galerie, sonst weglassen).
   - **api:** das Detail-Rezept mit `const IDS = [...]` davor ausführen (Portionen zu 8); es liefert die
     Rohdaten der Website-API. Übertrage die Felder selbst ins Schema.
   - **navigate:** für jedes Inserat `navigate(tabId, url)`, 2 s warten, Bibliothek ausführen,
     `WR.normalize(WR.liveDetail({include: new RegExp(INCLUDE), scope: SCOPE}), {source_id: "<id>"})`.
6. Jedes Ergebnis prüfen und fertigstellen:
   - `_deal` muss „Miete“ o. ä. sein (falls vorhanden), PLZ in Wien (1010–1230), sonst verwerfen und aus
     `seen_ids` nehmen.
   - Fehlende Werte aus der Liste ergänzen (Preis = meist Gesamtmiete, Fläche, Zimmer, PLZ).
   - Offensichtliche Fehlzuordnungen korrigieren (z. B. Kaution als Text, „Hauptmiete inkl. USt“ ≠ Netto).
     Liefert die Liste `rent_net`, gilt dieser Wert. Wenn Netto = Brutto, ist Netto unbekannt (`null`).
     Bilder aus „Ähnliche Objekte“/„In der Nähe“, Logos, Siegel und Share-Bilder gehören nicht ins Inserat.
   - `summary`: höchstens 2 Sätze **auf Deutsch, in eigenen Worten** aus `_text` (keine Kopie).
   - `building`: altbau / sanierter_altbau / neubau / erstbezug, wenn aus Titel/Text eindeutig.
   - Felder mit `_` am Anfang entfernen, `broker_name` setzen. Fehlen Bilder oder Preis: `data_quality: "partial"`.
   - Seiten mit Status 404/410 (`gone: true`) → source_id in `gone_ids`.
7. `complete: true`, wenn das Listen-Rezept fehlerfrei lief; sonst `false`.

## Ergebnisdatei (genau eine, Pfad steht im Auftrag)
```json
{"agent": "<batch>", "run_id": "<run_id>", "mode": "browser",
 "brokers": [{"slug": "...", "ok": true, "complete": true, "seen_ids": ["..."], "listings": [{...Schema...}],
              "gone_ids": [], "reserved_ids": [], "error": null, "fetches": 0}]}
```
Schema-Felder wie im Makler-Handbuch (`rent_total`, `rent_net`, `operating_costs`, `vat`, `heating_costs`, `other_costs`,
`deposit`, `deposit_text`, `commission`, `commission_text`, `commission_free`, `area`, `rooms`, `bedrooms`,
`bathrooms`, `toilets`, `floor`, `floors_total`, `outdoor`, `elevator`, `furnished`, `kitchen`, `cellar`, `parking`,
`building`, `year_built`, `condition`, `heating`, `hwb`, `hwb_class`, `fgee`, `fgee_class`, `available_from`,
`available_text`, `term`, `term_years`, `features`, `street`, `house_number`, `zip`, `lat`, `lng`, `contact`,
`summary`, `images`, `floorplans`, `title`, `url`, `source_id`, `status`).
Gültiges JSON prüfen, dann mit Write schreiben. Antworte zum Schluss mit einer Zeile pro Makler:
`slug: ok/fehler, gesehen N, neu N`.
