"""Server-Sent Events helpers used by ``mvp20.server``.

Implements two stream endpoints:
- ``/api/project-ult/stream/realtime?ts_code=X`` —— periodic delta of
  ``realtime_current`` rows that changed for one ts_code; emits an SSE
  ``message`` event roughly every ``poll_interval_seconds`` seconds. Returns
  empty ``{}`` events as heartbeats so the client knows we're still up.

SSE protocol notes:
- Frames are ``"data: <json>\\n\\n"`` (two newlines terminate the event).
- We send a leading ``"retry: 5000\\n\\n"`` so the EventSource auto-reconnects
  after 5s if the connection drops.
- The server keeps the response open and ``flush()`` after every event.
- This blocks the calling thread for the duration of the stream — fine on
  ``ThreadingHTTPServer`` but the operator should cap concurrent SSE clients
  (no enforcement here; honour-system in phase 1).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from mvp20.json_utils import dumps_strict_json

# Conservative defaults; can be overridden per-request later via query string.
DEFAULT_POLL_INTERVAL_SECONDS = 5
DEFAULT_MAX_DURATION_SECONDS = 30 * 60   # auto-close after 30 min, client will reconnect
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30  # send empty event if no changes for this long


def write_event(write_bytes: Callable[[bytes], int], flush: Callable[[], None],
                data: dict, event: str | None = None) -> bool:
    """Write a single SSE event. Returns False if the client has disconnected
    (i.e. write_bytes raised), True otherwise."""

    parts: list[str] = []
    if event is not None:
        parts.append(f"event: {event}\n")
    payload = dumps_strict_json(data)
    # SSE: each line of data must be prefixed; we keep payload single-line.
    parts.append(f"data: {payload}\n\n")
    try:
        write_bytes("".join(parts).encode("utf-8"))
        flush()
        return True
    except (BrokenPipeError, ConnectionResetError, OSError):
        return False


def write_retry_hint(write_bytes: Callable[[bytes], int], flush: Callable[[], None],
                     retry_ms: int = 5000) -> bool:
    try:
        write_bytes(f"retry: {retry_ms}\n\n".encode("utf-8"))
        flush()
        return True
    except (BrokenPipeError, ConnectionResetError, OSError):
        return False


def stream_realtime_delta(
    write_bytes: Callable[[bytes], int],
    flush: Callable[[], None],
    hot_db_path: Path,
    ts_code: str,
    industry_id: str | None = None,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    max_duration_seconds: int = DEFAULT_MAX_DURATION_SECONDS,
    heartbeat_interval_seconds: int = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
) -> None:
    """Long-lived SSE loop: every ``poll_interval_seconds`` query the hot
    snapshot for rows changed since the last cycle, emit them as one event.

    Exits when:
    - the client disconnects (write fails)
    - ``max_duration_seconds`` elapsed (client will EventSource-reconnect)
    """

    # Late import: server.py reads this file as well; avoid circular import.
    from mvp20.storage import read_hot_snapshot, read_hot_snapshot_changed_since

    write_retry_hint(write_bytes, flush)

    # Send a full snapshot once at start so the UI doesn't have to wait for
    # the first delta tick (which can be up to poll_interval_seconds).
    initial = read_hot_snapshot(hot_db_path, ts_code)
    if not write_event(write_bytes, flush,
                       {"ts_code": ts_code, "industry_id": industry_id,
                        "kind": "snapshot", "values": initial}):
        return

    started_at = time.time()
    last_check = int(time.time())
    last_event_at = time.time()

    while True:
        if time.time() - started_at > max_duration_seconds:
            write_event(write_bytes, flush,
                        {"ts_code": ts_code, "industry_id": industry_id, "kind": "close",
                         "reason": "max_duration_reached"})
            return

        time.sleep(poll_interval_seconds)
        now = int(time.time())

        delta = read_hot_snapshot_changed_since(hot_db_path, ts_code, last_check)
        last_check = now

        if delta:
            ok = write_event(write_bytes, flush,
                             {"ts_code": ts_code, "industry_id": industry_id, "kind": "delta",
                              "values": delta, "at": now})
            if not ok:
                return
            last_event_at = time.time()
        elif time.time() - last_event_at > heartbeat_interval_seconds:
            ok = write_event(write_bytes, flush,
                             {"ts_code": ts_code, "industry_id": industry_id,
                              "kind": "heartbeat", "at": now})
            if not ok:
                return
            last_event_at = time.time()
