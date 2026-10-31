// Birnleitner: Start-URL https://www.birnleitner-immobilien.at/properties  (Single-Page-App, Seitenknöpfe klicken)
await WR.sleep(3000);
const grab = () => [...document.querySelectorAll('a[href*="/properties/"]')].map(a => ({ h: a.href.split('#')[0], t: WR.clean((a.closest('article,li,div') || a).innerText) }));
const sig = () => grab().map(x => x.h).join('|');
const all = new Map(); grab().forEach(x => all.set(x.h, x));
const btns = () => [...document.querySelectorAll('button,a')].filter(b => /^\d+$/.test(b.innerText.trim()));
const n = Math.max(1, ...btns().map(b => +b.innerText.trim()));
let pagesRead = 1;
for (let p = 2; p <= n; p++) {
  const b = btns().find(b => b.innerText.trim() === String(p)); if (!b) break;
  const before = sig(); b.click();
  for (let t = 0; t < 24 && sig() === before; t++) await WR.sleep(500);   // bis zu 12 s warten, bis die neue Seite da ist
  if (sig() === before) break;
  // Seite rendert nachträglich weiter: warten, bis die Kartenzahl 1,5 s lang gleich bleibt (mind. 3 s)
  let last = -1, stable = 0;
  for (let t = 0; t < 30 && (stable < 3 || t < 6); t++) { await WR.sleep(500); const c = grab().length; stable = c === last ? stable + 1 : 0; last = c; }
  grab().forEach(x => all.set(x.h, x)); pagesRead++;
}
const total = +((document.body.innerText.match(/(\d+)\s+(Properties|Immobilien)/i) || [])[1] || 0);
const rows = [...all.values()].filter(x => /\b(RENT|MIETE)\b/i.test(x.t) && /\bWIEN\b/i.test(x.t) && /(FLAT|WOHNUNG|APARTMENT)/i.test(x.t))
  .map(x => ({ source_id: (x.t.match(/\bID\s*(\d+)/) || [])[1] || x.h, url: x.h, price: WR.num((x.t.match(/€\s*([\d.,]+)/) || [])[1]),
    area: WR.num((x.t.match(/(?:size|Fläche|Wohnfläche):?\s*([\d.,]+)/i) || [])[1]), rooms: WR.num((x.t.match(/(?:Rooms|Zimmer):?\s*([\d.,]+)/i) || [])[1]),
    district: (x.t.match(/(\d{1,2})\.\s*BEZIRK/i) || [])[1] || null, zip: null, title: x.t.slice(0, 160) }));
window.__WR_RESULT = ({ complete: pagesRead === n && (!total || all.size >= total), cards: all.size, total, rows });
