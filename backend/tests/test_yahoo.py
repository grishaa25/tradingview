"""Contract tests for the Yahoo v8 chart API parser."""

from datetime import datetime, timezone

from app.marketdata.ingest.yahoo import parse_chart, yahoo_symbol


def chart_payload(timestamps, opens, highs, lows, closes, volumes):
    return {
        "chart": {
            "result": [
                {
                    "meta": {"symbol": "RELIANCE.NS"},
                    "timestamp": timestamps,
                    "indicators": {
                        "quote": [
                            {
                                "open": opens,
                                "high": highs,
                                "low": lows,
                                "close": closes,
                                "volume": volumes,
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }


def test_parse_chart_normal():
    payload = chart_payload(
        [1751856300, 1751942700],
        [2880.0, 2915.0],
        [2925.5, 2940.0],
        [2868.1, 2905.0],
        [2912.35, 2931.2],
        [5824312, 4102331],
    )
    rows = parse_chart(payload)
    assert len(rows) == 2
    assert rows[0]["ts"] == datetime.fromtimestamp(1751856300, tz=timezone.utc)
    assert rows[0]["o"] == 2880.0 and rows[0]["c"] == 2912.35
    assert rows[1]["v"] == 4102331


def test_parse_chart_skips_null_bars():
    payload = chart_payload(
        [1751856300, 1751942700, 1752029100],
        [2880.0, None, 2950.0],
        [2925.5, None, 2960.0],
        [2868.1, None, 2940.0],
        [2912.35, None, 2955.0],
        [5824312, None, 3000000],
    )
    rows = parse_chart(payload)
    assert len(rows) == 2  # null middle bar dropped


def test_parse_chart_malformed():
    assert parse_chart({}) == []
    assert parse_chart({"chart": {"result": None}}) == []
    assert parse_chart({"chart": {"result": [{"timestamp": None, "indicators": {"quote": [{}]}}]}}) == []


def test_yahoo_symbol_mapping():
    assert yahoo_symbol("RELIANCE") == "RELIANCE.NS"
    assert yahoo_symbol("RELIANCE", "BSE") == "RELIANCE.BO"
    assert yahoo_symbol("M&M") == "M&M.NS"  # httpx handles URL quoting
