from app.impact.service import compute_contributions
from app.impact.weights_seed import NIFTY50_WEIGHTS
from app.marketdata.fno_seed import FNO_TICKERS


def test_weights_seed_sane():
    assert len(NIFTY50_WEIGHTS) == 50
    assert 90 <= sum(NIFTY50_WEIGHTS.values()) <= 110  # ~100%, drift-tolerant
    assert all(w > 0 for w in NIFTY50_WEIGHTS.values())


def test_weights_tickers_exist_in_fno_universe():
    # Every NIFTY 50 name trades F&O; catches typos/renames in the seed.
    missing = set(NIFTY50_WEIGHTS) - set(FNO_TICKERS)
    assert not missing, f"weights seed tickers not in FNO seed: {missing}"


def test_compute_contributions_math():
    # index at 25000, two stocks with equal 50% normalized weight:
    # +2% on half the index = +250 points, -1% on the other half = -125.
    out = compute_contributions(
        25000.0,
        [
            {"ticker": "A", "weight": 30.0, "change_pct": 2.0},
            {"ticker": "B", "weight": 30.0, "change_pct": -1.0},
        ],
    )
    assert out[0] == {"ticker": "A", "weight": 30.0, "change_pct": 2.0,
                      "impact_points": 250.0}
    assert out[1]["impact_points"] == -125.0


def test_compute_contributions_sorted_desc():
    out = compute_contributions(
        20000.0,
        [
            {"ticker": "LOSER", "weight": 10.0, "change_pct": -3.0},
            {"ticker": "WINNER", "weight": 10.0, "change_pct": 5.0},
        ],
    )
    assert [c["ticker"] for c in out] == ["WINNER", "LOSER"]


def test_compute_contributions_missing_data_passthrough():
    out = compute_contributions(
        20000.0,
        [
            {"ticker": "NODATA", "weight": 5.0, "change_pct": None},
            {"ticker": "UP", "weight": 5.0, "change_pct": 1.0},
        ],
    )
    nodata = next(c for c in out if c["ticker"] == "NODATA")
    assert nodata["impact_points"] is None
