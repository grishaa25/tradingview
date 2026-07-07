"""Golden-file tests: the reference rules.json evaluated over synthetic candles.

Synthetic universes are engineered so we know exactly which conditions hold:
a strong uptrend must fire BUY, a strong downtrend must fire SELL, and a
mixed regime (daily up, hourly weak) must fire neither — the dual-timeframe
agreement requirement is the whole point of the strategy.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.scanner.evaluator import (
    PassContext,
    evaluate_condition,
    evaluate_side,
    evaluate_symbol,
)
from app.scanner.schema import Rules
from app.scanner.state import ARMED, FIRED, transition

RULES = Rules.model_validate(
    json.loads(
        (Path(__file__).resolve().parents[2] / "nse-trading-bot" / "rules.json").read_text()
    )
)


def make_df(closes: list[float]) -> pd.DataFrame:
    c = pd.Series(closes, dtype=float)
    return pd.DataFrame(
        {"o": c.shift(1).fillna(c[0]), "h": c * 1.01, "l": c * 0.99, "c": c, "v": 1000}
    )


def trending(n: int, start: float, step: float, wobble: float = 0.0) -> list[float]:
    rng = np.random.default_rng(42)
    return [
        start + step * i + (rng.uniform(-wobble, wobble) if wobble else 0.0)
        for i in range(n)
    ]


@pytest.fixture
def uptrend_ctx() -> PassContext:
    # steady rise on both timeframes → RSI high, close>prev close, close>SMA50
    return PassContext(
        candles={"1D": make_df(trending(60, 100, 1.0)),
                 "60": make_df(trending(120, 100, 0.5))},
        rules=RULES,
    )


@pytest.fixture
def downtrend_ctx() -> PassContext:
    return PassContext(
        candles={"1D": make_df(trending(60, 200, -1.0)),
                 "60": make_df(trending(120, 200, -0.5))},
        rules=RULES,
    )


def test_buy_fires_in_uptrend(uptrend_ctx):
    fired, snapshots = evaluate_side(RULES.signals["buy"], uptrend_ctx)
    assert fired
    assert len(snapshots) == 4 and all(s["passed"] for s in snapshots)
    by_id = {s["id"]: s for s in snapshots}
    assert by_id["daily_rsi_bullish"]["left"] > 60
    assert by_id["price_above_hourly_sma50"]["left"] > by_id["price_above_hourly_sma50"]["right"]


def test_sell_does_not_fire_in_uptrend(uptrend_ctx):
    fired, snapshots = evaluate_side(RULES.signals["sell"], uptrend_ctx)
    assert not fired
    # ALL logic short-circuits: first failing condition ends evaluation
    assert len(snapshots) < 4 or not all(s["passed"] for s in snapshots)


def test_sell_fires_in_downtrend(downtrend_ctx):
    results = evaluate_symbol(downtrend_ctx)
    assert results["sell"][0] and not results["buy"][0]


def test_mixed_regime_fires_nothing():
    # daily strongly up, hourly strongly down → dual-timeframe agreement fails
    ctx = PassContext(
        candles={"1D": make_df(trending(60, 100, 1.0)),
                 "60": make_df(trending(120, 200, -0.5))},
        rules=RULES,
    )
    results = evaluate_symbol(ctx)
    assert not results["buy"][0] and not results["sell"][0]


def test_insufficient_history_does_not_fire():
    # fewer bars than SMA50/RSI warm-up → NaN values must evaluate false, not crash
    ctx = PassContext(
        candles={"1D": make_df(trending(10, 100, 1.0)),
                 "60": make_df(trending(10, 100, 0.5))},
        rules=RULES,
    )
    results = evaluate_symbol(ctx)
    assert not results["buy"][0] and not results["sell"][0]


def test_crosses_above_semantics():
    from app.scanner.schema import Condition, Operand

    # hourly close crosses above sma5: engineered flat-then-jump series
    closes = [10.0] * 20 + [9.0, 12.0]  # prev bar below sma, current above
    ctx = PassContext(candles={"60": make_df(closes)}, rules=RULES)
    cond = Condition(
        id="x",
        operator="crosses_above",
        left=Operand(timeframe="60", field="close"),
        right=Operand(timeframe="60", field="open"),  # open lags close by 1 bar
    )
    passed, snap = evaluate_condition(cond, ctx)
    # close[now]=12 > open[now]=9 and close[prev]=9 <= open[prev]=10 → cross
    assert passed


def test_rearm_state_machine():
    # armed + true → fire
    assert transition(ARMED, True) == (FIRED, True)
    # fired + true → no duplicate
    assert transition(FIRED, True) == (FIRED, False)
    # fired + false → re-arm silently
    assert transition(FIRED, False) == (ARMED, False)
    # armed + false → stay armed
    assert transition(ARMED, False) == (ARMED, False)
