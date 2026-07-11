from app.options import analytics
from app.options.nse_chain import parse_chain, parse_expiry
from app.options.service import merge_by_strike, pick_expiry

# Trimmed but shape-faithful NSE option-chain-indices payload.
NSE_PAYLOAD = {
    "records": {
        "expiryDates": ["16-Jul-2026", "30-Jul-2026"],
        "underlyingValue": 25050.5,
        "timestamp": "10-Jul-2026 15:30:00",
        "data": [
            {
                "strikePrice": 25000,
                "expiryDate": "16-Jul-2026",
                "CE": {
                    "lastPrice": 180.5, "openInterest": 5000,
                    "changeinOpenInterest": 400, "impliedVolatility": 12.5,
                    "totalTradedVolume": 90000, "bidprice": 180.0, "askPrice": 181.0,
                },
                "PE": {
                    "lastPrice": 130.0, "openInterest": 8000,
                    "changeinOpenInterest": -200, "impliedVolatility": 13.1,
                    "totalTradedVolume": 110000, "bidprice": 129.5, "askPrice": 130.5,
                },
            },
            {
                "strikePrice": 25100,
                "expiryDate": "16-Jul-2026",
                "CE": {
                    "lastPrice": 120.0, "openInterest": 9000,
                    "changeinOpenInterest": 900, "impliedVolatility": 12.1,
                    "totalTradedVolume": 150000, "bidprice": 119.5, "askPrice": 120.5,
                },
                # PE leg absent — common for far strikes
            },
            {"strikePrice": "junk", "expiryDate": "16-Jul-2026"},  # skipped
        ],
    }
}


def test_parse_chain_meta_and_rows():
    meta, rows = parse_chain(NSE_PAYLOAD)
    assert meta["spot"] == 25050.5
    assert meta["expiries"] == ["2026-07-16", "2026-07-30"]
    assert len(rows) == 3  # 25000 CE+PE, 25100 CE only; junk row skipped
    ce = next(r for r in rows if r["strike"] == 25000 and r["opt_type"] == "CE")
    assert ce == {
        "expiry": "2026-07-16", "strike": 25000.0, "opt_type": "CE",
        "ltp": 180.5, "oi": 5000, "oi_chg": 400, "iv": 12.5,
        "volume": 90000, "bid": 180.0, "ask": 181.0,
    }


def test_parse_chain_malformed_payload():
    assert parse_chain({}) == ({"spot": None, "expiries": [], "fetched_at": None}, [])


def test_parse_expiry():
    assert parse_expiry("30-Jul-2026").date().isoformat() == "2026-07-30"


def _row(strike, opt_type, oi, volume=0, iv=None):
    return {"strike": strike, "opt_type": opt_type, "oi": oi, "volume": volume, "iv": iv}


def test_pcr():
    rows = [_row(100, "CE", 1000, volume=500), _row(100, "PE", 1500, volume=250)]
    assert analytics.pcr(rows) == {"oi": 1.5, "volume": 0.5}


def test_pcr_zero_denominator():
    assert analytics.pcr([_row(100, "PE", 500)]) == {"oi": None, "volume": None}


def test_max_pain_prefers_heavy_oi_cluster():
    # All the put OI sits at 100 and call OI at 120 → pain minimized between,
    # and exactly computable: at 110 pain = 500*(110-100 from puts? no—puts pay when K>S)
    rows = [
        _row(100, "PE", 5000),
        _row(110, "CE", 100), _row(110, "PE", 100),
        _row(120, "CE", 5000),
    ]
    # Settling at 110: calls(120) pay 0, puts(100) pay 0 → near-zero pain.
    assert analytics.max_pain(rows) == 110


def test_max_pain_empty():
    assert analytics.max_pain([]) is None


def test_atm_strike_and_oi_extremes():
    rows = [
        _row(24900, "PE", 9000), _row(24900, "CE", 100),
        _row(25000, "PE", 500), _row(25000, "CE", 700),
        _row(25100, "CE", 8000), _row(25100, "PE", 50),
    ]
    assert analytics.atm_strike(rows, 25040.0) == 25000
    assert analytics.oi_extremes(rows) == {"support": 24900, "resistance": 25100}


def test_atm_iv_averages_both_legs():
    rows = [
        _row(25000, "CE", 10, iv=12.0), _row(25000, "PE", 10, iv=14.0),
        _row(26000, "CE", 10, iv=99.0),
    ]
    assert analytics.atm_iv(rows, 25010.0) == 13.0


def test_summarize_bundles_everything():
    rows = [_row(25000, "CE", 100, volume=10, iv=12.0),
            _row(25000, "PE", 200, volume=20, iv=14.0)]
    summary = analytics.summarize(rows, 25000.0)
    assert set(summary) == {"pcr", "max_pain", "atm_strike", "atm_iv",
                            "support", "resistance"}


def test_pick_expiry():
    expiries = ["2020-01-30", "2099-01-16", "2099-01-30"]
    assert pick_expiry(expiries, None) == "2099-01-16"          # nearest upcoming
    assert pick_expiry(expiries, "2099-01-30") == "2099-01-30"  # explicit
    assert pick_expiry(expiries, "2098-01-01") == "2099-01-16"  # unknown → default
    assert pick_expiry(["2020-01-30"], None) == "2020-01-30"    # all past → last
    assert pick_expiry([], None) is None


def test_merge_by_strike():
    _, rows = parse_chain(NSE_PAYLOAD)
    merged = merge_by_strike(rows)
    assert [m["strike"] for m in merged] == [25000.0, 25100.0]
    assert merged[0]["ce"]["ltp"] == 180.5
    assert merged[0]["pe"]["oi"] == 8000
    assert merged[1]["pe"] is None
