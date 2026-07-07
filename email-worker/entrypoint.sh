#!/bin/sh
# Wrapper that launches poll as a fresh process each cycle
# This works around an issue where imaplib hangs when run as PID 1 entrypoint

echo "[*] Email worker wrapper started. Polling every ${POLL_INTERVAL:-300}s"
sleep 10

while true; do
    python -u -c "from worker import poll; poll()" 2>&1
    sleep ${POLL_INTERVAL:-300}
done
