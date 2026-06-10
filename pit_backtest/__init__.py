"""Isolated point-in-time (no-look-ahead) backtest harness for the A-share
scoring system.

This package is fully self-contained: it builds its own point-in-time data
(direct tushare ``pro`` API calls with explicit as-of dates + ``f_ann_date``
filtering + qfq adjustment), writes into an isolated PIT sqlite under
``runtime/backtest/``, and then *reuses* the production scoring engine by
**importing** public functions only — it never modifies any ``mvp20/*`` file
and never writes to the live ``runtime/hot.sqlite``.

See ``docs/audit/a_share_pit_backtest_*.md`` for methodology + caveats.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
