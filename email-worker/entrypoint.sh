#!/bin/sh
# Wrapper: launches poll as a separate python process each cycle
# Workaround for imaplib hanging when run from container entrypoint

echo "[*] Email worker wrapper started. Polling every ${POLL_INTERVAL:-300}s"
sleep 10

while true; do
    timeout 120 python -u -c "
import socket
socket.setdefaulttimeout(30)
from worker import poll
poll()
" 2>&1
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 124 ]; then
        echo "[!] Poll timed out (120s)"
    fi
    sleep ${POLL_INTERVAL:-300}
done
