// OTTO: Start-URL https://www.otto.at/immobilien/  (onOffice-JSON der eigenen Website)
// fi.rg = Gesamtmiete brutto, fi.hx = Hauptmiete netto (Detailseite zeigt "Hauptmiete inkl. USt." = hx × 1,10)
const j = await WR.getJSON('/wp-json/api/v1/onoffice/otto/estate/minimal');
window.__WR_RESULT = j.data.estates.filter(e => e.me.us === 'wohnen' && e.me.ma === 'miete' && !/haus|grundstueck|investment/.test(e.me.ty) && WR.isViennaZip(e.lo.pc))
  .map(e => ({ source_id: String(e.id), url: 'https://www.otto.at/immobilien/' + e.la.deu.sl, zip: e.lo.pc, price: e.fi.rg || null,
    rent_net: e.fi.hx || null, area: e.ar.ls || null, rooms: e.pr.cr || null, title: e.la.deu.tt, available_text: e.la.deu.af || null }));
