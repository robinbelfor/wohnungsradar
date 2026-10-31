#!/usr/bin/env python3
"""Wohnungsradar Wien – deterministic merge step (stdlib only, Python >= 3.8).

Usage (paths relative to the portal root, e.g. ~/projects/Wohnungsportal):
  python3 tools/merge.py known              -> writes data/known.json (what the agents already know)
  python3 tools/merge.py merge inbox/current <run_id>
                                            -> merges every *.json of that run in the folder, rewrites data files,
                                               prints a JSON summary (new matches for the notification)
  python3 tools/merge.py rebuild            -> only regenerates data/listings.js from the json files

Inbox file format (one per agent):
{
  "agent": "justimmo-a", "run_id": "2026102918",
  "brokers": [
    {"slug": "winegg", "ok": true, "complete": true,
     "seen_ids": ["123", "124"],            # ALL source ids of Vienna rental flats currently listed
     "listings": [ {...normalized...} ],     # new or changed listings, full detail
     "gone_ids": [], "reserved_ids": [],     # explicitly confirmed taken / reserved
     "error": null, "recipe_update": null, "notes": null}
  ]
}
"""
import datetime as dt
import hashlib
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA = os.path.join(ROOT, "data")
LISTINGS_JSON = os.path.join(DATA, "listings.json")
BROKERS_JSON = os.path.join(DATA, "brokers.json")
KNOWN_JSON = os.path.join(DATA, "known.json")
LISTINGS_JS = os.path.join(DATA, "listings.js")
CRITERIA_JSON = os.path.join(ROOT, "config", "suchkriterien.json")
RUNLOG = os.path.join(ROOT, "runs", "log.jsonl")

GONE_AFTER_MISSES = 2          # consecutive complete list reads without the id
PURGE_GONE_DAYS = 30
NEW_WINDOW_HOURS = 24

DISTRICTS = {
    1: "Innere Stadt", 2: "Leopoldstadt", 3: "Landstraße", 4: "Wieden", 5: "Margareten",
    6: "Mariahilf", 7: "Neubau", 8: "Josefstadt", 9: "Alsergrund", 10: "Favoriten",
    11: "Simmering", 12: "Meidling", 13: "Hietzing", 14: "Penzing", 15: "Rudolfsheim-Fünfhaus",
    16: "Ottakring", 17: "Hernals", 18: "Währing", 19: "Döbling", 20: "Brigittenau",
    21: "Floridsdorf", 22: "Donaustadt", 23: "Liesing",
}

NUM_FIELDS = ["rent_total", "rent_net", "operating_costs", "vat", "heating_costs", "other_costs", "deposit",
              "commission", "area", "rooms", "bedrooms", "bathrooms", "toilets", "floor_num",
              "floors_total", "year_built", "hwb", "fgee", "lat", "lng", "term_years"]
CORE_FIELDS = ["title", "rent_total", "rent_net", "operating_costs", "area", "rooms", "floor",
               "zip", "street", "outdoor", "available_from", "term", "commission", "images", "status"]


def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def to_num(v):
    """'1.450,50 €' -> 1450.5 ; '72,5 m²' -> 72.5 ; 3 -> 3.0 ; None/'' -> None"""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    s = re.sub(r"[^\d,.\-]", "", s)
    if not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    elif s.count(".") > 1 or re.search(r"\.\d{3}$", s):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def host_of(u):
    m = re.match(r"^https?://([^/:?#]+)", str(u or "").strip().lower())
    if not m:
        return None
    h = m.group(1)
    return h[4:] if h.startswith("www.") else h


def safe_seg(s):
    s = re.sub(r"[^A-Za-z0-9_\-.~]+", "-", str(s)).strip("-.")
    return s[:120] or hashlib.sha1(str(s).encode()).hexdigest()[:12]


def district_from_zip(z):
    m = re.match(r"^1(\d\d)0$", str(z or "").strip())
    if not m:
        return None
    d = int(m.group(1))
    return d if 1 <= d <= 23 else None


