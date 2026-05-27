"""Unit tests for the deterministic debate-loop stopping logic (convergence.py).

Pure functions, no LLM — these encode the behavior table from the plan.
Run: .venv/bin/python -m pytest tests/test_convergence.py -q
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from convergence import (  # noqa: E402
    trades_equivalent,
    whatif_settled,
    has_converged,
)


def _iter(pm_trades, *, valid=True, whatif_trades=None):
    """Build one iteration-history dict."""
    return {
        "pm_proposal": {"proposed_trades": pm_trades},
        "monitor_check": {"is_valid": valid},
        "what_if_critique": {
            "alternative_scenario": {"proposed_trades": whatif_trades or []}
        },
    }


BUY_NVDA = [{"action": "buy", "ticker": "NVDA", "shares": 100}]


# ── trades_equivalent ───────────────────────────────────────────────────────

def test_equivalent_identical():
    assert trades_equivalent(BUY_NVDA, BUY_NVDA)


def test_equivalent_within_tolerance():
    # 100 vs 101 shares = 1% < 2% tolerance
    assert trades_equivalent(
        [{"action": "buy", "ticker": "NVDA", "shares": 100}],
        [{"action": "buy", "ticker": "NVDA", "shares": 101}],
    )


def test_not_equivalent_beyond_tolerance():
    assert not trades_equivalent(
        [{"action": "buy", "ticker": "NVDA", "shares": 100}],
        [{"action": "buy", "ticker": "NVDA", "shares": 130}],
    )


def test_not_equivalent_different_ticker():
    assert not trades_equivalent(
        BUY_NVDA, [{"action": "buy", "ticker": "AAPL", "shares": 100}]
    )


def test_empty_equivalent_empty():
    assert trades_equivalent([], [])
    assert trades_equivalent(None, [])


def test_order_insensitive():
    a = [{"action": "buy", "ticker": "NVDA", "shares": 10},
         {"action": "buy", "ticker": "AAPL", "shares": 5}]
    b = list(reversed(a))
    assert trades_equivalent(a, b)


# ── has_converged: the behavior table ───────────────────────────────────────

def test_strong_consensus_stops_early():
    # same proposal, valid, what-if accepts → converges at the patience window
    hist = [_iter(BUY_NVDA) for _ in range(3)]
    assert has_converged(hist)


def test_below_min_iterations_does_not_stop():
    assert not has_converged([_iter(BUY_NVDA)])  # only 1 round


def test_oscillation_never_converges():
    a = BUY_NVDA
    b = [{"action": "buy", "ticker": "AAPL", "shares": 50}]
    hist = [_iter(a), _iter(b), _iter(a), _iter(b)]
    assert not has_converged(hist)


def test_monitor_violation_blocks_stop():
    hist = [_iter(BUY_NVDA), _iter(BUY_NVDA), _iter(BUY_NVDA, valid=False)]
    assert not has_converged(hist)


def test_empty_trades_stable_stops():
    # PM proposes nothing repeatedly, monitor valid → stop, don't burn rounds
    hist = [_iter([]) for _ in range(3)]
    assert has_converged(hist)


def test_new_whatif_critique_blocks_stop():
    # stable PM + valid, but the latest what-if raises a *new* alternative
    hist = [
        _iter(BUY_NVDA),
        _iter(BUY_NVDA),
        _iter(BUY_NVDA, whatif_trades=[{"action": "sell", "ticker": "NVDA", "shares": 40}]),
    ]
    assert not has_converged(hist)


def test_repeated_whatif_alternative_is_settled():
    # same standing disagreement repeated → settled → stop (orchestrator decides)
    alt = [{"action": "sell", "ticker": "NVDA", "shares": 40}]
    hist = [
        _iter(BUY_NVDA, whatif_trades=alt),
        _iter(BUY_NVDA, whatif_trades=alt),
        _iter(BUY_NVDA, whatif_trades=alt),
    ]
    assert whatif_settled(hist[-2:])
    assert has_converged(hist)


def test_patience_requires_consecutive_stability():
    # A change inside the patience+1 window blocks convergence...
    other = [{"action": "buy", "ticker": "AAPL", "shares": 50}]
    hist = [_iter(other), _iter(BUY_NVDA), _iter(BUY_NVDA)]
    assert not has_converged(hist)  # window [other, nvda, nvda] not all-stable
    # ...one more stable round makes the window [nvda, nvda, nvda] -> converged
    hist.append(_iter(BUY_NVDA))
    assert has_converged(hist)
