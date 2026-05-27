"""Tests for Final Orchestrator robustness helpers: history compaction, JSON
extraction, and the safe fallback. Offline, no LLM.

Run: .venv/bin/python -m pytest tests/test_orchestrator.py -q
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_agents.final_orchestrator_agent import (  # noqa: E402
    _extract_json,
    _last_valid_trades,
    compact_history,
)


def test_compact_history_strips_bloat():
    hist = [{
        "iteration": 1,
        "pm_proposal": {"proposed_trades": [{"action": "buy", "ticker": "NVDA", "shares": 10}],
                        "notes": ["x" * 2000], "reasoning": "y" * 8000},
        "monitor_check": {"is_valid": True, "violations": [], "summary": {"k": "v" * 2000}},
        "what_if_critique": {"critique": "z" * 2000,
                             "alternative_scenario": {"proposed_trades": [{"action": "sell", "ticker": "NVDA", "shares": 5}]}},
    }]
    c = compact_history(hist)
    assert c[0]["pm_trades"] == [{"action": "buy", "ticker": "NVDA", "shares": 10}]
    assert c[0]["monitor_valid"] is True
    assert len(c[0]["what_if_critique"]) <= 300
    assert c[0]["what_if_alt_trades"] == [{"action": "sell", "ticker": "NVDA", "shares": 5}]
    # the whole point: far smaller payload than the raw history
    assert len(json.dumps(c)) < len(json.dumps(hist)) / 5


def test_extract_json_fenced():
    assert json.loads(_extract_json('```json\n{"a": 1}\n```')) == {"a": 1}


def test_extract_json_prose_wrapped():
    assert json.loads(_extract_json('Here is my decision:\n{"final_trades": []}\nDone.')) == {"final_trades": []}


def test_extract_json_plain():
    assert json.loads(_extract_json('{"x": 2}')) == {"x": 2}


def test_last_valid_trades_picks_latest_valid():
    hist = [
        {"monitor_check": {"is_valid": True}, "pm_proposal": {"proposed_trades": [{"action": "buy", "ticker": "A", "shares": 1}]}},
        {"monitor_check": {"is_valid": False}, "pm_proposal": {"proposed_trades": [{"action": "buy", "ticker": "B", "shares": 2}]}},
    ]
    assert _last_valid_trades(hist) == [{"action": "buy", "ticker": "A", "shares": 1}]


def test_last_valid_trades_none_valid():
    assert _last_valid_trades([{"monitor_check": {"is_valid": False}, "pm_proposal": {"proposed_trades": []}}]) == []
