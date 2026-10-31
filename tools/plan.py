#!/usr/bin/env python3
"""Wohnungsradar Wien – plans one polling run (stdlib only).

  python3 tools/plan.py <run_id> [--all]      (writes plan/current/, overwritten every run)

Reads data/brokers.json + data/known.json, decides which brokers are due, groups them into
agent batches and writes one self-contained prompt file per batch to plan/current/batch-XX.md
plus plan/current/plan.json. The orchestrator passes each prompt file verbatim to a sub-agent.

Due rules (tier):
  A  broker had Vienna rental flats within the last 14 days, or was never polled  -> every run
  B  broker polled fine but had no Vienna rentals for 14 days                      -> every 6 hours
  R  broker failed 3+ times in a row                                                -> repair agent,
     at most 3 per run and at most once per 24 h per broker
  O  broker without recipe -> onboarding, at most 24 per run, highest `priority` first
  brokers that offer no rentals on their own site (offers_rentals=false) -> weekly re-check
  disabled brokers (enabled=false) are skipped.
"""
import datetime as dt
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BATCH_ROUTINE = 8
BATCH_ONBOARD = 4
TIER_B_HOURS = 6
REPAIR_PER_RUN = 3
ONBOARD_PER_RUN = 24          # new brokers are onboarded gradually, highest priority first
FETCH_BUDGET = 250            # expected WebFetch calls per run (override in config/abgleich.json)
NO_RENTALS_DAYS = 7           # brokers without own rental offers are re-checked weekly


def load(p, d):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return d


def parse(s):
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")) if s else None
    except ValueError:
        return None


