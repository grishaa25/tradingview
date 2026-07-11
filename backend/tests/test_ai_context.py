from app.ai.context import build_messages, extract_tickers, format_market_context

KNOWN = {"RELIANCE", "SBIN", "M&M", "VEDL", "BAJAJ-AUTO"}
ALIASES = {"VEDANTA": "VEDL"}


def test_extract_tickers_case_insensitive_and_deduped():
    msg = "compare reliance vs SBIN, then Reliance again"
    assert extract_tickers(msg, KNOWN) == ["RELIANCE", "SBIN"]


def test_extract_tickers_special_chars():
    assert extract_tickers("thoughts on M&M and BAJAJ-AUTO?", KNOWN) == [
        "M&M", "BAJAJ-AUTO",
    ]


def test_extract_tickers_resolves_aliases():
    assert extract_tickers("is VEDANTA a buy?", KNOWN, ALIASES) == ["VEDL"]


def test_extract_tickers_ignores_unknown_words():
    assert extract_tickers("what is the market doing today", KNOWN) == []


def test_extract_tickers_cap():
    msg = "RELIANCE SBIN M&M VEDL BAJAJ-AUTO"
    assert extract_tickers(msg, KNOWN, cap=2) == ["RELIANCE", "SBIN"]


def test_format_market_context_empty():
    assert format_market_context([], []) == ""
    assert format_market_context([{"ticker": "X", "has_data": False}], []) == ""


def test_format_market_context_quotes_and_signals():
    quotes = [{"ticker": "SBIN", "has_data": True, "close": 810.5, "change_pct": 1.25}]
    signals = [{"ts": "2026-07-10", "side": "buy", "ticker": "VEDL", "scan": "rsi-x"}]
    block = format_market_context(quotes, signals)
    assert "SBIN: close 810.5 (+1.25%)" in block
    assert "BUY VEDL (scan: rsi-x)" in block
    assert block.startswith("MARKET CONTEXT")


def test_build_messages_order_and_context_injection():
    msgs = build_messages(
        "next question",
        history=[{"role": "user", "content": "hi"},
                 {"role": "assistant", "content": "hello"}],
        market_context="MARKET CONTEXT: test",
    )
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    assert "MARKET CONTEXT: test" in msgs[0]["content"]
    assert msgs[-1]["content"] == "next question"


def test_build_messages_no_context():
    msgs = build_messages("q", history=[], market_context="")
    # no data block appended — only the base prompt
    assert "from the platform's own database" not in msgs[0]["content"]
