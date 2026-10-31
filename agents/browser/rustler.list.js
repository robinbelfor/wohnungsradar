// Rustler: Start-URL https://rustler.eu/immobilien/  (GET-Filter Wohnung + Miete + Wien)
// Stand 31.10.2026: Die Liste zeigt höchstens 150 Objekte des Gesamtbestands; neuere Inserate fehlen darin,
// obwohl ihre Detailseiten erreichbar sind. Deshalb complete=false, solange die ungefilterte Liste gekürzt ist.
const base = '/immobilien/?' + new URLSearchParams([['objektart[]', 'wohnung'], ['vermarktungsart[]', 'miete'], ['bundesland[]', 'Wien']]);
const out = new Map();
const r = await WR.getDoc(base);
r.doc.querySelectorAll('a[href*="/immobilien-details/"]').forEach(a => {
  const h = WR.abs(a.getAttribute('href'), r.url); const id = (h.match(/immobilien-details\/(\d+)/) || [])[1];
  if (id && !out.has(id)) { const t = WR.cardText(a); out.set(id, { source_id: id, url: h,
    zip: (t.match(/PLZ\s*(\d{4})/) || t.match(/\b(1(?:0[1-9]|1\d|2[0-3])0)\s*Wien/) || [])[1] || null,
    price: WR.num((t.match(/([\d.,]+)\s*€/) || t.match(/€\s*([\d.,]+)/) || [])[1]), area: WR.num((t.match(/([\d.,]+)\s*m²/) || [])[1]), title: t.slice(0, 160) }); }
});
const all = await WR.getDoc('/immobilien/');
const shown = new Set([...all.html.matchAll(/immobilien-details\/(\d+)/g)].map(m => m[1])).size;
window.__WR_RESULT = ({ rows: [...out.values()], complete: shown < 150, note: 'ungefilterte Liste zeigt ' + shown + ' Objekte' });
