"""NSE EOD bhavcopy ingestion (ARCHITECTURE §3.1, ~18:30 IST daily).

Downloads the official `sec_bhavdata_full_DDMMYYYY.csv` (includes delivery %),
parses EQ-series rows, and upserts daily candles + symbol rows. The official
bhavcopy always wins over broker data for daily candles.

Format (whitespace-padded):
SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE,
LAST_PRICE, CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS,
NO_OF_TRADES, DELIV_QTY, DELIV_PER
"""

import csv
import io
from datetime import date, datetime

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

BHAVCOPY_URL = (
    "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"
)
# NSE rejects default client UAs; be a polite browser and back off on 429/403.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "text/csv,*/*",
    "Referer": "https://www.nseindia.com/",
}

SERIES_ALLOWED = {"EQ", "BE", "BZ"}


def parse_bhavcopy(csv_text: str) -> list[dict]:
    """Pure parser: CSV text → normalized candle rows (EQ-family series only)."""
    rows: list[dict] = []
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        return rows
    # header cells can carry leading spaces
    reader.fieldnames = [f.strip() for f in reader.fieldnames]
    for raw in reader:
        row = {k.strip(): (v or "").strip() for k, v in raw.items()}
        if row.get("SERIES") not in SERIES_ALLOWED:
            continue
        try:
            rows.append(
                {
                    "ticker": row["SYMBOL"],
                    "ts": datetime.strptime(row["DATE1"], "%d-%b-%Y").date(),
                    "o": float(row["OPEN_PRICE"]),
                    "h": float(row["HIGH_PRICE"]),
                    "l": float(row["LOW_PRICE"]),
                    "c": float(row["CLOSE_PRICE"]),
                    "prev_close": float(row["PREV_CLOSE"]),
                    "v": int(row["TTL_TRD_QNTY"]),
                    "deliv_per": float(row["DELIV_PER"]) if row.get("DELIV_PER", "-") not in ("-", "") else None,
                }
            )
        except (KeyError, ValueError):
            continue  # malformed row; never let one bad line kill the ingest
    return rows


async def fetch_bhavcopy(for_date: date) -> str:
    url = BHAVCOPY_URL.format(ddmmyyyy=for_date.strftime("%d%m%Y"))
    async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


async def upsert_candles(session: AsyncSession, rows: list[dict]) -> int:
    """Upsert parsed rows into symbols + candles (tf='1D'). Returns row count."""
    if not rows:
        return 0
    # ensure symbols exist, then map ticker → id in one round-trip each
    await session.execute(
        text(
            "INSERT INTO symbols (ticker, exchange) "
            "SELECT DISTINCT x.ticker, 'NSE' FROM jsonb_to_recordset(CAST(:rows AS jsonb)) "
            "AS x(ticker text) "
            "ON CONFLICT (exchange, ticker) DO NOTHING"
        ),
        {"rows": _json([{"ticker": r["ticker"]} for r in rows])},
    )
    result = await session.execute(
        text(
            "INSERT INTO candles (symbol_id, tf, ts, o, h, l, c, v) "
            "SELECT s.id, '1D', x.ts::timestamptz, x.o, x.h, x.l, x.c, x.v "
            "FROM jsonb_to_recordset(CAST(:rows AS jsonb)) "
            "AS x(ticker text, ts date, o numeric, h numeric, l numeric, c numeric, v bigint) "
            "JOIN symbols s ON s.exchange = 'NSE' AND s.ticker = x.ticker "
            "ON CONFLICT (symbol_id, tf, ts) DO UPDATE "
            "SET o = excluded.o, h = excluded.h, l = excluded.l, "
            "    c = excluded.c, v = excluded.v"
        ),
        {
            "rows": _json(
                [
                    {k: (v.isoformat() if isinstance(v, date) else v)
                     for k, v in r.items() if k in ("ticker", "ts", "o", "h", "l", "c", "v")}
                    for r in rows
                ]
            )
        },
    )
    await session.commit()
    return result.rowcount or 0


async def ingest_bhavcopy(session: AsyncSession, for_date: date) -> int:
    """Full job body: download → parse → upsert. Idempotent."""
    csv_text = await fetch_bhavcopy(for_date)
    return await upsert_candles(session, parse_bhavcopy(csv_text))


def _json(obj: list[dict]) -> str:
    import json

    return json.dumps(obj)
