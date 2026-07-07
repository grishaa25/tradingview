"""Golden-file test: the reference rules.json must parse against the schema."""

import json
from pathlib import Path

from app.scanner.schema import Rules

RULES_PATH = Path(__file__).resolve().parents[2] / "nse-trading-bot" / "rules.json"


def test_reference_rules_parse():
    rules = Rules.model_validate(json.loads(RULES_PATH.read_text()))
    assert {i.id for i in rules.indicators} == {"rsi_daily", "rsi_hourly", "sma50_hourly"}
    assert rules.signals["buy"].logic == "ALL"
    assert len(rules.signals["buy"].conditions) == 4
    assert len(rules.signals["sell"].conditions) == 4