def main():
    run_id = sys.argv[1]
    force_all = "--all" in sys.argv
    global ONBOARD_PER_RUN
    deferred = []
    for a in sys.argv:
        if a.startswith("--onboard="):
            ONBOARD_PER_RUN = int(a.split("=", 1)[1])
    now = dt.datetime.now(dt.timezone.utc)
    brokers = load(os.path.join(ROOT, "data", "brokers.json"), [])
    known = load(os.path.join(ROOT, "data", "known.json"), {}).get("brokers", {})
    listings = load(os.path.join(ROOT, "data", "listings.json"), {})
    last_rental = {}
    for l in listings.values():
        ls = l.get("last_seen")
        if ls and ls > last_rental.get(l["broker"], ""):
            last_rental[l["broker"]] = ls

    routine, onboard, repair, browser = [], [], [], []
    for b in brokers:
        if b.get("enabled") is False:
            continue
        if b.get("method") == "browser" and b.get("browser"):
            last_run = parse(b.get("last_run"))
            recent = parse(last_rental.get(b["slug"]))
            hot = force_all or bool(b.get("pending")) or int(b.get("active_count") or 0) > 0 or not b.get("last_ok")
            if hot or last_run is None or (now - last_run).total_seconds() >= TIER_B_HOURS * 3600 - 600:
                browser.append(b)
            continue
        fails = int(b.get("consecutive_failures") or 0)
        lr = parse(b.get("last_repair"))
        if fails >= 3 and (lr is None or (now - lr).total_seconds() > 86400):
            repair.append(b)
            continue
        if not b.get("recipe") or not b.get("last_ok"):
            onboard.append(b)
            continue
        last_run = parse(b.get("last_run"))
        if b.get("offers_rentals") is False:
            if last_run is None or (now - last_run).days >= NO_RENTALS_DAYS:
                routine.append(b)
            continue
        recent = parse(last_rental.get(b["slug"]))
        tier_a = (force_all or (recent and (now - recent).days < 14) or b.get("tier") == "A"
                  or bool(b.get("pending")) or int(b.get("active_count") or 0) > 0)
        if tier_a or last_run is None or (now - last_run).total_seconds() >= TIER_B_HOURS * 3600 - 600:
            routine.append(b)
    repair = repair[:REPAIR_PER_RUN]
    # fetch budget: WebFetch has an hourly limit. Keep the expected number of fetches per run below
    # FETCH_BUDGET; routine brokers that do not fit are deferred (least recently polled go first next time).
    cfg = load(os.path.join(ROOT, "config", "abgleich.json"), {})
    budget = int(cfg.get("fetch_budget") or FETCH_BUDGET)
    def cost(b):
        cap = max(14, int(b.get("list_budget") or 0) + 6)
        return max(2, min(int(b.get("last_fetches") or 3), cap))
    routine.sort(key=lambda b: (-(1 if last_rental.get(b["slug"]) else 0), b.get("last_run") or ""))
    used, kept, deferred = 0, [], []
    for b in repair:
        used += 16
    for b in routine:
        if used + cost(b) <= budget:
            kept.append(b); used += cost(b)
        else:
            deferred.append(b)
    routine = kept
    onboard_room = max(0, (budget - used) // 8)
    ONBOARD_PER_RUN = min(ONBOARD_PER_RUN, onboard_room)
    onboard_total = len(onboard)
    onboard = sorted(onboard, key=lambda b: (-int(b.get("priority") or 0), b["slug"]))[:ONBOARD_PER_RUN]

    def chunks(lst, n):
        lst = sorted(lst, key=lambda x: (x.get("platform") or "zz", x["slug"]))
        return [lst[i:i + n] for i in range(0, len(lst), n)]

    only = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--only=")), None)
    batches = []
    onboard_hi = [b for b in onboard if int(b.get("priority") or 0) >= 30]
    onboard_lo = [b for b in onboard if int(b.get("priority") or 0) < 30]
    for kind, lst, n in (("routine", routine, BATCH_ROUTINE), ("onboarding", onboard_hi, BATCH_ONBOARD),
                         ("classify", onboard_lo, 6), ("repair", repair, 1), ("browser", browser, 3)):
        if only and kind != only:
            continue
        if kind == "browser" and "--no-browser" in sys.argv:
            continue  # cloud mode: JavaScript brokers come from the browser service on the server
        for c in chunks(lst, n):
            batches.append({"kind": kind, "brokers": c})

    out_dir = os.path.join(ROOT, "plan", "current")
    os.makedirs(out_dir, exist_ok=True)
    meta = []
    for i, bt in enumerate(batches, 1):
        bid = f"batch-{i:02d}"
        mode = "onboarding" if bt["kind"] == "classify" else bt["kind"]
        book = "{BROWSER_PLAYBOOK}" if bt["kind"] == "browser" else "{PLAYBOOK}"
        lines = [f"# Auftrag {bid} ({bt['kind']}) – Lauf {run_id}", "",
                 f"Modus: **{mode}**. Ergebnisdatei: `{{OUT_DIR}}/{bid}.json` (Feld run_id: \"{run_id}\")",
                 f"Lies zuerst dein Handbuch: `{book}` und halte dich exakt daran.", "",
                 "## Makler dieser Charge", ""]
        for b in bt["brokers"]:
            kn = sorted((known.get(b["slug"]) or {}).keys())
            is_browser = b.get("method") == "browser" and b.get("browser")
            lines += [f"### {b['name']}  (slug: `{b['slug']}`)",
                      f"- Website: {b.get('website') or '–'}",
                      f"- Software: {b.get('platform') or 'unbekannt'}"]
            if not is_browser:
                lines.append("- Listen-URLs (nur diese bzw. von WebFetch gelieferte Links abrufen):")
                lines += [f"  - {u}" for u in (b.get("list_urls") or [])] or ["  - (keine bekannt – Onboarding)"]
            if b.get("method") == "browser" and b.get("browser"):
                bw = b["browser"]
                lines += [f"- Methode: **Browser**. Start-URL: {bw.get('start_url')}",
                          f"- Listen-Rezept: `{{PLAYBOOK_DIR}}/browser/{bw.get('list')}`",
                          f"- Detail-Modus: {bw.get('detail', 'fetch')}"
                          + (f" (Rezept `{{PLAYBOOK_DIR}}/browser/{bw.get('detail_js')}`)" if bw.get("detail_js") else ""),
                          f"- INCLUDE (Bild-Filter, RegExp): `{bw.get('include', '.')}` · RAW: {str(bool(bw.get('raw_scan'))).lower()}"
                          + (f" · SCOPE: `{bw['scope']}`" if bw.get("scope") else ""),
                          f"- detail_cap: {int(bw.get('detail_cap') or 30)}"]
                if bw.get("notes"):
                    lines.append(f"- Hinweise: {bw['notes']}")
            if b.get("list_budget"):
                lines.append(f"- Listen-Budget für diesen Makler: bis {int(b['list_budget'])} Listenseiten (große Bestände)")
            if not is_browser:
                lines.append(f"- Rezept: {b.get('recipe') or '(noch keins – im Onboarding ermitteln)'}")
            if b.get("last_error"):
                lines.append(f"- Letzter Fehler: {b['last_error']}")
            lines.append(f"- Bekannte aktive source_ids ({len(kn)}): {', '.join(kn) if kn else '–'}")
            lines.append("")
        if bt["kind"] == "classify":
            lines += ["Hinweis: Diese Makler stammen aus Branchenverzeichnissen. Viele haben keine Wiener Mietwohnungen",
                      "auf der eigenen Seite. Prüfe zuerst knapp (≤ 4 Abrufe), ob es überhaupt eine Objektliste mit",
                      "Mietwohnungen in Wien gibt. Wenn nein: offers_rentals false und weiter. Wenn ja: normales Onboarding.", ""]
        with open(os.path.join(out_dir, bid + ".md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        meta.append({"batch": bid, "kind": bt["kind"], "brokers": [b["slug"] for b in bt["brokers"]]})
    with open(os.path.join(out_dir, "plan.json"), "w", encoding="utf-8") as f:
        json.dump({"run_id": run_id, "created": now.isoformat(), "batches": meta}, f, ensure_ascii=False, indent=1)
    print(json.dumps({"run_id": run_id, "batches": len(batches),
                      "routine": len(routine), "onboarding": len(onboard),
                      "onboarding_queue": onboard_total - len(onboard), "repair": len(repair),
                      "deferred": len(deferred), "expected_fetches": used + 8 * len(onboard)}))


if __name__ == "__main__":
    main()
