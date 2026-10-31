#!/usr/bin/env python3
"""Builds the scheduled task's prompt: agents/trigger-template.md + the current block of entry URLs.
   python3 tools/trigger_prompt.py          -> prompt text
   python3 tools/trigger_prompt.py --hash   -> hash of the URL block (compare with 'Stand' in the prompt)"""
import hashlib, json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from urlblock import block
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
urls = block()
h = hashlib.sha1("\n".join(urls).encode()).hexdigest()[:10]
if "--hash" in sys.argv:
    print(h); sys.exit(0)
cfg = json.load(open(os.path.join(ROOT, "config", "abgleich.json"), encoding="utf-8"))
t = open(os.path.join(ROOT, "agents", "trigger-template.md"), encoding="utf-8").read()
print(t.replace("{HASH}", h).replace("{URLS}", "\n".join(urls)).replace("{TRIGGER_ID}", cfg.get("trigger_id", "?")))
