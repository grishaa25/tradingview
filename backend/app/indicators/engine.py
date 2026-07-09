"""Core indicator engine.

Pure pandas implementations of the indicators the Phase-1 scanner needs.
Values match the TA-Lib / TradingView conventions (Wilder smoothing for
RSI/ATR). Each function takes and returns pandas Series aligned to the
input index; leading values are NaN until the warm-up period is filled.
"""

import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    # TradingView-style EMA: seeded with the SMA of the first `period` values.
    sma_seed = series.rolling(window=period, min_periods=period).mean()
    result = series.ewm(span=period, adjust=False).mean()
    result[: period - 1] = float("nan")
    result.iloc[period - 1] = sma_seed.iloc[period - 1]
    # re-run the recursion from the seed for exact TV/TA-Lib parity
    alpha = 2.0 / (period + 1)
    values = result.to_numpy().copy()
    for i in range(period, len(values)):
        values[i] = alpha * series.iloc[i] + (1 - alpha) * values[i - 1]
    return pd.Series(values, index=series.index, name=f"ema{period}")


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI (the TradingView / TA-Lib default).

    The first average gain/loss is the simple mean of the first `period`
    changes; subsequent values use Wilder smoothing
    avg = (prev_avg * (period-1) + current) / period.
    """
    import numpy as np

    delta = series.diff().to_numpy()
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)

    n = len(series)
    out = np.full(n, np.nan)
    if n <= period:
        return pd.Series(out, index=series.index, name=f"rsi{period}")

    avg_gain = np.nanmean(gain[1 : period + 1])
    avg_loss = np.nanmean(loss[1 : period + 1])

    def _rsi(g: float, lo: float) -> float:
        if lo == 0:
            return 100.0
        return 100.0 - 100.0 / (1.0 + g / lo)

    out[period] = _rsi(avg_gain, avg_loss)
    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gain[i]) / period
        avg_loss = (avg_loss * (period - 1) + loss[i]) / period
        out[i] = _rsi(avg_gain, avg_loss)
    return pd.Series(out, index=series.index, name=f"rsi{period}")


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean().rename(f"atr{period}")


def macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame(
        {"macd": macd_line, "signal": signal_line, "hist": macd_line - signal_line}
    )


def bollinger(series: pd.Series, period: int = 20, mult: float = 2.0) -> pd.DataFrame:
    mid = sma(series, period)
    std = series.rolling(window=period, min_periods=period).std(ddof=0)
    return pd.DataFrame(
        {"lower": mid - mult * std, "mid": mid, "upper": mid + mult * std}
    )


# Registry used by the scanner: rules.json indicator name → callable(df, period, source)
def compute(name: str, df: pd.DataFrame, period: int, source: str = "close") -> pd.Series:
    """Compute an indicator series from an OHLCV DataFrame (columns o,h,l,c,v)."""
    col = {"close": "c", "open": "o", "high": "h", "low": "l", "volume": "v"}[source]
    name = name.upper()
    if name == "RSI":
        return rsi(df[col], period)
    if name == "SMA":
        return sma(df[col], period)
    if name == "EMA":
        return ema(df[col], period)
    if name == "ATR":
        return atr(df["h"], df["l"], df["c"], period)
    raise ValueError(f"unsupported indicator: {name}")
