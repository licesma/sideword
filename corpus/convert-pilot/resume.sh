#!/bin/zsh
# Probe the subscription every 10 min; when the spend-limit block lifts, resume the batch (resumable, skips done blobs).
cd /Users/esteban/repos/sideword
LOG=corpus/convert-pilot/run.log
while true; do
  out=$(printf 'say hi\n' | env -i HOME=$HOME PATH=/usr/bin:/bin:/Users/esteban/.nvm/versions/node/v20.19.5/bin USER=$USER TERM=dumb \
        claude -p --model claude-opus-5 --effort low --system-prompt "Answer with one word." --no-session-persistence --output-format json --tools "" 2>/dev/null)
  if echo "$out" | grep -q '"is_error":false'; then
    echo "[$(date +%H:%M:%S)] probe ok — resuming batch" >> $LOG
    .venv/bin/python harness/convert_pilot.py run --jobs 4 >> $LOG 2>&1
    rc=$?
    echo "[$(date +%H:%M:%S)] batch exited rc=$rc" >> $LOG
    if [ $rc -eq 0 ]; then
      .venv/bin/python harness/convert_pilot.py score >> $LOG 2>&1
      echo "[$(date +%H:%M:%S)] BATCH COMPLETE AND SCORED" >> $LOG
      exit 0
    fi
  else
    echo "[$(date +%H:%M:%S)] probe blocked: $(echo "$out" | grep -o '"result":"[^"]*"' | head -c 120)" >> $LOG
  fi
  sleep 600
done
