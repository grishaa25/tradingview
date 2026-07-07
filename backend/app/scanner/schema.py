"""Pydantic mirror of the nse-trading-bot/rules.json scanner schema.

This is the contract shared by the scanner evaluator, the scans.rules jsonb
column, and (later) the backtest translator — see docs/ARCHITECTURE.md §5.1.
"""

from typing import Literal

from pydantic import BaseModel, model_validator

Operator = Literal[">", "<", ">=", "<=", "==", "crosses_above", "crosses_below"]


class IndicatorDef(BaseModel):
    name: str                      # 'RSI' | 'SMA' | 'EMA' | ...
    period: int
    timeframe: str                 # '1D' | '60'
    source: str = "close"
    id: str


class Operand(BaseModel):
    timeframe: str | None = None   # '1D' | '60'
    field: str | None = None       # 'close','open','high','low','volume'
    offset: int = 0                # 0 = current bar, 1 = previous bar
    indicator: str | None = None   # id from the indicators[] block


class Condition(BaseModel):
    id: str
    description: str | None = None
    indicator: str | None = None   # shorthand form: indicator OP value
    operator: Operator
    value: float | None = None
    left: Operand | None = None    # general form: left OP right
    right: Operand | None = None

    @model_validator(mode="after")
    def check_form(self) -> "Condition":
        shorthand = self.indicator is not None and self.value is not None
        general = self.left is not None and self.right is not None
        if not (shorthand or general):
            raise ValueError(
                f"condition {self.id!r} must be either indicator/value or left/right"
            )
        return self


class Trigger(BaseModel):
    mode: Literal["immediate"] = "immediate"
    description: str | None = None
    re_arm: str | None = None


class SignalSide(BaseModel):
    logic: Literal["ALL", "ANY"]
    description: str | None = None
    conditions: list[Condition]
    trigger: Trigger


class Rules(BaseModel):
    """Top-level rules.json document (only the fields the engine consumes)."""

    meta: dict = {}
    universe: dict = {}
    timeframes: dict = {}
    indicators: list[IndicatorDef]
    signals: dict[Literal["buy", "sell"], SignalSide]
    scan: dict = {}
    risk: dict = {}
