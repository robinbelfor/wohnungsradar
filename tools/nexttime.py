#!/usr/bin/env python3
"""Next scheduled scan time (UTC, RFC3339) from config/abgleich.json:
   {"times": ["06:00", "12:00"], "tz": "Europe/Vienna"}
   python3 tools/nexttime.py   -> 2026-10-30T05:00:00Z
"""
import datetime as dt
import json
import os
from zoneinfo import ZoneInfo

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
cfg = {}
try:
    cfg = json.load(open(os.path.join(ROOT, "config", "abgleich.json"), encoding="utf-8"))
except Exception:
    pass
times = cfg.get("times") or ["06:00", "12:00"]
tz = ZoneInfo(cfg.get("tz") or "Europe/Vienna")
now = dt.datetime.now(tz) + dt.timedelta(minutes=10)  # never schedule the run that is just happening
cands = []
for d in range(0, 3):
    day = (now + dt.timedelta(days=d)).date()
    for t in times:
        h, m = map(int, t.split(":"))
        c = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=tz)
        if c > now:
            cands.append(c)
nxt = min(cands)
print(nxt.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), nxt.strftime("%a %d.%m. %H:%M %Z"))
