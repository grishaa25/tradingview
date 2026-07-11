import pytest

from app.marketdata.service import compute_change_pct


def test_compute_change_pct_positive():
    assert compute_change_pct(100.0, 110.0) == 10.0


def test_compute_change_pct_negative():
    assert compute_change_pct(200.0, 190.0) == -5.0


def test_compute_change_pct_none_inputs():
    assert compute_change_pct(None, 100.0) is None
    assert compute_change_pct(100.0, None) is None


def test_compute_change_pct_zero_prev_close():
    assert compute_change_pct(0.0, 100.0) is None


def test_compute_change_pct_rounds():
    assert compute_change_pct(3.0, 3.1) == pytest.approx(3.33)
