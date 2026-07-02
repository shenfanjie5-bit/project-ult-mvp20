"""Freshness gate in ``scripts/run_eod_refresh.py`` (review finding #4).

A collect-core failure must SKIP the whole derive/score chain instead of
baking a stale daily_basic/moneyflow cross-section into L11 and the signal
artifacts, while a collect-full failure alone stays soft (collect-core
re-fetches the cross-section by design).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_eod_refresh as eod  # noqa: E402


def _fake_run_factory(calls: list[str], fail_steps: set[str]):
    def _fake_run(label: str, args: list[str], timeout_s: int) -> dict:
        calls.append(label)
        ok = label not in fail_steps
        return {"step": label, "ok": ok, "rc": 0 if ok else 1,
                "elapsed_s": 0.0, "tail": []}
    return _fake_run


def test_core_failure_skips_derive_chain(monkeypatch, capsys) -> None:
    calls: list[str] = []
    monkeypatch.setattr(eod, "_run", _fake_run_factory(calls, {"collect-core"}))
    monkeypatch.setattr(
        eod, "_run_derive_inprocess",
        lambda: (_ for _ in ()).throw(AssertionError("derive must not run when the gate fails")),
    )

    rc = eod.main()

    assert rc == 1
    # Only the three collectors actually ran.
    assert calls == ["collect-full", "collect-core", "collect-macro"]
    out = capsys.readouterr().out
    assert '"skipped": true' in out
    assert "gate: collect-core failed" in out
    # Every derive-chain step is present as an explicitly skipped record.
    for label in ("derive", "derive-snapshot", "compile-overlays",
                  "build-peer-context", "build-quant-scores",
                  "build-signal-5d", "build-signal-up-5d"):
        assert f'"step": "{label}"' in out


def test_full_collector_failure_alone_does_not_gate(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(eod, "_run", _fake_run_factory(calls, {"collect-full"}))
    monkeypatch.setattr(
        eod, "_run_derive_inprocess",
        lambda: (calls.append("derive") or {"step": "derive", "ok": True, "rc": 0, "elapsed_s": 0.0}),
    )

    rc = eod.main()

    # collect-full failing alone is the designed-tolerated case: the chain
    # still runs (exit code stays 1 so ops sees the failed step).
    assert rc == 1
    assert "derive" in calls
    assert calls[-1] == "build-signal-up-5d"


def test_all_green_runs_everything_in_order(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(eod, "_run", _fake_run_factory(calls, set()))
    monkeypatch.setattr(
        eod, "_run_derive_inprocess",
        lambda: (calls.append("derive") or {"step": "derive", "ok": True, "rc": 0, "elapsed_s": 0.0}),
    )

    rc = eod.main()

    assert rc == 0
    assert calls == [
        "collect-full", "collect-core", "collect-macro", "derive",
        "derive-snapshot", "compile-overlays", "build-peer-context",
        "build-quant-scores", "build-signal-5d", "build-signal-up-5d",
    ]
