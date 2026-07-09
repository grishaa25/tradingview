"""Indicator engine tests against known-good values.

The RSI reference values are from Wilder's original worked example
(New Concepts in Technical Trading Systems, 1978), the same dataset
TA-Lib and StockCharts use to validate RSI(14).
"""

import pandas as pd
import pytest

from app.indicators.engine import bollinger, compute, ema, rsi, sma

# Wilder's classic 38-value close series
WILDER_CLOSES = [
    44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
    45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64,
    46.21, 46.25, 45.71, 46.45, 45.78, 45.35, 44.03, 44.18, 44.22, 44.57,
    43.42, 42.66, 43.13,
]


def test_rsi_wilder_reference():
    series = pd.Series(WILDER_CLOSES)
    out = rsi(series, 14)
    # Published reference values (StockCharts/TA-Lib) for this dataset
    assert out.iloc[14] == pytest.approx(70.46, abs=0.05)
    assert out.iloc[15] == pytest.approx(66.25, abs=0.05)
    assert out.iloc[27] == pytest.approx(41.49, abs=0.05)
    assert out.iloc[30] == pytest.approx(37.32, abs=0.05)
    # warm-up region is NaN
    assert out.iloc[:14].isna().all()


def test_rsi_bounds_and_edge_cases():
    up = pd.Series(range(1, 40), dtype=float)
    assert rsi(up, 14).iloc[-1] == pytest.approx(100.0)
    down = pd.Series(range(40, 1, -1), dtype=float)
    assert rsi(down, 14).iloc[-1] == pytest.approx(0.0, abs=1e-9)


def test_sma_simple():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    out = sma(s, 3)
    assert out.iloc[2] == pytest.approx(2.0)
    assert out.iloc[4] == pytest.approx(4.0)
    assert out.iloc[:2].isna().all()


def test_ema_seeded_with_sma():
    s = pd.Series([2.0, 4.0, 6.0, 8.0, 12.0, 14.0, 16.0, 18.0, 20.0])
    out = ema(s, 5)
    # seed = SMA(5) of first five = 6.4; next = 14*(1/3) + 6.4*(2/3)
    assert out.iloc[4] == pytest.approx(6.4)
    assert out.iloc[5] == pytest.approx(14 / 3 + 6.4 * 2 / 3)


def test_bollinger_shape():
    s = pd.Series(range(1, 30), dtype=float)
    bands = bollinger(s, 20)
    row = bands.iloc[-1]
    assert row["lower"] < row["mid"] < row["upper"]


def test_compute_registry_matches_direct_call():
    df = pd.DataFrame({"c": WILDER_CLOSES, "o": WILDER_CLOSES,
                       "h": WILDER_CLOSES, "l": WILDER_CLOSES, "v": 0})
    via_registry = compute("RSI", df, 14)
    direct = rsi(df["c"], 14)
    pd.testing.assert_series_equal(via_registry, direct)
