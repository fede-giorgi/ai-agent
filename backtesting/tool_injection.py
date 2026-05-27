"""Inject the as-of cache in place of the live FinancialDatasets tools.

``install_cache`` swaps each ``@tool`` object's underlying callable (``.func``)
for the matching ``AsOfProvider`` method, then restores it on exit. This touches
no tool/agent source: the research agent's ``await tool.ainvoke(args)`` path runs
the sync ``func`` in a thread when no coroutine is registered (true for these
``@tool`` functions), and ``main.py``/agents call ``tool.func(...)`` directly —
so patching ``.func`` alone covers every call site.
"""

from __future__ import annotations

from contextlib import contextmanager

from .as_of_provider import AsOfProvider


def _set_func(tool_obj, fn):
    """Assign ``tool_obj.func`` even if the tool model resists normal attribute set."""
    try:
        tool_obj.func = fn
    except (AttributeError, ValueError, TypeError):
        object.__setattr__(tool_obj, "func", fn)


@contextmanager
def install_cache(provider: AsOfProvider):
    """Within the context, every research/data tool reads from ``provider`` (cache,
    masked to the cutoff) instead of the network. Fully reversible."""
    from tools.get_stock_prices import get_stock_prices
    from tools.get_financials import get_financials
    from tools.get_metrics import get_metrics
    from tools.get_financial_line_items import get_financial_line_items
    from tools.get_company_news import get_company_news
    from tools.get_insider_trades import get_insider_trades
    from tools.get_analyst_estimates import get_analyst_estimates
    from tools.get_segmented_revenues import get_segmented_revenues

    mapping = [
        (get_stock_prices, provider.get_stock_prices),
        (get_financials, provider.get_financials),
        (get_metrics, provider.get_metrics),
        (get_financial_line_items, provider.get_financial_line_items),
        (get_company_news, provider.get_company_news),
        (get_insider_trades, provider.get_insider_trades),
        (get_analyst_estimates, provider.get_analyst_estimates),
        (get_segmented_revenues, provider.get_segmented_revenues),
    ]
    saved = [(tool_obj, tool_obj.func) for tool_obj, _ in mapping]
    for tool_obj, fn in mapping:
        _set_func(tool_obj, fn)
    try:
        yield provider
    finally:
        for tool_obj, original in saved:
            _set_func(tool_obj, original)
