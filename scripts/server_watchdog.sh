#!/usr/bin/env bash
# mvp20 backend watchdog — cron-driven, session-independent.
#
# Probes /api/health (3s budget). On connection failure OR wedge (the known
# listen-but-not-accepting state), force-kills any leftover serve process and
# starts a fresh one fully detached (setsid-like via nohup + new process group)
# so it never dies with a terminal/session.
#
# Cron: */5 * * * * /Users/fanjie/Desktop/Cowork/project-ult-mvp20/scripts/server_watchdog.sh >> /Users/fanjie/Desktop/Cowork/project-ult-mvp20/runtime/watchdog.log 2>&1

set -u
ROOT="/Users/fanjie/Desktop/Cowork/project-ult-mvp20"
cd "$ROOT"

ts() { date "+%Y-%m-%d %H:%M:%S"; }

# healthy? (connect + respond within 3s)
if curl -s -m 3 -o /dev/null -w "%{http_code}" "http://127.0.0.1:8701/api/health" | grep -q "200"; then
    exit 0
fi

echo "[$(ts)] health probe FAILED — restarting backend"
pkill -9 -f "mvp20.cli serve" 2>/dev/null
sleep 1
# port must be free before restart (wedged sockets linger otherwise)
if lsof -i :8701 2>/dev/null | grep -q LISTEN; then
    echo "[$(ts)] port 8701 still held after kill — aborting this round"
    exit 1
fi
nohup "$ROOT/.venv/bin/python" -u -m mvp20.cli serve \
    >> "$ROOT/runtime/serve.log" 2>&1 < /dev/null &
disown
sleep 4
if curl -s -m 3 -o /dev/null -w "%{http_code}" "http://127.0.0.1:8701/api/health" | grep -q "200"; then
    echo "[$(ts)] backend restarted OK (pid $(pgrep -f 'mvp20.cli serve' | head -1))"
else
    echo "[$(ts)] restart FAILED — see runtime/serve.log"
fi
