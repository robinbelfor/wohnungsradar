// EHL: Start-URL https://www.ehl.at/wohnen/immobiliensuche/mietwohnung/object-type/4 (Cookie-Banner: "Ablehnen")
const f = [...document.querySelectorAll('form')].find(f => /realtysearch/.test(f.action));
const fd = new FormData(f);
fd.delete('tx_immo_realtysearch[filter][federalStateId][]'); fd.delete('tx_immo_realtysearch[filter][regionId][]');
fd.append('tx_immo_realtysearch[filter][federalStateId][]', '134');
fd.set('tx_immo_realtysearch[filter][limit]', '100'); fd.set('tx_immo_realtysearch[filter][objectType]', '4');
const first = await WR.getDoc(f.action, { method: 'POST', body: fd });
const docs = [first.doc], seenPages = new Set();
for (const u of WR.links(first.doc, /currentPage%5D=\d+/, first.url)) {
  const p = (u.match(/currentPage%5D=(\d+)/) || [])[1];
  if (!p || p === '1' || seenPages.has(p)) continue; seenPages.add(p);
  docs.push((await WR.getDoc(u)).doc); await WR.sleep(300);
}
const out = {};
for (const d of docs) d.querySelectorAll('a[href*="/objekt/"]').forEach(a => {
  const id = (a.getAttribute('href').match(/\/objekt\/(\d+)/) || [])[1]; if (!id || out[id]) return;
  const t = WR.cardText(a);
  out[id] = { source_id: id, url: 'https://www.ehl.at/objekt/' + id, zip: (t.match(/\b(1\d{2}0)\s+Wien/) || [])[1] || null,
    price: WR.num((t.match(/€\s*([\d.,]+)/) || [])[1]), area: WR.num((t.match(/Fläche\s*([\d.,]+)/) || [])[1]),
    rooms: WR.num((t.match(/Zimmer\s*([\d.,]+)/) || [])[1]), title: t.slice(0, 140) };
});
// neueste zuerst (hoehere ID = neuer), damit detail_cap die frischen Inserate trifft
window.__WR_RESULT = Object.values(out).filter(x => !x.zip || WR.isViennaZip(x.zip)).sort((a, b) => Number(b.source_id) - Number(a.source_id));
