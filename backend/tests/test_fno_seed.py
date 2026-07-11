from app.marketdata.fno_seed import FNO_TICKERS, TICKER_ALIASES


def test_no_duplicate_tickers():
    assert len(FNO_TICKERS) == len(set(FNO_TICKERS))


def test_recent_renames_present():
    for t in ("ETERNAL", "ADANIENSOL", "TMPV"):
        assert t in FNO_TICKERS


def test_common_aliases_resolve_into_seed_list():
    for alias, canonical in TICKER_ALIASES.items():
        assert canonical in FNO_TICKERS, f"{alias} -> {canonical} not in FNO_TICKERS"
