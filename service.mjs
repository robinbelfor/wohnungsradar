// Wohnungsradar Browser-Dienst
// Umgebungsvariablen (in Coolify setzen):
//   GITHUB_TOKEN  Fine-grained Token, nur Repository robinbelfor/wohnungsradar, Berechtigung "Contents: Read and write"
//   RUN_TIMES     Uhrzeiten (Wien), Standard "05:25,11:25" – kurz vor den Scans um 6 und 12 Uhr
//   RUN_ON_START  "1" = einmal direkt nach dem Start laufen (zum Testen)
//   REPO, BRANCH  Standard robinbelfor/wohnungsradar, engine
import http from "node:http";
import { chromium } from "playwright";

const REPO = process.env.REPO || "robinbelfor/wohnungsradar";
const BRANCH = process.env.BRANCH || "engine";
const TOKEN = process.env.GITHUB_TOKEN || "";
const TIMES = (process.env.RUN_TIMES || "05:25,11:25").split(",").map(s => s.trim()).filter(Boolean);
const TZ = "Europe/Vienna";
const RAW = process.env.RAW_BASE || `https://raw.githubusercontent.com/${REPO}/${BRANCH}/`;
const VERSION = "1.0.0";
const state = { version: VERSION, started: new Date().toISOString(), running: false, last: null };

const log = (...a) => console.log(new Date().toISOString(), ...a);
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function raw(path, json = false) {
  const r = await fetch(RAW + path + "?t=" + Date.now(), { headers: { "Cache-Control": "no-cache" } });
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return json ? r.json() : r.text();
}
async function gh(path, init = {}) {
  const r = await fetch(`https://api.github.com/repos/${REPO}/${path}`, {
    ...init, headers: { Authorization: `Bearer ${TOKEN}`, Accept: "application/vnd.github+json", "User-Agent": "wohnungsradar-browser", ...(init.headers || {}) } });
  const body = await r.text();
  if (!r.ok && r.status !== 404) throw new Error(`GitHub ${r.status}: ${body.slice(0, 300)}`);
  return { status: r.status, json: body ? JSON.parse(body) : null };
}
async function putFile(path, content, message) {
  const cur = await gh(`contents/${path}?ref=${BRANCH}`);
  const sha = cur.status === 200 ? cur.json.sha : undefined;
  await gh(`contents/${path}`, { method: "PUT", body: JSON.stringify({ message, branch: BRANCH, sha,
    content: Buffer.from(content, "utf8").toString("base64") }) });
}
const num = v => (v == null || v === "" ? null : Number(v));

