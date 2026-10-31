#!/usr/bin/env python3
"""Prints the block of entry URLs that the hourly task's prompt must contain.

WebFetch only opens URLs the user provided in the run (or that a previous fetch/search returned), so the
scheduled task's prompt carries each broker's entry URLs. Pagination and detail links are picked up from
the fetched pages themselves. Brokers without a confirmed entry URL fall back to one WebSearch per run.

  python3 tools/urlblock.py            -> URL block on stdout
  python3 tools/urlblock.py --hash     -> short hash of the block (to see whether the task prompt is outdated)
"""
import hashlib
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OK = re.compile(r"^https?://[^\s<>\"'`]{4,300}$")


def block():
    brokers = json.load(open(os.path.join(ROOT, "data", "brokers.json"), encoding="utf-8"))
    urls = []
    for b in sorted(brokers, key=lambda x: x["slug"]):
        if b.get("enabled") is False or b.get("offers_rentals") is False or b.get("method") == "browser":
            continue
        cand = list(b.get("list_urls") or [])
        if not b.get("recipe") and b.get("website"):
            cand.append(b["website"])
        if not b.get("recipe") and int(b.get("priority") or 0) < 30:
            continue  # directory brokers are classified via WebSearch seeding
        for u in cand[:8]:
            if OK.match(u) and u not in urls:
                urls.append(u)
    return urls


if __name__ == "__main__":
    u = block()
    text = "\n".join(u)
    if "--hash" in sys.argv:
        print(hashlib.sha1(text.encode()).hexdigest()[:10], len(u))
    else:
        print(text)
