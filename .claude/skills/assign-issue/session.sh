#!/usr/bin/env bash
# Print "<sessionId>\t<aiTitle>" for a conversation in this repo.
# Usage: session.sh [sessionId]
# With no argument, falls back to the most recently modified transcript.
set -euo pipefail

PROJECT_ROOT="/Users/esteban/repos/sideword"
CFG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
DIR="$CFG/projects/$(printf '%s' "$PROJECT_ROOT" | tr '/' '-')"

if [ "$#" -ge 1 ] && [ -n "$1" ]; then
  FILE="$DIR/$1.jsonl"
else
  FILE=$(ls -t "$DIR"/*.jsonl 2>/dev/null | head -1 || true)
fi

if [ -z "${FILE:-}" ] || [ ! -f "$FILE" ]; then
  echo "assign-issue: no transcript found in $DIR" >&2
  exit 1
fi

python3 - "$FILE" <<'PY'
import json, os, sys

path = sys.argv[1]
title = ""
with open(path) as fh:
    for line in fh:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        # The last ai-title entry wins; earlier ones are superseded renames.
        if entry.get("type") == "ai-title" and entry.get("aiTitle"):
            title = entry["aiTitle"]

print(os.path.basename(path)[:-len(".jsonl")] + "\t" + title)
PY
