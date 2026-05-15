#!/usr/bin/env bash
# Collector daemon supervisor — start/stop/restart/status/tail
# Self-respawning: writes PID file, on SIGTERM kills child + cleans up.
#
# Usage:
#   scripts/collector_supervisor.sh start [--source all] [--interval 60]
#   scripts/collector_supervisor.sh stop
#   scripts/collector_supervisor.sh restart
#   scripts/collector_supervisor.sh status
#   scripts/collector_supervisor.sh tail [N]   # last N log lines
#
# Environment overrides:
#   COLLECTOR_SOURCE   (default: all)
#   COLLECTOR_INTERVAL (default: 60)
#   LOG_ROTATE_SIZE_MB (default: 100)

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PID_FILE="runtime/collector.pid"
LOG_FILE="runtime/collector.log"
LOG_ROTATE_SIZE_MB="${LOG_ROTATE_SIZE_MB:-100}"
SOURCE="${COLLECTOR_SOURCE:-all}"
INTERVAL="${COLLECTOR_INTERVAL:-60}"

mkdir -p runtime

is_running() {
    [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

rotate_log_if_too_big() {
    if [ -f "$LOG_FILE" ]; then
        size_mb=$(du -m "$LOG_FILE" | cut -f1)
        if [ "$size_mb" -gt "$LOG_ROTATE_SIZE_MB" ]; then
            mv "$LOG_FILE" "${LOG_FILE}.$(date +%Y%m%d_%H%M%S)"
            # Keep at most 5 rotated archives
            ls -1t "${LOG_FILE}".* 2>/dev/null | tail -n +6 | xargs -I{} rm -f {}
        fi
    fi
}

start_collector() {
    if is_running; then
        echo "collector already running (pid=$(cat "$PID_FILE"))"
        return 0
    fi
    rotate_log_if_too_big
    # Use a respawn loop so accidental crashes auto-recover.
    # The outer bash gets a PID via $!; on SIGTERM it kills its child python
    # and we then break out of the loop.
    nohup bash -c "
        cd '$ROOT'
        trap 'echo \"[supervisor] received SIGTERM @ \$(date)\" >> \"$LOG_FILE\"; kill -TERM \$child 2>/dev/null; wait \$child 2>/dev/null; exit 143' TERM INT
        while true; do
            echo '[supervisor] starting collector @ '\$(date) >> '$LOG_FILE'
            .venv/bin/python scripts/collector.py --source $SOURCE --interval $INTERVAL >> '$LOG_FILE' 2>&1 &
            child=\$!
            wait \$child
            EXIT_CODE=\$?
            echo '[supervisor] collector exited with code='\$EXIT_CODE' @ '\$(date) >> '$LOG_FILE'
            if [ \$EXIT_CODE -eq 130 ] || [ \$EXIT_CODE -eq 143 ]; then
                # SIGINT / SIGTERM — clean stop
                echo '[supervisor] clean stop' >> '$LOG_FILE'
                break
            fi
            sleep 5
        done
    " >/dev/null 2>&1 &
    echo $! > "$PID_FILE"
    sleep 1
    if is_running; then
        echo "collector started (supervisor pid=$(cat "$PID_FILE"), source=$SOURCE, interval=${INTERVAL}s)"
        echo "  log: $LOG_FILE"
    else
        echo "ERROR: collector failed to start (check $LOG_FILE)"
        rm -f "$PID_FILE"
        return 1
    fi
}

stop_collector() {
    if ! is_running; then
        echo "collector not running"
        rm -f "$PID_FILE"
        return 0
    fi
    sup_pid="$(cat "$PID_FILE")"
    # Kill children first (python collector), then supervisor.
    pkill -P "$sup_pid" 2>/dev/null || true
    kill -TERM "$sup_pid" 2>/dev/null || true
    for i in {1..20}; do
        if ! is_running; then break; fi
        sleep 0.5
    done
    if is_running; then
        # Force-kill leftover supervisor + its children.
        pkill -KILL -P "$sup_pid" 2>/dev/null || true
        kill -KILL "$sup_pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
    echo "collector stopped"
}

case "${1:-}" in
    start)   start_collector ;;
    stop)    stop_collector ;;
    restart) stop_collector; sleep 1; start_collector ;;
    status)
        if is_running; then
            echo "RUNNING (pid=$(cat "$PID_FILE"))"
            ps aux | grep -E "(scripts/collector\.py|collector_supervisor)" | grep -v grep | head -5
        else
            echo "STOPPED"
        fi
        ;;
    tail)
        N="${2:-50}"
        tail -n "$N" "$LOG_FILE" 2>/dev/null || echo "no log yet"
        ;;
    *)
        echo "usage: $0 {start|stop|restart|status|tail [N]}"
        exit 1
        ;;
esac
