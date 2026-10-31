// BETTERHOMES Detail: IDS = Liste von source_ids (uniqueKey)
const strip = o => { if (Array.isArray(o)) return o.map(strip); if (o && typeof o === 'object') { const n = {}; for (const [k, v] of Object.entries(o)) { if (/Label$|^cta|Disclaimer|wikipedia|schools|shops|publicTransport|similar|translation|priceRating/i.test(k)) continue; if (v === null || v === '' || v === false) continue; n[k] = strip(v); } return n; } return typeof o === 'string' && o.length > 1800 ? o.slice(0, 1800) : o; };
const out = [];
for (const id of IDS) {
  try { const r = await WR.postJSON('/apirequest', { action: 'Object/detail', method: 'POST', data: { id, countryCode: 'AT', languageCode: 'de', referrer: '' } });
    const d = strip(r.responseData || r); if (d.images) d.images = d.images.map(i => i.imageUrl || i).filter(Boolean);
    out.push({ source_id: id, url: 'https://www.betterhomes.at/de/immobilie-suchen/detail/objectId/' + id, data: d }); }
  catch (e) { out.push({ source_id: id, error: String(e) }); }
  await WR.sleep(300);
}
window.__WR_RESULT = out;
