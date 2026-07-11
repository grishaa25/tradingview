"""Pure option-chain analytics — derived on read from parsed chain rows.

All functions take rows already filtered to a single expiry:
[{strike, opt_type: 'CE'|'PE', oi, oi_chg, volume, ltp, iv, ...}]
"""


def _oi(row: dict) -> int:
    return int(row.get("oi") or 0)


def pcr(rows: list[dict]) -> dict:
    """Put/Call ratio by OI and by volume. None when the denominator is 0."""
    ce_oi = sum(_oi(r) for r in rows if r["opt_type"] == "CE")
    pe_oi = sum(_oi(r) for r in rows if r["opt_type"] == "PE")
    ce_vol = sum(int(r.get("volume") or 0) for r in rows if r["opt_type"] == "CE")
    pe_vol = sum(int(r.get("volume") or 0) for r in rows if r["opt_type"] == "PE")
    return {
        "oi": round(pe_oi / ce_oi, 2) if ce_oi else None,
        "volume": round(pe_vol / ce_vol, 2) if ce_vol else None,
    }


def max_pain(rows: list[dict]) -> float | None:
    """Strike where total option-writer payout is minimal at expiry.

    Payout at settlement S: calls pay OI·max(S−K, 0), puts pay OI·max(K−S, 0).
    Evaluated at each listed strike (the standard approximation).
    """
    strikes = sorted({r["strike"] for r in rows})
    if not strikes:
        return None
    calls = [(r["strike"], _oi(r)) for r in rows if r["opt_type"] == "CE"]
    puts = [(r["strike"], _oi(r)) for r in rows if r["opt_type"] == "PE"]

    best_strike, best_pain = None, None
    for s in strikes:
        pain = sum(oi * max(s - k, 0) for k, oi in calls) + sum(
            oi * max(k - s, 0) for k, oi in puts
        )
        if best_pain is None or pain < best_pain:
            best_strike, best_pain = s, pain
    return best_strike


def atm_strike(rows: list[dict], spot: float | None) -> float | None:
    strikes = sorted({r["strike"] for r in rows})
    if not strikes or spot is None:
        return None
    return min(strikes, key=lambda k: abs(k - spot))


def oi_extremes(rows: list[dict]) -> dict:
    """Highest-OI strikes: PE wall reads as support, CE wall as resistance."""

    def top(opt_type: str) -> float | None:
        side = [r for r in rows if r["opt_type"] == opt_type and _oi(r) > 0]
        return max(side, key=_oi)["strike"] if side else None

    return {"support": top("PE"), "resistance": top("CE")}


def atm_iv(rows: list[dict], spot: float | None) -> float | None:
    """Mean CE/PE implied vol at the ATM strike (feeds iv_history later)."""
    atm = atm_strike(rows, spot)
    if atm is None:
        return None
    ivs = [
        float(r["iv"])
        for r in rows
        if r["strike"] == atm and r.get("iv") not in (None, 0)
    ]
    return round(sum(ivs) / len(ivs), 2) if ivs else None


def summarize(rows: list[dict], spot: float | None) -> dict:
    """Bundle every analytic for one expiry's rows."""
    return {
        "pcr": pcr(rows),
        "max_pain": max_pain(rows),
        "atm_strike": atm_strike(rows, spot),
        "atm_iv": atm_iv(rows, spot),
        **oi_extremes(rows),
    }
