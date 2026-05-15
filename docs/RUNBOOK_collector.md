# Collector Daemon Runbook

`scripts/collector.py` pulls 4 data sources (Tushare / FMP / Futu OpenD /
akshare) every 60 s and UPSERTs the rows into `runtime/hot.sqlite`. The
loop must keep running in the background; this runbook covers how to
launch it, keep it alive across crashes / reboots, and what to look at
when it misbehaves.

## When to use which launcher

| Method | Auto-restart on crash | Auto-start on reboot | Setup cost | Use for |
|---|---|---|---|---|
| Manual `nohup` | No | No | None | Ad-hoc dev runs |
| `collector_supervisor.sh` | Yes (5 s backoff) | No | None | Daily dev box (macOS / Linux) |
| `launchd` (macOS) | Yes (rate-limited 60 s) | Yes | One-time `launchctl load` | Always-on macOS workstation |
| `systemd` (Linux) | Yes (`Restart=always`, 10 s) | Yes | One-time `systemctl enable` | Production Linux server |

Rule of thumb: use the supervisor while you're iterating, switch to
`launchd`/`systemd` once the host is stable.

## Method 1 — Manual `nohup` (debug only)

```bash
.venv/bin/python scripts/collector.py --source all --interval 60 \
  > runtime/collector.log 2>&1 &
```

No respawn, no PID tracking. Fine for a quick smoke test, useless for
overnight runs.

## Method 2 — Bash supervisor

```bash
chmod +x scripts/collector_supervisor.sh

scripts/collector_supervisor.sh start            # default: source=all, interval=60
COLLECTOR_SOURCE=tushare scripts/collector_supervisor.sh start
scripts/collector_supervisor.sh status           # RUNNING / STOPPED + ps summary
scripts/collector_supervisor.sh tail 100         # last 100 log lines
scripts/collector_supervisor.sh restart          # stop + start, fresh PID
scripts/collector_supervisor.sh stop             # graceful SIGTERM, falls back to SIGKILL
```

PID lives at `runtime/collector.pid`; log at `runtime/collector.log`.
The supervisor:

- Auto-respawns the python process if it exits non-zero (5 s backoff)
- Treats exit 130 (SIGINT) / 143 (SIGTERM) as clean stop → does not respawn
- Rotates `collector.log` when it exceeds `LOG_ROTATE_SIZE_MB` (default 100 MB),
  keeps 5 archived files

## Method 3 — macOS `launchd`

```bash
# 1. Copy the plist into the user LaunchAgents folder
cp scripts/com.mvp20.collector.plist ~/Library/LaunchAgents/

# 2. Validate
plutil -lint ~/Library/LaunchAgents/com.mvp20.collector.plist

# 3. Load + start
launchctl load -w ~/Library/LaunchAgents/com.mvp20.collector.plist

# 4. Status
launchctl list | grep com.mvp20.collector

# 5. Stop / unload
launchctl unload ~/Library/LaunchAgents/com.mvp20.collector.plist
```

Logs go to `runtime/collector.launchd.log`. `KeepAlive` only respawns
on non-zero exit or crash; `ThrottleInterval=60` prevents tight restart
loops if the binary is misconfigured.

Do **not** run the supervisor and launchd simultaneously — they will
fight for `runtime/hot.sqlite` writes.

## Method 4 — Linux `systemd`

```bash
# 1. Copy the unit
sudo cp scripts/mvp20-collector.service /etc/systemd/system/

# 2. Reload + enable + start
sudo systemctl daemon-reload
sudo systemctl enable mvp20-collector
sudo systemctl start mvp20-collector

# 3. Status / logs
sudo systemctl status mvp20-collector
journalctl -u mvp20-collector -f
```

Adjust `User=` and the absolute paths if you cloned the repo somewhere
other than `/Users/fanjie/Desktop/Cowork/project-ult-mvp20`.

## Health checks

After ~2 cycles (≈ 2 min) you should see new rows in SQLite:

```bash
.venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('runtime/hot.sqlite')
cur = conn.execute('SELECT COUNT(DISTINCT dp_id), COUNT(*) FROM realtime_current')
distinct_dp, total = cur.fetchone()
print(f'distinct dp_id={distinct_dp}  total rows={total}')
cur = conn.execute('SELECT sync_status, ts FROM freshness_meta WHERE layer=\"realtime\" ORDER BY ts DESC LIMIT 1')
print(cur.fetchone())
"
```

`distinct dp_id` should be > 0 and grow as new sources warm up.
`freshness_meta` should report `ok` with a timestamp within the last
two cycles.

Quick log tail:

```bash
scripts/collector_supervisor.sh tail 50
# look for lines like:
#   [collector] tick=42 upserted=210
#   [collector]   tushare: 84 rows
#   [collector]   futu: 31 rows
```

## Troubleshooting

### Collector keeps crashing

- `tail -n 200 runtime/collector.log` — find the python traceback
- If it's a missing token (`TUSHARE_TOKEN`, `FMP_API_KEY`,
  `FUTU_OPEND_PASSWORD`), populate `.env` and restart
- The collector catches **per-source** exceptions; a full crash usually
  means a syntax / import error in adapter code → run
  `.venv/bin/python scripts/collector.py --source all --max-cycles 1`
  in the foreground to see the traceback live

### Quota exhausted (Tushare / FMP / Futu)

- Symptom: log shows `[collector]   tushare: FAILED (...quota...)` but
  the daemon keeps running other sources. That's expected.
- Fix: wait for the daily window to reset, or temporarily switch to
  `COLLECTOR_SOURCE=mock` so the BFF has something to serve.

### `database is locked` (SQLite)

- The most common cause is two collectors writing in parallel (e.g.
  supervisor + launchd both loaded). Run `ps aux | grep collector` and
  kill duplicates.
- Second cause: a long-running analytical query holding the write
  lock — close DB browser / DuckDB sessions that opened
  `runtime/hot.sqlite` in read-write mode.

### `collector.pid` exists but `kill -0` fails

The previous process died without cleanup. `scripts/collector_supervisor.sh
status` will report `STOPPED` and the next `start` will overwrite the
stale PID file. You can also delete it manually.

### Log file grew huge

Rotation happens on `start` (not while running). To force a rotation:

```bash
scripts/collector_supervisor.sh restart
# or manually:
mv runtime/collector.log runtime/collector.log.$(date +%Y%m%d_%H%M%S)
```
