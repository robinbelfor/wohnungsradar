#!/bin/bash
# Veröffentlicht die aktuellen Wohnungsdaten im Zweig "data" von robinbelfor/wohnungsradar.
# Läuft in der Cloud-Arbeitsumgebung (dort ist GitHub erreichbar), NICHT in der Geräte-Shell.
#   bash publish_web.sh <pfad zu listings.js (gestaged vom Mac)> <RUN_ID>
set -euo pipefail
SRC="$1"; RUN="$2"; REPO=/home/claude/wohnungsradar-data
if [ ! -d "$REPO/.git" ]; then
  git clone -q --depth 1 --branch data https://github.com/robinbelfor/wohnungsradar "$REPO"
fi
cd "$REPO"
git fetch -q --depth 1 origin data && git reset -q --hard origin/data
python3 - "$SRC" <<'PY'
import json, sys
s = open(sys.argv[1], encoding="utf-8").read()
d = json.loads(s[s.index("=") + 1:].strip().rstrip(";"))
json.dump(d, open("listings.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print("listings:", len(d["listings"]), "stand:", d.get("generated_at"))
PY
if git diff --quiet; then echo "keine Änderung"; exit 0; fi
git add listings.json
git commit -q -m "Daten: Scan $RUN

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012Lkw7DAPbPfRcuJjQYQqUz"
git push -q origin data && echo "veröffentlicht"
