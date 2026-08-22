#!/bin/zsh
# EST-120: probe the subscription every 10 min; when the individual spend limit
# lifts, finish the v1 medium rerun (resumable — skips blobs already on disk)
# and score it. Medium only: the v1 comparison is medium-to-medium.
cd /Users/esteban/repos/sideword
LOG=corpus/convert-pilot/run-v1.log
# Which account to bill. Without this the CLI falls back to ~/.claude, which is
# a different (exhausted) account than the one this batch is meant to run on.
export SIDEWORD_CLAUDE_CONFIG_DIR=$HOME/.claude2
while true; do
  out=$(printf 'say hi\n' | env -i HOME=$HOME PATH=/usr/bin:/bin:/Users/esteban/.nvm/versions/node/v20.19.5/bin USER=$USER TERM=dumb \
        CLAUDE_CONFIG_DIR=$SIDEWORD_CLAUDE_CONFIG_DIR \
        claude -p --model claude-opus-5 --effort low --system-prompt "Answer with one word." --no-session-persistence --output-format json --tools "" 2>/dev/null)
  if echo "$out" | grep -q '"is_error":false'; then
    echo "[$(date +%H:%M:%S)] probe ok — resuming v1 medium batch" >> $LOG
    .venv/bin/python harness/convert_pilot.py run --effort medium --jobs 4 >> $LOG 2>&1
    rc=$?
    echo "[$(date +%H:%M:%S)] batch exited rc=$rc" >> $LOG
    if [ $rc -eq 0 ]; then
      .venv/bin/python harness/convert_pilot.py score >> $LOG 2>&1
      echo "[$(date +%H:%M:%S)] V1 MEDIUM COMPLETE AND SCORED" >> $LOG
      exit 0
    fi
  else
    echo "[$(date +%H:%M:%S)] probe blocked" >> $LOG
  fi
  sleep 600
done
