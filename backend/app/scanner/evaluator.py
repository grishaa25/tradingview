"""Scanner condition-tree evaluator (docs/ARCHITECTURE.md §5).

Deterministic and pure: (candles per timeframe, rules) → per-side result.
The runner supplies a PassContext per symbol; indicator series are computed
once and memoized there. `ALL` logic short-circuits on rejects (the hot
path), but when a side fires we evaluate every condition so the signal
snapshot records each condition's actual values.
"""

from dataclasses import dataclass, field

import pandas as pd

from app.indicators import engine as ind
from app.scanner.schema import Condition, Operand, Rules, SignalSide


@dataclass
class PassContext:
    """Everything needed to evaluate one symbol on one scan pass."""

    candles: dict[str, pd.DataFrame]  # timeframe id → OHLCV df (o,h,l,c,v cols)
    rules: Rules
    _indicators: dict[str, pd.Series] = field(default_factory=dict)

    def indicator_series(self, indicator_id: str) -> pd.Series:
        if indicator_id not in self._indicators:
            spec = next(
                (i for i in self.rules.indicators if i.id == indicator_id), None
            )
            if spec is None:
                raise KeyError(f"indicator id not defined in rules: {indicator_id}")
            df = self.candles[spec.timeframe]
            self._indicators[indicator_id] = ind.compute(
                spec.name, df, spec.period, spec.source
            )
        return self._indicators[indicator_id]

    def operand_series(self, op: Operand) -> tuple[pd.Series, int]:
        """Resolve an operand to (series, offset)."""
        if op.indicator is not None:
            return self.indicator_series(op.indicator), op.offset
        if op.timeframe is None or op.field is None:
            raise ValueError(f"operand needs indicator or timeframe+field: {op}")
        col = {"close": "c", "open": "o", "high": "h", "low": "l", "volume": "v"}[op.field]
        return self.candles[op.timeframe][col], op.offset


def _value_at(series: pd.Series, offset: int, back: int = 0) -> float:
    """Value `offset` bars back from the latest bar (+`back` for crosses)."""
    idx = -1 - offset - back
    if len(series) < -idx:
        raise IndexError("not enough bars")
    return float(series.iloc[idx])


def _compare(op: str, left: float, right: float) -> bool:
    match op:
        case ">":
            return left > right
        case "<":
            return left < right
        case ">=":
            return left >= right
        case "<=":
            return left <= right
        case "==":
            return left == right
    raise ValueError(f"unsupported operator: {op}")


def evaluate_condition(cond: Condition, ctx: PassContext) -> tuple[bool, dict]:
    """Returns (passed, snapshot-entry with actual values)."""
    if cond.indicator is not None and cond.value is not None:
        # shorthand form: indicator OP threshold
        series = ctx.indicator_series(cond.indicator)
        left_now, right_now = _value_at(series, 0), float(cond.value)
        if cond.operator in ("crosses_above", "crosses_below"):
            left_prev, right_prev = _value_at(series, 0, back=1), right_now
        else:
            left_prev = right_prev = None
    else:
        left_series, l_off = ctx.operand_series(cond.left)  # type: ignore[arg-type]
        right_series, r_off = ctx.operand_series(cond.right)  # type: ignore[arg-type]
        left_now = _value_at(left_series, l_off)
        right_now = _value_at(right_series, r_off)
        if cond.operator in ("crosses_above", "crosses_below"):
            left_prev = _value_at(left_series, l_off, back=1)
            right_prev = _value_at(right_series, r_off, back=1)
        else:
            left_prev = right_prev = None

    if pd.isna(left_now) or pd.isna(right_now):
        passed = False
    elif cond.operator == "crosses_above":
        passed = (
            left_prev is not None
            and not pd.isna(left_prev)
            and left_prev <= right_prev
            and left_now > right_now
        )
    elif cond.operator == "crosses_below":
        passed = (
            left_prev is not None
            and not pd.isna(left_prev)
            and left_prev >= right_prev
            and left_now < right_now
        )
    else:
        passed = _compare(cond.operator, left_now, right_now)

    snapshot = {
        "id": cond.id,
        "operator": cond.operator,
        "left": None if pd.isna(left_now) else round(left_now, 4),
        "right": None if pd.isna(right_now) else round(right_now, 4),
        "passed": passed,
    }
    return passed, snapshot


def evaluate_side(side: SignalSide, ctx: PassContext) -> tuple[bool, list[dict]]:
    """Evaluate one signal side. Short-circuit rejects; full snapshot on fire."""
    snapshots: list[dict] = []
    if side.logic == "ALL":
        for cond in side.conditions:
            passed, snap = evaluate_condition(cond, ctx)
            snapshots.append(snap)
            if not passed:
                return False, snapshots  # short-circuit: reject is the hot path
        return True, snapshots
    # ANY: must evaluate all either way
    any_passed = False
    for cond in side.conditions:
        passed, snap = evaluate_condition(cond, ctx)
        snapshots.append(snap)
        any_passed = any_passed or passed
    return any_passed, snapshots


def evaluate_symbol(ctx: PassContext) -> dict[str, tuple[bool, list[dict]]]:
    """Evaluate every side defined in the rules for one symbol."""
    return {
        side_name: evaluate_side(side, ctx)
        for side_name, side in ctx.rules.signals.items()
    }