def normalize(raw, broker):
    l = dict(raw)
    slug = broker["slug"]
    l["broker"] = slug
    l["broker_name"] = l.get("broker_name") or broker.get("name") or slug
    l["source_id"] = str(l.get("source_id") or l.get("url") or "").strip()
    l["id"] = f"{slug}--{safe_seg(l['source_id'])}"
    for k in NUM_FIELDS:
        if k in l:
            l[k] = to_num(l[k])
    if l.get("rooms") is not None and l["rooms"] > 20:
        l["rooms"] = None
    z = str(l.get("zip") or "").strip()
    l["zip"] = z or None
    if not l.get("district"):
        l["district"] = district_from_zip(z)
    else:
        l["district"] = int(to_num(l["district"]) or 0) or district_from_zip(z)
    if l.get("district"):
        l["district_name"] = DISTRICTS.get(l["district"])
    if l.get("rent_total") is None and l.get("rent_net") is not None:
        parts = [l.get("rent_net"), l.get("operating_costs"), l.get("vat")]
        if all(p is not None for p in parts):
            l["rent_total"] = round(sum(parts), 2)
            l["rent_note"] = (l.get("rent_note") or "") + " (Gesamtmiete aus Netto + BK + USt berechnet)"
    if l.get("rent_total") and l.get("area"):
        l["price_per_m2"] = round(l["rent_total"] / l["area"], 2)
    else:
        l["price_per_m2"] = None
    imgs, seen = [], set()
    for u in l.get("images") or []:
        if isinstance(u, str) and u.startswith(("http://", "https://")) and u not in seen:
            seen.add(u)
            imgs.append(u)
    l["images"] = imgs
    l["floorplans"] = [u for u in (l.get("floorplans") or []) if isinstance(u, str) and u.startswith("http")]
    out = []
    for o in l.get("outdoor") or []:
        if isinstance(o, dict) and o.get("type"):
            out.append({"type": str(o["type"]).lower(), "area": to_num(o.get("area"))})
        elif isinstance(o, str):
            out.append({"type": o.lower(), "area": None})
    l["outdoor"] = out
    l["features"] = [str(f) for f in (l.get("features") or []) if f][:40]
    if l.get("commission_free") is None and l.get("commission") == 0:
        l["commission_free"] = True
    for k in ("status", "first_seen", "last_seen", "last_changed", "gone_since", "price_history", "miss_count"):
        l.pop(k, None) if k in ("first_seen", "last_seen", "last_changed", "gone_since", "price_history", "miss_count") else None
    st = str(raw.get("status") or "active").lower()
    l["status"] = st if st in ("active", "reserved", "gone") else "active"
    l["data_quality"] = l.get("data_quality") or ("full" if l["images"] and l.get("area") else "partial")
    return l


