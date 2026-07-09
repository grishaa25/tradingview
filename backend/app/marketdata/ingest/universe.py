"""F&O universe + lot-size refresh from NSE's fo_mktlots.csv (daily, EOD).

Format:
UNDERLYING,SYMBOL,JUL-26,AUG-26,SEP-26
NIFTY 50,NIFTY,25,25,25
RELIANCE INDUSTRIES,RELIANCE,250,250,250
"""

import csv
import io

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.marketdata.ingest.bhavcopy import HEADERS

LOTS_URL = "https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv"

INDEX_UNDERLYINGS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"}


def parse_lots(csv_text: str) -> list[dict]:
    """Pure parser: CSV → [{ticker, lot_size}] for stock (non-index) rows."""
    out: list[dict] = []
    reader = csv.reader(io.StringIO(csv_text))
    header = next(reader, None)
    if header is None or len(header) < 3:
        return out
    for row in reader:
        if len(row) < 3:
            continue
        ticker = row[1].strip()
        if not ticker or ticker.upper() in INDEX_UNDERLYINGS:
            continue
        try:
            out.append({"ticker": ticker, "lot_size": int(row[2].strip())})
        except ValueError:
            continue
    return out


async def fetch_lots() -> str:
    async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:
        resp = await client.get(LOTS_URL)
        resp.raise_for_status()
        return resp.text


async def apply_universe(session: AsyncSession, lots: list[dict]) -> int:
    """Marks F&O membership + lot sizes; clears the flag for departures."""
    import json

    await session.execute(text("UPDATE symbols SET fno_flag = false WHERE fno_flag"))
    result = await session.execute(
        text(
            "INSERT INTO symbols (ticker, exchange, fno_flag, lot_size) "
            "SELECT x.ticker, 'NSE', true, x.lot_size "
            "FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS x(ticker text, lot_size int) "
            "ON CONFLICT (exchange, ticker) DO UPDATE "
            "SET fno_flag = true, lot_size = excluded.lot_size"
        ),
        {"rows": json.dumps(lots)},
    )
    await session.commit()
    return result.rowcount or 0


async def refresh_universe(session: AsyncSession) -> int:
    return await apply_universe(session, parse_lots(await fetch_lots()))
