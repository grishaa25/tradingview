"""Contract tests for NSE file parsers, using recorded-format fixtures."""

from datetime import date
from pathlib import Path

from app.marketdata.ingest.bhavcopy import parse_bhavcopy
from app.marketdata.ingest.universe import parse_lots

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_bhavcopy_keeps_eq_series_and_skips_junk():
    rows = parse_bhavcopy((FIXTURES / "sec_bhavdata_full_sample.csv").read_text())
    # RELIANCE + HDFCBANK (EQ) + INFY (BE); BADROW malformed, SOMEBOND wrong series
    assert {r["ticker"] for r in rows} == {"RELIANCE", "HDFCBANK", "INFY"}
    rel = next(r for r in rows if r["ticker"] == "RELIANCE")
    assert rel["ts"] == date(2026, 7, 6)
    assert rel["o"] == 2880.00 and rel["c"] == 2912.35
    assert rel["prev_close"] == 2871.00
    assert rel["v"] == 5824312
    assert rel["deliv_per"] == 50.00


def test_parse_bhavcopy_empty_input():
    assert parse_bhavcopy("") == []


def test_parse_lots_excludes_indices_and_junk():
    lots = parse_lots((FIXTURES / "fo_mktlots_sample.csv").read_text())
    # NIFTY/BANKNIFTY are indices; BADSTOCK has a non-numeric lot
    assert lots == [
        {"ticker": "RELIANCE", "lot_size": 250},
        {"ticker": "HDFCBANK", "lot_size": 550},
    ]
