"""Verbose per-day render shows the FULL agent transcript (no truncation).

Regression for the old _render_day, which clipped What-If critiques at 240 chars
and never showed the PM's notes, the Monitor's concrete violations, or the
What-If alternative — making it impossible to judge whether the agents' choices
made sense. Sentinels are placed well past the old 240-char cutoff; single-token
sentinels survive line-wrapping so they're reliable substring checks.
"""

from rich.console import Console

from backtesting.decision_fn import _render_day

# Long lead so each sentinel lands well past the old 240-char truncation point.
_LEAD = "WMT carries a NEUTRAL signal due to a rich 44x forward P/E and an unconfirmed margin of safety. " * 4


def _render_to_text() -> str:
    signals = {
        "WMT": {
            "signal": "neutral",
            "confidence": 52,
            "reasoning": _LEAD + "SENTINEL_SIGNAL_TAIL",
        }
    }
    history = [{
        "iteration": 1,
        "pm_proposal": {
            "proposed_trades": [{"action": "sell", "ticker": "WMT", "shares": 100}],
            "notes": ["Trim the overweight WMT position. " + _LEAD + "SENTINEL_PM_NOTE"],
        },
        "monitor_check": {
            "is_valid": False,
            "violations": [{"type": "NoShort", "ticker": "WMT",
                            "detail": "trying to sell 500 but only SENTINEL_VIOLATION holds 237"}],
            "notes": [],
        },
        "what_if_critique": {
            "critique": _LEAD + "SENTINEL_CRITIQUE_TAIL",
            "alternative_scenario": {
                "description": "Hold WMT and rotate into JNJ. " + _LEAD + "SENTINEL_ALT",
                "proposed_trades": [{"action": "buy", "ticker": "JNJ", "shares": 10}],
            },
            "reasoning": "JNJ offers a wider margin of safety. " + _LEAD + "SENTINEL_WHY",
        },
    }]
    final = {"final_decision_reasoning": _LEAD + "SENTINEL_ORCH", "final_trades": []}

    console = Console(record=True, width=100, force_terminal=False)
    _render_day("2026-03-10", signals, history, final, console=console)
    return console.export_text()


def test_no_agent_text_is_truncated():
    out = _render_to_text()
    # Every agent's text must survive in full, past the old 240-char cutoff.
    for sentinel in ("SENTINEL_SIGNAL_TAIL", "SENTINEL_PM_NOTE", "SENTINEL_VIOLATION",
                     "SENTINEL_CRITIQUE_TAIL", "SENTINEL_ALT", "SENTINEL_WHY", "SENTINEL_ORCH"):
        assert sentinel in out, f"{sentinel} missing — content was truncated"


def test_structure_labels_present():
    out = _render_to_text()
    assert "Iteration 1" in out
    for label in ("Portfolio Mgr", "Monitor", "What-If", "Final decision"):
        assert label in out
    assert "NoShort" in out          # Monitor violation type surfaced
    assert "VIOLATIONS" in out       # invalid round flagged
    assert "JNJ" in out              # What-If alternative trade shown
