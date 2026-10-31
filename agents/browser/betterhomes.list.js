// BETTERHOMES: Start-URL https://www.betterhomes.at/de/immobilie-suchen/mieten  (eigene API /apirequest)
const a = await WR.postJSON('/apirequest', { action: 'Object/search', method: 'POST', data: { countryCode: 'AT', languageCode: 'de', searchType: 'rent', objectType: 'all', sortOrder: 'newestDesc' } });
window.__WR_RESULT = a.filter(o => WR.isViennaZip(o.zipcode) && /wohnung|dachgeschoss|maisonette|loft|penthouse|apartment|appartment|attika|studio|garconn|erdgeschoss|parterre|etage/i.test(o.objectType || ''))
 .map(o => ({ source_id: o.uniqueKey, url: 'https://www.betterhomes.at/de/immobilie-suchen/detail/objectId/' + o.uniqueKey, zip: o.zipcode,
   price: parseFloat(o.priceGrossFloat) || null, area: WR.num(o.livingSpace), rooms: WR.num(o.rooms), title: o.title, type: o.objectType }));
