# Quickstart — zero to running scanner in ~30 minutes, ₹0

Everything below uses **free, keyless data** (Yahoo Finance + NSE bhavcopy).
No broker account needed. TradingView Pro is used for charts and webhook alerts.

## 1. Supabase (once, ~10 min)

1. Create a project at supabase.com → region **ap-south-1 (Mumbai)**.
2. From **Settings → API** note: Project URL, `anon` key, `service_role` key, JWT Secret.
3. From **Settings → Database → Connection string** copy the Session-pooler URI.
4. Apply the schema:
   ```bash
   npm install -g supabase
   supabase login
   supabase link --project-ref <ref>
   supabase db push        # applies all migrations in supabase/migrations/
   ```

## 2. Backend

```bash
cd backend
cp .env.example .env      # fill: DATABASE_URL (postgresql+asyncpg://...),
                          #       SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY,
                          #       SUPABASE_JWT_SECRET, WEBHOOK_SECRET (any random string)
pip install -e ".[dev]"
uvicorn app.main:app --reload            # → http://localhost:8000/docs
```

## 3. Frontend

```bash
cd frontend
cp .env.local.example .env.local          # NEXT_PUBLIC_* values from step 1
npm install && npm run dev                # → http://localhost:3000
```

Register at `/register`, confirm the email Supabase sends, sign in.

## 4. Get data + run the scanner (all on http://localhost:8000/docs)

Click **Authorize** and paste your Supabase access token. To get it: sign in
on the frontend, open browser devtools → Console →
`JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k=>k.endsWith("-auth-token")))).access_token`

Then, in order:

| # | Call | What it does |
|---|---|---|
| 1 | `POST /marketdata/admin/seed-universe` | loads ~180 F&O symbols |
| 2 | `POST /marketdata/admin/backfill?tickers=RELIANCE,TCS,HDFCBANK,INFY,ICICIBANK` | pulls 2y daily + 6mo hourly from Yahoo (seconds). Omit `tickers` for the full universe (~4 min) |
| 3 | `POST /scans` with the JSON body of `nse-trading-bot/rules.json` | creates scan #1 |
| 4 | `POST /scans/1/run` | full dual-timeframe scan pass — returns fired signals with condition values |

Now open `localhost:3000/scanner` (live signal list) and
`localhost:3000/charts/RELIANCE` (platform chart ↔ TradingView tab).

## 5. Automate it

```bash
cd backend && python -m app.workers.scheduler
```
Runs (IST, Mon–Fri): Yahoo refresh :10 past each market hour → scan pass at
:15 → official NSE bhavcopy at 18:30 → liquidity ranks 19:00 → signal
outcome labeling 19:45.

## 6. Telegram alerts (~2 min, free)

1. Message **@BotFather** → `/newbot` → copy the token into `TELEGRAM_BOT_TOKEN`.
2. Message your new bot once, then message **@userinfobot** → copy your id into `TELEGRAM_CHAT_ID`.
3. Restart backend + scheduler. Fired signals now ping your phone.

## 7. TradingView Pro webhooks (optional)

In any TradingView alert, set the webhook URL to
`https://<your-backend-host>/alerts/webhooks/tradingview?secret=<WEBHOOK_SECRET>`
and the message to:
```json
{"ticker": "{{ticker}}", "side": "buy", "price": {{close}}, "note": "my setup"}
```
Alerts are stored in `webhook_events` and forwarded to Telegram instantly.
(Requires the backend to be reachable from the internet — fine once deployed;
for local testing use `ngrok http 8000`.)

## Data sources & costs

| Data | Source | Cost | Notes |
|---|---|---|---|
| Daily + hourly candles | Yahoo Finance chart API | ₹0, no key | ~15 min delayed; perfect for scanning |
| Official daily OHLCV | NSE bhavcopy (18:30 IST) | ₹0 | overwrites Yahoo daily candles nightly |
| F&O universe + lot sizes | NSE fo_mktlots.csv | ₹0 | static seed included as fallback |
| Charts + manual alerts | TradingView (your Pro) | already paid | embed + webhooks integrated |
| Real-time ticks, option chain | Angel One / Dhan API | ₹0 with account | the upgrade path when you want live data |
