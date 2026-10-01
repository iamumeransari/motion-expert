#!/usr/bin/env bash
# Scaffold a new style skill from the template and register it.
# Usage: toolkit/new-style.sh <slug> <source-url>
set -euo pipefail
slug="$1"; url="$2"; root="$(cd "$(dirname "$0")/.." && pwd)"
dest="$root/skills/$slug-motion"
[ -e "$dest" ] && { echo "exists: $dest" >&2; exit 1; }
cp -R "$root/skills/motion-expert/_template" "$dest"
mv "$dest/SKILL.md.tmpl" "$dest/SKILL.md"
today="$(date +%Y-%m-%d)"
grep -rl '{{slug}}' "$dest" | xargs sed -i '' "s|{{slug}}|$slug|g"
grep -rl '{{source_url}}\|{{url}}' "$dest" | xargs sed -i '' -e "s|{{source_url}}|$url|g" -e "s|{{url}}|$url|g"
grep -rl '{{date}}' "$dest" | xargs sed -i '' "s|{{date}}|$today|g"
python3 - "$root/registry.json" "$slug" "$url" "$today" <<'PY'
import json,sys
p,slug,url,d=sys.argv[1:]
r=json.load(open(p))
r["styles"].append({"slug":slug,"skill":f"skills/{slug}-motion","source":url,"captured":d,"status":"capturing","fingerprint":f"skills/{slug}-motion/fingerprint.json"})
json.dump(r,open(p,"w"),indent=2)
PY
ln -sfn "$dest" "$HOME/.claude/skills/$slug-motion"
echo "$dest"