async function scrapeBroker(ctx, b, known, lib, recipes) {
  const cfg = b.browser || {};
  const res = { slug: b.slug, ok: false, complete: false, rows: [], details: [], known_check: [], error: null };
  const page = await ctx.newPage();
  try {
    await page.goto(cfg.start_url, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(3500);
    await page.evaluate(lib);
    const out = await page.evaluate(`(async () => { ${recipes[cfg.list]}\n; return window.__WR_RESULT; })()`);
    const rows = Array.isArray(out) ? out : (out && out.rows) || [];
    res.complete = Array.isArray(out) ? rows.length > 0 : !!(out && out.complete);
    res.rows = rows;
    const k = known[b.slug] || { listings: {}, pending: new Set() };
    const inc = cfg.include || ".";
    // new or changed offers, in list order (lists are sorted newest first where possible)
    const cand = rows.filter(r => {
      const sid = String(r.source_id || ""); if (!sid) return false;
      const old = k.listings[sid]; if (!old) return true;
      const p = num(r.price), a = num(r.area);
      return (p && old.rent_total && Math.abs(p - old.rent_total) > 1) || (a && old.area && Math.abs(a - old.area) > 0.5);
    }).slice(0, cfg.detail_cap || 30);
    if (cand.length) {
      if (cfg.detail === "api" && cfg.detail_js) {
        for (let i = 0; i < cand.length; i += 8) {
          const ids = cand.slice(i, i + 8).map(r => r.source_id);
          const d = await page.evaluate(`(async () => { const IDS = ${JSON.stringify(ids)};\n${recipes[cfg.detail_js]}\n; return window.__WR_RESULT; })()`);
          (d || []).forEach(x => res.details.push({ mode: "api", source_id: x.source_id, raw: x }));
        }
      } else if (cfg.detail === "navigate") {
        for (const r of cand) {
          try {
            await page.goto(r.url, { waitUntil: "domcontentloaded", timeout: 45000 }); await page.waitForTimeout(2500);
            await page.evaluate(lib);
            const n = await page.evaluate(([inc, scope, sid]) => window.WR.normalize(window.WR.liveDetail({ include: new RegExp(inc), scope: scope || undefined }), { source_id: sid }), [inc, cfg.scope || "", String(r.source_id)]);
            res.details.push({ mode: "navigate", source_id: String(r.source_id), normalized: n });
          } catch (e) { res.details.push({ mode: "navigate", source_id: String(r.source_id), error: String(e).slice(0, 200) }); }
        }
        await page.goto(cfg.start_url, { waitUntil: "domcontentloaded", timeout: 60000 }); await page.waitForTimeout(2000); await page.evaluate(lib);
      } else {
        for (let i = 0; i < cand.length; i += 8) {
          const items = cand.slice(i, i + 8).map(r => ({ source_id: String(r.source_id), url: r.url }));
          const d = await page.evaluate(([items, inc, rawScan, scope]) => window.WR.detailsNormalized(items, { include: new RegExp(inc), rawScan, scope: scope || undefined }), [items, inc, !!cfg.raw_scan, cfg.scope || ""]);
          (d || []).forEach(x => res.details.push({ mode: "fetch", source_id: x.source_id, normalized: x }));
        }
      }
    }
    // incomplete list: check known offers that are missing, so they are not lost and real removals are seen
    if (!res.complete) {
      const seen = new Set(rows.map(r => String(r.source_id)));
      const missing = Object.entries(k.listings).filter(([sid]) => !seen.has(sid)).slice(0, 40);
      for (const [sid, l] of missing) {
        if (!l.url) continue;
        const c = await page.evaluate(async url => { try { const r = await fetch(url, { credentials: "include" }); const t = await r.text();
          return { status: r.status, final_url: r.url, flags: (t.match(/\b(vermietet|vergeben|reserviert|nicht mehr verfügbar)\b/gi) || []).slice(0, 3) }; }
          catch (e) { return { status: 0, error: String(e).slice(0, 120) }; } }, l.url);
        res.known_check.push({ source_id: sid, url: l.url, ...c });
      }
    }
    res.ok = true;
  } catch (e) {
    res.error = String(e && e.message || e).slice(0, 400);
  } finally {
    await page.close().catch(() => {});
  }
  return res;
}

async function runOnce(reason) {
  if (state.running) return;
  state.running = true;
  const t0 = Date.now();
  log("Lauf startet:", reason);
  let browser;
  try {
    const [brokers, listings, lib] = await Promise.all([raw("data/brokers.json", true), raw("data/listings.json", true), raw("agents/browser-lib.min.js")]);
    const list = Array.isArray(listings) ? listings : Object.values(listings.listings || listings);
    const targets = brokers.filter(b => b.method === "browser" && b.enabled !== false && b.browser);
    const files = new Set(); targets.forEach(b => { files.add(b.browser.list); if (b.browser.detail_js) files.add(b.browser.detail_js); });
    const recipes = {}; for (const f of files) recipes[f] = await raw("agents/browser/" + f);
    const known = {};
    for (const b of targets) known[b.slug] = { listings: {}, pending: new Set(Object.keys(b.pending || {})) };
    for (const l of list) if (known[l.broker] && l.status !== "gone") known[l.broker].listings[String(l.source_id)] = { rent_total: num(l.rent_total), area: num(l.area), url: l.url };
    browser = await chromium.launch({ args: ["--no-sandbox", "--disable-dev-shm-usage"] });
    const ctx = await browser.newContext({ locale: "de-AT", timezoneId: TZ, viewport: { width: 1366, height: 900 } });
    const results = [];
    for (const b of targets) { log("Makler", b.slug); results.push(await scrapeBroker(ctx, b, known, lib, recipes)); await sleep(1500); }
    const out = { service: "wohnungsradar-browser", version: VERSION, reason, fetched_at: new Date().toISOString(), duration_s: Math.round((Date.now() - t0) / 1000), brokers: results };
    const text = JSON.stringify(out);
    if (TOKEN) { await putFile("inbox/browser/latest.json", text, `Browser-Dienst: ${results.filter(r => r.ok).length}/${results.length} Makler`); log("nach GitHub geschrieben", text.length, "Bytes"); }
    else log("Kein GITHUB_TOKEN gesetzt – Ergebnis nicht gespeichert");
    state.last = { at: out.fetched_at, duration_s: out.duration_s, brokers: results.map(r => ({ slug: r.slug, ok: r.ok, rows: r.rows.length, details: r.details.length, error: r.error })) };
  } catch (e) {
    state.last = { at: new Date().toISOString(), error: String(e && e.message || e) };
    log("Fehler:", state.last.error);
  } finally {
    if (browser) await browser.close().catch(() => {});
    state.running = false;
  }
}

// simple scheduler on Vienna wall-clock time
const fmt = new Intl.DateTimeFormat("de-AT", { timeZone: TZ, hour: "2-digit", minute: "2-digit", year: "numeric", month: "2-digit", day: "2-digit", hourCycle: "h23" });
let lastKey = "";
setInterval(() => {
  const p = Object.fromEntries(fmt.formatToParts(new Date()).map(x => [x.type, x.value]));
  const hm = `${p.hour}:${p.minute}`, key = `${p.year}-${p.month}-${p.day} ${hm}`;
  if (TIMES.includes(hm) && key !== lastKey) { lastKey = key; runOnce("Zeitplan " + hm); }
}, 20000);

http.createServer((req, res) => {
  res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify({ ...state, times: TIMES, timezone: TZ, token: TOKEN ? "gesetzt" : "fehlt" }, null, 1));
}).listen(Number(process.env.PORT || 3000), () => log("Browser-Dienst läuft, Zeiten:", TIMES.join(", "), TZ));

if (process.env.RUN_ON_START === "1") runOnce("Start");
