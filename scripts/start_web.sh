#!/bin/bash
# TeaMgr - Start uvicorn
# Safe to call repeatedly: kills previous process before starting a new one

set -e
cd /app

echo "[start_web] Checking for existing uvicorn process..."
pkill -f "uvicorn app.main:app" 2>/dev/null && echo "[start_web] Stopped previous process" || true
sleep 1

echo "[start_web] Starting uvicorn..."
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 \
    >> /var/log/uvicorn.log 2>&1 &

sleep 2
if pgrep -f "uvicorn app.main:app" > /dev/null; then
    echo "[start_web] uvicorn started (PID: $(pgrep -f 'uvicorn app.main:app' | head -1))"
    echo "[start_web] Log: docker-compose -f docker/docker-compose.yml exec teamgr tail -f /var/log/uvicorn.log"
else
    echo "[start_web] ERROR: uvicorn failed to start, check /var/log/uvicorn.log"
    tail -20 /var/log/uvicorn.log 2>/dev/null
    exit 1
fi
