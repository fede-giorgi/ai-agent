"""Deterministic convergence detection for the trading debate loop.

Replaces the old fixed-iteration loop with early stopping. The debate is a search
for a fixed point: stop when the Portfolio Manager's proposed trades have been
stable for ``STABILITY_PATIENCE`` consecutive rounds, the Monitor reports no
violations, and the What-If challenge is settled (accepted or a repeated standing
disagreement). These are *pure functions* over the structured outputs the loop
already produces — no extra LLM call — so the stop decision is reproducible and
unit-testable. See also ``config.py`` for the tunable thresholds.
"""

from __future__ import annotations

from typing import Any

from config import (
    MIN_ITERATIONS,
    STABILITY_PATIENCE,
    SHARE_STABILITY_TOLERANCE,
)


def _trade_map(trades: list[dict] | None) -> dict[tuple[str, str], float]:
    """Collapse a proposed-trades list into ``{(ticker, action): total_shares}``."""
    m: dict[tuple[str, str], float] = {}
    for t in trades or []:
        if not isinstance(t, dict):
            continue
        key = (str(t.get("ticker", "")).upper(), str(t.get("action", "")).lower())
        try:
            shares = float(t.get("shares", 0) or 0)
        except (TypeError, ValueError):
            shares = 0.0
        m[key] = m.get(key, 0.0) + shares
    return m


def trades_equivalent(
    a: list[dict] | None,
    b: list[dict] | None,
    tol: float = SHARE_STABILITY_TOLERANCE,
) -> bool:
    """True if two proposals trade the same tickers/actions with share counts
    within a relative tolerance ``tol`` (default ±2%). Empty vs empty is equivalent."""
    ma, mb = _trade_map(a), _trade_map(b)
    if set(ma) != set(mb):
        return False
    for key, sa in ma.items():
        sb = mb[key]
        if abs(sa - sb) > tol * max(sa, sb, 1.0):
            return False
    return True


def whatif_settled(window: list[dict]) -> bool:
    """The What-If challenge is "settled" when the latest critique either proposes
    no alternative (accepted) or repeats the same alternative as the prior round
    (a standing disagreement the Final Orchestrator will adjudicate)."""
    if not window:
        return True
    last = window[-1].get("what_if_critique") or {}
    alt = last.get("alternative_scenario") or {}
    alt_trades = alt.get("proposed_trades", []) if isinstance(alt, dict) else []
    if not alt_trades:
        return True
    if len(window) >= 2:
        prev = window[-2].get("what_if_critique") or {}
        prev_alt = prev.get("alternative_scenario") or {}
        prev_trades = prev_alt.get("proposed_trades", []) if isinstance(prev_alt, dict) else []
        if trades_equivalent(alt_trades, prev_trades):
            return True
    return False


def proposals_stable(window: list[dict], tol: float = SHARE_STABILITY_TOLERANCE) -> bool:
    """True if the PM proposed-trades are equivalent across every round in ``window``."""
    pm_trades = [
        ((h.get("pm_proposal") or {}).get("proposed_trades", []) or [])
        for h in window
    ]
    first = pm_trades[0]
    return all(trades_equivalent(t, first, tol) for t in pm_trades)


def has_converged(
    history: list[dict],
    *,
    min_iterations: int = MIN_ITERATIONS,
    patience: int = STABILITY_PATIENCE,
    tol: float = SHARE_STABILITY_TOLERANCE,
) -> bool:
    """Decide whether the debate loop should stop.

    Stops when, over the last ``patience + 1`` rounds: the PM proposal is stable,
    the most recent Monitor check is valid (no violations), and the What-If is
    settled — but never before ``min_iterations`` rounds have run.

    ``history`` items are the per-iteration dicts with ``pm_proposal``,
    ``monitor_check`` and ``what_if_critique`` keys.
    """
    if len(history) < max(min_iterations, patience + 1):
        return False
    window = history[-(patience + 1):]
    stable = proposals_stable(window, tol)
    monitor = history[-1].get("monitor_check") or {}
    valid = bool(monitor.get("is_valid", False))
    settled = whatif_settled(window)
    return stable and valid and settled


def convergence_reason(history: list[dict]) -> str:
    """Human-readable note on why the loop did/can't yet stop (for display/logs)."""
    if not history:
        return "no iterations yet"
    if has_converged(history):
        n = len(history)
        return f"converged after {n} iteration{'s' if n != 1 else ''} (stable, valid, settled)"
    monitor = history[-1].get("monitor_check") or {}
    if not monitor.get("is_valid", False):
        return "not converged: monitor reports violations"
    return "not converged: proposals still changing or new what-if critique"
