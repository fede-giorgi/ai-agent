"""Walk-forward (no-refit) backtesting harness for the Agentic AI Hedge Fund.

Subpackage layout:
    config.py         — window/universe/cache/concurrency settings
    data_cache.py     — PiTDataCache: download the full window once, persist, serve raw
    as_of_provider.py — AsOfProvider: cutoff-masked, tool-shaped views (no look-ahead)
    tool_injection.py — install_cache(): swap the live tools for the cache during a run

Phases 2/3 add: calendar, execution, benchmarks, metrics, skip_gate, walk_forward, run_backtest.
"""
