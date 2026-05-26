"""Offline tests for the walk-forward harness core: calendar, metrics, execution,
benchmarks, skip-gate. Synthetic price cache, no network, no LLM.

Run: .venv/bin/python -m pytest tests/test_harness.py -q
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtesting.data_cache import PiTDataCache  # noqa: E402
from backtesting.calendar import TradingCalendar  # noqa: E402
from backtesting import metrics, benchmarks  # noqa: E402
from backtesting.execution import ExecutionEngine  # noqa: E402
from backtesting.skip_gate import SkipGate, build_snapshot  # noqa: E402

SESSIONS = ["2026-01-05", "2026-01-06", "2026-01-07"]


def _px(rows):
    return {"prices": [{"time": t, "open": o, "close": c} for t, o, c in rows]}


def _cache():
    store = {
        "AAPL": {"prices": _px([("2026-01-05", 100, 100), ("2026-01-06", 110, 110), ("2026-01-07", 121, 121)]),
                 "insider": {"insider_trades": []}, "news": {"news": []},
                 "financials": {"income_statements": []}},
        "MSFT": {"prices": _px([("2026-01-05", 200, 200), ("2026-01-06", 200, 200), ("2026-01-07", 200, 200)]),
                 "insider": {"insider_trades": []}, "news": {"news": []},
                 "financials": {"income_statements": []}},
        "SPY": {"prices": _px([("2026-01-05", 400, 400), ("2026-01-06", 404, 404), ("2026-01-07", 408.04, 408.04)])},
    }
    return PiTDataCache.from_store(store, ["AAPL", "MSFT"], "2026-01-05", "2026-01-07")


# ── calendar ─────────────────────────────────────────────────────────────────

def test_calendar_sessions_and_nav():
    cal = TradingCalendar(_cache())
    assert cal.sessions("2026-01-05", "2026-01-07") == SESSIONS
    assert cal.next_session("2026-01-05") == "2026-01-06"
    assert cal.prev_session("2026-01-07") == "2026-01-06"
    assert cal.next_session("2026-01-07") is None
    assert cal.is_session("2026-01-06") and not cal.is_session("2026-01-04")


# ── metrics ──────────────────────────────────────────────────────────────────

def test_total_return_and_drawdown():
    curve = [("d1", 100.0), ("d2", 110.0), ("d3", 121.0)]
    assert abs(metrics.total_return(curve) - 0.21) < 1e-9
    dd = [("d1", 100.0), ("d2", 80.0), ("d3", 90.0)]
    assert abs(metrics.max_drawdown(dd) - (-0.2)) < 1e-9


def test_summarize_beats_flat_benchmark():
    agent = [("d1", 100.0), ("d2", 110.0), ("d3", 121.0)]
    flat = [("d1", 100.0), ("d2", 100.0), ("d3", 100.0)]
    s = metrics.summarize(agent, {"flat": flat})
    assert s["n_beaten"] == 1 and "flat" in s["beaten"]
    assert s["benchmarks"]["flat"]["alpha"] > 0


# ── execution ────────────────────────────────────────────────────────────────

def test_buy_clamps_to_affordable_whole_shares_next_open():
    cache = _cache()
    eng = ExecutionEngine(cache, TradingCalendar(cache), fill_timing="next_open")
    # decision on 01-05 → fills at next open (01-06) = 110
    pf, cash, fills = eng.apply([{"action": "buy", "ticker": "AAPL", "shares": 100}], {}, 1050.0, "2026-01-05")
    assert fills[0]["fill_price"] == 110.0
    assert pf["AAPL"] == 9 and cash >= 0 and abs(cash - 60.0) < 1e-9


def test_sell_clamped_to_holdings_no_negative():
    cache = _cache()
    eng = ExecutionEngine(cache, TradingCalendar(cache), fill_timing="close")
    pf, cash, _ = eng.apply([{"action": "sell", "ticker": "AAPL", "shares": 50}], {"AAPL": 3}, 0.0, "2026-01-05")
    assert "AAPL" not in pf and cash == 300.0  # sold only the 3 held @ close 100


def test_mark_to_market():
    cache = _cache()
    eng = ExecutionEngine(cache, TradingCalendar(cache))
    assert eng.mark_to_market({"AAPL": 10}, 100.0, "2026-01-07") == 10 * 121 + 100


# ── benchmarks ───────────────────────────────────────────────────────────────

def test_equal_weight_buy_and_hold():
    cache = _cache()
    curves = benchmarks.build_benchmarks(cache, ["AAPL", "MSFT"], SESSIONS, capital=1000.0)
    ew = curves["1/N Equal-Weight"]
    assert ew[0][1] == 1000.0                      # day 0 = capital
    assert abs(ew[-1][1] - 1105.0) < 1e-9          # 5·121 + 2·200 + 100 leftover
    assert "Risk-Free" in curves and "S&P 500 (SPY)" in curves


def test_buy_and_hold_loop_consistency():
    """A 'buy day0 and hold' execution must reproduce the single-name buy-and-hold curve."""
    cache = _cache()
    cal = TradingCalendar(cache)
    eng = ExecutionEngine(cache, cal, fill_timing="close")  # buy at day-0 close, like the benchmark
    pf, cash, _ = eng.apply([{"action": "buy", "ticker": "AAPL", "shares": 10}], {}, 1000.0, SESSIONS[0])
    agent_curve = [(d, eng.mark_to_market(pf, cash, d)) for d in SESSIONS]
    bh = benchmarks._buy_and_hold(cache, ["AAPL"], SESSIONS, 1000.0, fractional=False)
    assert agent_curve == bh


# ── skip gate ────────────────────────────────────────────────────────────────

def test_gate_first_day_then_no_trigger():
    cache = _cache()
    gate = SkipGate()
    run, reason = gate.should_run("2026-01-05", None, cache, ["MSFT"])
    assert run and reason == "first_day"
    snap = build_snapshot("2026-01-05", cache, ["MSFT"])
    run, reason = gate.should_run("2026-01-06", snap, cache, ["MSFT"])  # MSFT flat
    assert not run and reason == "no_trigger"


def test_gate_triggers_on_price_move():
    cache = _cache()
    gate = SkipGate()
    snap = build_snapshot("2026-01-05", cache, ["AAPL"])
    run, reason = gate.should_run("2026-01-06", snap, cache, ["AAPL"])  # AAPL +10%
    assert run and reason == "price_move:AAPL"


def test_gate_cadence_forces_run():
    cache = _cache()
    gate = SkipGate()
    snap = build_snapshot("2026-01-05", cache, ["MSFT"])
    run, reason = gate.should_run("2026-01-15", snap, cache, ["MSFT"])  # 10 days later
    assert run and reason == "cadence"


# ── full harness loop (stubbed decision fn — no LLM/network) ──────────────────

def test_walk_forward_loop_with_stub_decision(monkeypatch):
    import backtesting.walk_forward as wf

    calls = {"n": 0}

    def stub_run_one_day(cutoff, universe, portfolio, cash, risk, cache, *, max_iterations, log):
        calls["n"] += 1
        trades = [{"action": "buy", "ticker": "AAPL", "shares": 5}] if calls["n"] == 1 else []
        return {"final_trades": trades, "price_map": {}, "signals": {}, "iterations": 2}

    monkeypatch.setattr(wf, "run_one_day", stub_run_one_day)
    harness = wf.WalkForwardHarness(["AAPL", "MSFT"], "2026-01-05", "2026-01-07",
                                    capital=1000.0, cache=_cache(), log=lambda *a, **k: None)
    report = harness.run()

    assert len(report.day_results) == 3
    assert report.day_results[0].ran_pipeline and report.day_results[0].reason == "first_day"
    assert report.day_results[-1].portfolio.get("AAPL") == 5      # bought once, held
    assert report.metrics["n_benchmarks"] == 3
    assert report.metrics["agent"]["final_equity"] > 0
