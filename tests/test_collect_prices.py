"""Unit tests for the PriceCatcher collector.

Root cause (2026-09-04): the cron `collect_prices.yml` runs on `main` and
checks out `tools/collect_prices.py` there. `main` still builds the fixed
basket over the full window including the sparse, still-being-collected
trailing month, so the "every month" intersection collapses (~290 -> 47
items) and the Validate-output gate (`n >= 80`) fails. Four straight
failures (Sep 1-4); last success Aug 31.

`_index_months` drops a trailing month that carries < 50% of the prior
month's observations, building the basket/index over the completed months
and flagging the sparse one as `partial`. These tests pin that logic.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import collect_prices  # noqa: E402


def _obs(n_full, n_last, months):
    """Synthetic observations: every month `months` full except the last,
    which carries `n_last` rows (to simulate a sparse in-progress month)."""
    rows = []
    for ym in months[:-1]:
        for i in range(n_full):
            rows.append((ym, 1 + i % 10, 100 + i))
    for i in range(n_last):
        rows.append((months[-1], 1 + i % 10, 100 + i))
    return pd.DataFrame(rows, columns=["ym", "item_code", "price"])


def test_full_trailing_month_is_not_partial():
    obs = _obs(50, 45, ["2026-01", "2026-02"])  # last ~90% -> complete
    index_months, partial = collect_prices._index_months(obs, ["2026-01", "2026-02"])
    assert partial is None
    assert index_months == ["2026-01", "2026-02"]


def test_sparse_trailing_month_is_dropped_and_flagged():
    obs = _obs(50, 5, ["2026-01", "2026-02", "2026-03"])  # last ~10%
    index_months, partial = collect_prices._index_months(
        obs, ["2026-01", "2026-02", "2026-03"])
    assert partial == "2026-03"
    assert index_months == ["2026-01", "2026-02"]


def test_two_month_window_with_sparse_last_keeps_both():
    # Even at width 2 the sparse month is dropped and flagged partial; in the
    # real 13-month run this leaves a healthy 12-month index. A 1-point index
    # never reaches the Validate gate in production.
    obs = _obs(50, 5, ["2026-02", "2026-03"])
    index_months, partial = collect_prices._index_months(
        obs, ["2026-02", "2026-03"])
    assert index_months == ["2026-02"]
    assert partial == "2026-03"