import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from collect_insights import (anomalies, backtest_gain, forecast_series,
                              ground, iso_of)


# ── forecast_series ────────────────────────────────────────────────────
def test_bands_ordered_and_sized():
    hist = [100 + (i % 7) * 10 for i in range(120)]      # pure weekly cycle
    out = forecast_series(hist, horizon=14, season=7)
    assert len(out) == 14
    for r in out:
        assert r["lo"] <= r["mid"] <= r["hi"]
    # a perfectly periodic series forecasts itself, with a band of ~zero width
    assert out[0]["mid"] == hist[-7]
    assert out[0]["hi"] - out[0]["lo"] < 1.0


def test_forecast_continues_the_cycle():
    hist = [100 + (i % 7) * 10 for i in range(120)]
    out = forecast_series(hist, horizon=14, season=7)
    # day 8 of the forecast repeats day 1: the cycle carries forward
    assert out[7]["mid"] == out[0]["mid"]


def test_short_series_returns_nothing():
    assert forecast_series([1.0, 2.0, 3.0], horizon=14, season=7) == []


# ── backtest_gain ──────────────────────────────────────────────────────
def test_backtest_gain_detects_seasonality():
    seasonal = [100 + (i % 7) * 10 for i in range(200)]
    assert backtest_gain(seasonal, season=7) > 0.5       # weekly lag wins big


def test_backtest_gain_rejects_pure_trend():
    trend = [float(i) for i in range(200)]                # no weekly structure
    assert backtest_gain(trend, season=7) <= 0


# ── grounding gate ─────────────────────────────────────────────────────
def test_grounding_accepts_supplied_numbers():
    facts = {"ron95": 3.77, "donations": 1657}
    assert ground("RON95 is RM3.77 this week", facts) is True
    assert ground("Donations hit 1,657 today", facts) is True
    assert ground("No numbers here at all", facts) is True


def test_grounding_rejects_invented_numbers():
    facts = {"ron95": 3.77, "donations": 1657}
    assert ground("Inflation rose to 4.2%", facts) is False


def test_grounding_reads_nested_facts():
    facts = {"fuel": {"ron95": 3.77}, "top": [{"n": 1657}]}
    assert ground("RON95 3.77 and 1657 donors", facts) is True


# ── anomalies ──────────────────────────────────────────────────────────
def test_anomaly_flags_a_real_outlier():
    base = [100 + (i % 7) * 5 for i in range(200)]
    base[-3] = 900                                        # unmistakable spike
    hits = anomalies({"x": {"t0": 20000, "vals": base}}, holidays=set(), z=2.5)
    assert any(h["key"] == "x" and h["value"] == 900 for h in hits)


def test_anomaly_ignores_holidays():
    base = [100 + (i % 7) * 5 for i in range(200)]
    base[-3] = 900
    spike_day = iso_of(20000 + 197)
    hits = anomalies({"x": {"t0": 20000, "vals": base}},
                     holidays={spike_day}, z=2.5)
    assert all(h["date"] != spike_day for h in hits)


# ── gaps must not break the weekly lag ─────────────────────────────────
def test_lag_is_in_days_not_observations():
    """A series with holes must still forecast the right weekday.

    Compacting Nones out first would make `hist[-7]` mean 'seven observations
    ago'. On rapid rail komuter (1,060 gaps in 2,126 days) that is nowhere
    near seven days, which destroys the cycle the forecast depends on."""
    vals = [100 + (i % 7) * 10 for i in range(200)]
    for i in range(0, 200, 3):          # punch out a third of the series
        vals[i] = None
    out = forecast_series(vals, horizon=7, season=7)
    assert len(out) == 7
    for i, r in enumerate(out):
        expected = 100 + ((200 + i) % 7) * 10
        assert r["mid"] == expected, f"day {i}: {r['mid']} != {expected}"


def test_gain_ignores_gaps():
    seasonal = [100 + (i % 7) * 10 for i in range(200)]
    for i in range(0, 200, 5):
        seasonal[i] = None
    assert backtest_gain(seasonal, season=7) > 0.5