def fingerprint(l):
    core = {k: l.get(k) for k in CORE_FIELDS}
    return hashlib.sha1(json.dumps(core, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


# ---------------------------------------------------------------- matching (mirror of index.html)
def text_of(l):
    return " ".join([str(l.get("title") or ""), str(l.get("summary") or ""), " ".join(l.get("features") or []),
                     str(l.get("street") or ""), str(l.get("district_name") or "")]).lower()


def matches(l, s):
    if l.get("status") != "active":
        return False

    def rng(val, lo, hi):
        if val is None:
            return True  # unknown values never hide a flat
        if lo not in (None, "") and val < float(lo):
            return False
        if hi not in (None, "") and val > float(hi):
            return False
        return True

    if not rng(l.get("rent_total"), s.get("rent_min"), s.get("rent_max")):
        return False
    if not rng(l.get("area"), s.get("area_min"), s.get("area_max")):
        return False
    if not rng(l.get("rooms"), s.get("rooms_min"), s.get("rooms_max")):
        return False
    if not rng(l.get("price_per_m2"), None, s.get("ppm2_max")):
        return False
    d = s.get("districts") or []
    if d and l.get("district") is not None and l["district"] not in d:
        return False
    if s.get("outdoor") == "required" and not l.get("outdoor"):
        return False
    if s.get("elevator") == "required" and l.get("elevator") is not True:
        return False
    if s.get("term") == "unbefristet" and l.get("term") != "unbefristet":
        return False
    if s.get("commission_free") and l.get("commission_free") is not True:
        return False
    f = s.get("furnished") or "any"
    if f == "yes" and l.get("furnished") not in ("yes", "partly"):
        return False
    if f == "no" and l.get("furnished") in ("yes", "partly"):
        return False
    b = s.get("building") or []
    if b and l.get("building") not in b:
        return False
    if s.get("available_by") and l.get("available_from"):
        if str(l["available_from"])[:10] > str(s["available_by"])[:10]:
            return False
    t = text_of(l)
    inc = [k.strip().lower() for k in (s.get("keywords_include") or []) if k.strip()]
    exc = [k.strip().lower() for k in (s.get("keywords_exclude") or []) if k.strip()]
    if inc and not any(k in t for k in inc):
        return False
    if any(k in t for k in exc):
        return False
    return True


# ---------------------------------------------------------------- commands
def cmd_known():
    listings = load(LISTINGS_JSON, {})
    brokers = load(BROKERS_JSON, [])
    known = {}
    for l in listings.values():
        if l.get("status") == "gone":
            continue
        known.setdefault(l["broker"], {})[l["source_id"]] = {
            "rent_total": l.get("rent_total"), "area": l.get("area"), "status": l.get("status"), "url": l.get("url")}
    save(KNOWN_JSON, {"generated_at": now_iso(), "brokers": known})
    print(json.dumps({"brokers": len(brokers), "known_listings": sum(len(v) for v in known.values())}))


def write_js(listings, brokers, criteria, extra):
    payload = {
        "generated_at": now_iso(),
        "listings": sorted(listings.values(), key=lambda x: x.get("first_seen") or "", reverse=True),
        "brokers": [{k: b.get(k) for k in ("slug", "name", "website", "platform", "enabled", "last_run",
                                            "last_ok", "last_error", "active_count", "consecutive_failures",
                                            "tier")} for b in brokers],
        "criteria": criteria,
        "runs": extra.get("runs", []),
    }
    tmp = LISTINGS_JS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("window.WP_DATA = ")
        json.dump(payload, f, ensure_ascii=False)
        f.write(";\n")
    os.replace(tmp, LISTINGS_JS)


def recent_runs(n=48):
    out = []
    try:
        with open(RUNLOG, encoding="utf-8") as f:
            for line in f.readlines()[-n:]:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except FileNotFoundError:
        pass
    return out


def cmd_rebuild():
    write_js(load(LISTINGS_JSON, {}), load(BROKERS_JSON, []), load(CRITERIA_JSON, {"searches": []}),
             {"runs": recent_runs()})
    print("ok")


def cmd_merge(inbox, run_id=None):
    ts = now_iso()
    tnow = parse_iso(ts)
    listings = load(LISTINGS_JSON, {})
    brokers = load(BROKERS_JSON, [])
    bmap = {b["slug"]: b for b in brokers}
    criteria = load(CRITERIA_JSON, {"searches": []})
    files = sorted(fn for fn in os.listdir(inbox) if fn.endswith(".json"))
    new_ids, imported_ids, changed_ids, gone_ids, errors = [], [], [], [], []
    for fn in files:
        try:
            batch = load(os.path.join(inbox, fn), None)
            if not batch:
                errors.append({"file": fn, "error": "unreadable json"})
                continue
            if run_id and str(batch.get("run_id")) != str(run_id):
                continue  # leftover from an earlier run (inbox/current is reused)
        except Exception as e:  # noqa
            errors.append({"file": fn, "error": str(e)})
            continue
        for r in batch.get("brokers", []):
            slug = r.get("slug")
            b = bmap.get(slug)
            if not b:
                errors.append({"file": fn, "error": f"unknown broker {slug}"})
                continue
            b["last_run"] = ts
            if r.get("recipe_update"):
                if b.get("method") == "browser":  # browser recipes are files under agents/browser/ - keep the hint only
                    b["browser_feedback"] = str(r["recipe_update"])[:1000]
                    b["browser_feedback_at"] = ts
                else:
                    b["recipe"] = r["recipe_update"]
                    b["recipe_updated"] = ts
            if r.get("platform_detected") and not b.get("platform"):
                b["platform"] = r["platform_detected"]
            if r.get("list_urls_update"):
                urls = [u for u in r["list_urls_update"] if isinstance(u, str) and u.startswith("http")]
                if urls:
                    b["list_urls"] = urls[:12]
            if r.get("website_update") and str(r["website_update"]).startswith("http"):
                b["website"] = r["website_update"]
            dom = host_of(b.get("website"))
            twin = next((o for o in brokers if o is not b and o.get("enabled") is not False and dom
                         and host_of(o.get("website")) == dom), None)
            if twin and b.get("enabled") is not False:
                b["enabled"] = False
                b["disabled_reason"] = f"Dublette von {twin['slug']} (gleiche Website)"
                continue
            if r.get("repair"):
                b["last_repair"] = ts
            if "offers_rentals" in r and r["offers_rentals"] is not None:
                b["offers_rentals"] = bool(r["offers_rentals"])
            if r.get("fetches") is not None:
                try:
                    b["last_fetches"] = int(r["fetches"])
                except (TypeError, ValueError):
                    pass
            if r.get("rate_limited"):
                # not the broker's fault: no failure count, never mark flats as gone from a partial read
                r["complete"] = False
                if not (r.get("listings") or r.get("seen_ids")):
                    b["last_error"] = "WebFetch-Stundenlimit erreicht – nächster Lauf holt nach"
                    continue
                r["ok"] = True
            if not r.get("ok"):
                b["consecutive_failures"] = int(b.get("consecutive_failures") or 0) + 1
                b["last_error"] = (r.get("error") or "unbekannter Fehler")[:300]
                errors.append({"broker": slug, "error": b["last_error"]})
                continue
            b["consecutive_failures"] = 0
            b["last_error"] = None
            # A broker is "settled" once one complete list read happened, or after 2 earlier good reads.
            # Before that, IDs that show up for the first time are older stock that earlier partial reads
            # (budget limits, pagination) simply had not reached - they must not trigger notifications.
            if b.get("reads_counted_at") != ts:
                prev = b.get("ok_reads")
                if prev is None:
                    prev = 1 if b.get("last_ok") else 0  # brokers read before this counter existed
                b["prev_ok_reads"] = int(prev)
                b["ok_reads"] = int(prev) + 1
                b["reads_counted_at"] = ts
            settled = bool(b.get("complete_reads")) or int(b.get("prev_ok_reads") or 0) >= 2
            b["last_ok"] = ts
            if not b.get("baseline_at"):
                b["baseline_at"] = ts  # everything listed at the first good read is the starting stock
            seen_order = [str(x) for x in (r.get("seen_ids") or [])]
            top_of_list = set(seen_order[:max(3, int(len(seen_order) * 0.4))])

            def first_seen_stamp(sid, settled=settled, r=r, b=b, seen_order=seen_order, top=top_of_list):
                # incomplete read: only the top of the list (where brokers put new offers) can be new;
                # entries further down are older offers that pagination shifts brought into range
                if not settled or (not r.get("complete") and seen_order and str(sid) not in top):
                    return b["baseline_at"]
                return ts
            pending = dict(b.get("pending") or {})
            # upsert detailed listings
            for raw in r.get("listings") or []:
                try:
                    l = normalize(raw, b)
                except Exception as e:  # noqa
                    errors.append({"broker": slug, "error": f"normalize: {e}"})
                    continue
                if not l["source_id"]:
                    continue
                old = listings.get(l["id"])
                fp = fingerprint(l)
                if old is None:
                    appeared = pending.pop(l["source_id"], None) or first_seen_stamp(l["source_id"])
                    baseline = appeared <= b["baseline_at"]
                    l.update(first_seen=appeared, last_seen=ts, last_changed=ts, gone_since=None, miss_count=0,
                             fingerprint=fp, baseline=baseline,
                             price_history=[{"at": ts[:10], "rent_total": l.get("rent_total")}])
                    listings[l["id"]] = l
                    (imported_ids if baseline else new_ids).append(l["id"])
                else:
                    keep = {k: old.get(k) for k in ("first_seen", "price_history")}
                    was_gone = old.get("status") == "gone"
                    merged = dict(old)
                    for k, v in l.items():
                        if v not in (None, [], "") or k in ("status",):
                            merged[k] = v
                    merged.update(keep, last_seen=ts, miss_count=0)
                    if was_gone and merged["status"] != "gone":
                        merged["gone_since"] = None
                        merged["reactivated"] = ts
                    nfp = fingerprint(merged)
                    if nfp != old.get("fingerprint"):
                        merged["fingerprint"] = nfp
                        merged["last_changed"] = ts
                        changed_ids.append(l["id"])
                        if merged.get("rent_total") != old.get("rent_total"):
                            ph = list(merged.get("price_history") or [])
                            ph.append({"at": ts[:10], "rent_total": merged.get("rent_total")})
                            merged["price_history"] = ph[-12:]
                    listings[l["id"]] = merged
            seen = set(str(x) for x in (r.get("seen_ids") or []))
            seen |= set(str((x or {}).get("source_id")) for x in (r.get("listings") or []))
            for sid in seen:
                lid = f"{slug}--{safe_seg(sid)}"
                if lid not in listings:
                    pending.setdefault(sid, first_seen_stamp(sid))  # seen in the list, details follow in a later run
                if lid in listings:
                    L = listings[lid]
                    L["last_seen"] = ts
                    L["miss_count"] = 0
                    if L.get("status") == "gone" and str(sid) not in set(map(str, r.get("gone_ids") or [])):
                        L["status"] = "active"
                        L["gone_since"] = None
                        L["reactivated"] = ts
            for sid in r.get("reserved_ids") or []:
                lid = f"{slug}--{safe_seg(sid)}"
                if lid in listings and listings[lid].get("status") == "active":
                    listings[lid]["status"] = "reserved"
                    listings[lid]["last_changed"] = ts
            explicit_gone = set(f"{slug}--{safe_seg(s)}" for s in (r.get("gone_ids") or []))
            for lid in explicit_gone:
                if lid in listings and listings[lid].get("status") != "gone":
                    listings[lid].update(status="gone", gone_since=ts, last_changed=ts)
                    gone_ids.append(lid)
            if r.get("complete"):
                b["complete_reads"] = int(b.get("complete_reads") or 0) + (0 if b.get("complete_counted_at") == ts else 1)
                b["complete_counted_at"] = ts
                pending = {k: v for k, v in pending.items() if k in seen}
            b["pending"] = dict(list(pending.items())[-1500:])
            if r.get("complete"):
                seen_lids = set(f"{slug}--{safe_seg(s)}" for s in seen)
                for lid, L in listings.items():
                    if L.get("broker") != slug or L.get("status") == "gone" or lid in seen_lids:
                        continue
                    L["miss_count"] = int(L.get("miss_count") or 0) + 1
                    if L["miss_count"] >= GONE_AFTER_MISSES:
                        L.update(status="gone", gone_since=ts, last_changed=ts)
                        gone_ids.append(lid)
    # purge old gone listings
    for lid in [k for k, L in listings.items() if L.get("status") == "gone"]:
        g = parse_iso(listings[lid].get("gone_since"))
        if g and (tnow - g).days > PURGE_GONE_DAYS:
            del listings[lid]
    # broker counts
    counts = {}
    for L in listings.values():
        if L.get("status") in ("active", "reserved"):
            counts[L["broker"]] = counts.get(L["broker"], 0) + 1
    for b in brokers:
        b["active_count"] = counts.get(b["slug"], 0)
    # notification matches (new + reactivated + price drops into range)
    notify_searches = [s for s in criteria.get("searches", []) if s.get("notify")]
    hits = []
    for lid in dict.fromkeys(new_ids):
        L = listings.get(lid)
        if not L:
            continue
        names = [s.get("name") or "Suche" for s in notify_searches if matches(L, s)]
        if names:
            hits.append({"id": lid, "searches": names, "title": L.get("title"), "district": L.get("district"),
                         "district_name": L.get("district_name"), "street": L.get("street"),
                         "rent_total": L.get("rent_total"), "area": L.get("area"), "rooms": L.get("rooms"),
                         "outdoor": [o["type"] for o in L.get("outdoor") or []], "term": L.get("term"),
                         "broker": L.get("broker_name"), "url": L.get("url")})
    run = {"at": ts, "run_id": run_id, "files": len(files),
           "brokers_ok": sum(1 for b in brokers if b.get("last_run") == ts and b.get("last_ok") == ts),
           "brokers_failed": sum(1 for b in brokers if b.get("last_run") == ts and b.get("last_ok") != ts),
           "new": len(set(new_ids)), "imported": len(set(imported_ids)),
           "pending": sum(len(b.get("pending") or {}) for b in brokers), "changed": len(set(changed_ids)), "gone": len(set(gone_ids)),
           "matches": len(hits), "active_total": sum(counts.values())}
    os.makedirs(os.path.dirname(RUNLOG), exist_ok=True)
    with open(RUNLOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(run, ensure_ascii=False) + "\n")
    save(LISTINGS_JSON, listings)
    save(BROKERS_JSON, brokers)
    write_js(listings, brokers, criteria, {"runs": recent_runs()})
    cmd_known_silent(listings)
    print(json.dumps({"run": run, "matches": hits, "errors": errors[:40]}, ensure_ascii=False, indent=1))


def cmd_known_silent(listings):
    known = {}
    for l in listings.values():
        if l.get("status") == "gone":
            continue
        known.setdefault(l["broker"], {})[l["source_id"]] = {
            "rent_total": l.get("rent_total"), "area": l.get("area"), "status": l.get("status"), "url": l.get("url")}
    save(KNOWN_JSON, {"generated_at": now_iso(), "brokers": known})


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    c = sys.argv[1]
    if c == "known":
        cmd_known()
    elif c == "merge" and len(sys.argv) > 2:
        cmd_merge(sys.argv[2] if os.path.isabs(sys.argv[2]) else os.path.join(ROOT, sys.argv[2]),
                  sys.argv[3] if len(sys.argv) > 3 else None)
    elif c == "rebuild":
        cmd_rebuild()
    else:
        print(__doc__)
        sys.exit(1)
