#!/bin/bash
# TeaMgr - Restart uvicorn
# Kills existing process and starts a new one

set -e
cd /app

echo "[restart_web] Stopping uvicorn..."
pkill -f "uvicorn app.main:app" 2>/dev/null && echo "[restart_web] Stopped" || echo "[restart_web] No running process found"
sleep 1

echo "[restart_web] Starting uvicorn..."
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 \
    >> /var/log/uvicorn.log 2>&1 &

sleep 2
if pgrep -f "uvicorn app.main:app" > /dev/null; then
    echo "[restart_web] uvicorn restarted (PID: $(pgrep -f 'uvicorn app.main:app' | head -1))"
else
    echo "[restart_web] ERROR: uvicorn failed to start"
    tail -20 /var/log/uvicorn.log 2>/dev/null
    exit 1
fi
