from app.alerts.dispatcher import format_signal_message


def test_buy_message_format():
    msg = format_signal_message(
        "RELIANCE",
        "buy",
        [
            {"id": "daily_rsi_bullish", "operator": ">", "left": 64.2, "right": 60, "passed": True},
            {"id": "bullish_daily_candle", "operator": ">", "left": 2912.35, "right": 2871.0, "passed": True},
        ],
    )
    assert msg.startswith("🟢 <b>BUY RELIANCE</b>")
    assert "daily_rsi_bullish 64.2 > 60 ✓" in msg


def test_sell_message_format():
    msg = format_signal_message("INFY", "sell", [])
    assert msg.startswith("🔴 <b>SELL INFY</b>")
