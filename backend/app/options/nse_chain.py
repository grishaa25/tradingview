"""NSE option-chain API — free, keyless, same feed the nseindia.com UI uses.

NSE requires browser-like headers plus a cookie handshake: hit the option-chain
page once to receive cookies, then call the JSON API with the same client.
Indices (NIFTY, BANKNIFTY, ...) and F&O equities use different endpoints.
~3 min delayed; fine for analytics. Chain rows are persisted to
chain_snapshots so IV/OI history accumulates organically with use.
"""

import logging
from datetime import datetime

import httpx

log = logging.getLogger(__name__)

INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"}

BASE = "https://www.nseindia.com"
WARMUP_URL = f"{BASE}/option-chain"
INDICES_URL = f"{BASE}/api/option-chain-indices"
EQUITIES_URL = f"{BASE}/api/option-chain-equities"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": WARMUP_URL,
}


def chain_url(symbol: str) -> str:
    return INDICES_URL if symbol.upper() in INDEX_SYMBOLS else EQUITIES_URL


def parse_expiry(s: str) -> datetime:
    """NSE dates look like '30-Jul-2026'."""
    return datetime.strptime(s, "%d-%b-%Y")


def _leg(d: dict | None) -> dict | None:
    """One CE/PE dict from NSE → our normalized column names (None-safe)."""
    if not d:
        return None
    return {
        "ltp": d.get("lastPrice"),
        "oi": d.get("openInterest"),
        "oi_chg": d.get("changeinOpenInterest"),
        "iv": d.get("impliedVolatility"),
        "volume": d.get("totalTradedVolume"),
        "bid": d.get("bidprice"),
        "ask": d.get("askPrice"),
    }


def parse_chain(payload: dict) -> tuple[dict, list[dict]]:
    """Pure parser: NSE JSON → (meta, rows).

    meta  = {spot, expiries: [iso dates], fetched_at: raw NSE timestamp}
    rows  = [{expiry, strike, opt_type, ltp, oi, oi_chg, iv, volume, bid, ask}]
    """
    records = payload.get("records") or {}
    data = records.get("data") or []

    rows: list[dict] = []
    spot = records.get("underlyingValue")
    for item in data:
        try:
            expiry = parse_expiry(item["expiryDate"]).date().isoformat()
            strike = float(item["strikePrice"])
        except (KeyError, ValueError, TypeError):
            continue
        for opt_type in ("CE", "PE"):
            leg = _leg(item.get(opt_type))
            if leg is not None:
                rows.append({"expiry": expiry, "strike": strike, "opt_type": opt_type, **leg})
        # equities payloads carry underlyingValue per-leg, not in records
        if spot is None:
            spot = (item.get("CE") or item.get("PE") or {}).get("underlyingValue")

    expiries = sorted(
        {parse_expiry(e).date().isoformat() for e in records.get("expiryDates") or []}
    )
    meta = {"spot": spot, "expiries": expiries, "fetched_at": records.get("timestamp")}
    return meta, rows


async def fetch_chain(symbol: str) -> dict:
    """Live chain JSON for an index or F&O equity. Raises on block/network."""
    async with httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True) as client:
        # Cookie handshake — NSE 401s API calls without site cookies.
        await client.get(WARMUP_URL)
        resp = await client.get(chain_url(symbol), params={"symbol": symbol.upper()})
        resp.raise_for_status()
        return resp.json()
