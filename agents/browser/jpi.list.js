// JPI: Start-URL https://jpi.at/immobilien/?_nutzungsart=wohnen&_vermarktungsart=miete  (FacetWP-Seiten durchblättern)
await WR.sleep(1500);
const grab = () => [...document.querySelectorAll('a[href*="/immobilien/"]')].map(a => a.href.split('#')[0]).filter(h => /-101-\d+\/?$/.test(h));
const all = new Set(grab());
const tp = (window.FWP && FWP.settings && FWP.settings.pager && FWP.settings.pager.total_pages) || 1;
for (let p = 2; p <= tp; p++) { FWP.paged = p; FWP.refresh(); await WR.sleep(2500); grab().forEach(l => all.add(l)); }
window.__WR_RESULT = [...all].map(u => ({ source_id: (u.match(/-(101-\d+)\/?$/) || [])[1], url: u, zip: (u.match(/-(1\d{2}0)-wien/) || [])[1] || null }))
  .filter(x => x.source_id && (!x.zip || WR.isViennaZip(x.zip)));
