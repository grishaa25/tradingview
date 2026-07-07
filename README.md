# AI Trading Intelligence Platform

AI-powered trading analyst & research platform for Indian markets (NSE / BSE / MCX).
Decision support only — not a broker, not an auto-trading bot.

Full specs: [docs/PRD.md](docs/PRD.md) · [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · reference scanner config: [nse-trading-bot/rules.json](nse-trading-bot/rules.json)

## Hosting decisions (differs from the original architecture doc)

| Concern | Choice |
|---|---|
| Database + Auth | **Supabase** (hosted Postgres + Supabase Auth + RLS; no TimescaleDB — plain tables with BRIN indexes, pgvector enabled) |
| Frontend | **Next.js on Vercel** (root directory: `frontend/`) |
| Backend API + workers | FastAPI + APScheduler (containerized; deploy on any small host — Railway/Render/Fly/VPS). Connects to Supabase Postgres, verifies Supabase JWTs |

## Repository layout

```
├── frontend/               # Next.js 15 + TS + Tailwind (Vercel)
│   ├── app/                # routes: charts, scanner, options, impact,
│   │                       # portfolio, news, backtest, assistant, (auth)
│   ├── components/         # chart/ ui/ widgets/
│   └── lib/                # supabase clients, API client
├── backend/                # FastAPI modular monolith + workers
│   ├── app/
│   │   ├── core/           # config, db (async SQLAlchemy), Supabase JWT auth
│   │   ├── marketdata/     # ingest, broker adapters, candle API
│   │   ├── indicators/     # pandas-ta engine + custom composites
│   │   ├── scanner/        # rules.json schema, evaluator, runner, re-arm state
│   │   ├── options/ impact/ ai/ portfolio/ risk/ news/ backtest/ alerts/
│   │   └── workers/        # APScheduler job definitions
│   └── tests/
├── supabase/
│   ├── migrations/         # SQL migrations (schema + RLS policies)
│   └── seed.sql
├── infra/                  # local compose, litellm.yaml
├── nse-trading-bot/        # rules.json — reference scanner config
└── docs/                   # PRD, architecture, per-module docs
```

## Getting started

### 1. Database (Supabase)

1. Create a project at [supabase.com](https://supabase.com) (region: `ap-south-1` Mumbai for NSE latency).
2. Install the [Supabase CLI](https://supabase.com/docs/guides/cli), then:

```bash
supabase link --project-ref <project-ref>
supabase db push          # applies supabase/migrations/
```

Local development database instead: `supabase start` then `supabase db reset` (applies migrations + seed.sql).

### 2. Frontend (Vercel)

```bash
cd frontend
cp .env.local.example .env.local   # fill in Supabase URL + anon key
npm install
npm run dev                        # http://localhost:3000
```

Deploy: import the repo in Vercel, set **Root Directory = `frontend`**, add the
`NEXT_PUBLIC_*` env vars from `.env.local.example`.

### 3. Backend (FastAPI)

```bash
cd backend
cp .env.example .env               # Supabase DB URL, JWT secret, broker keys
pip install -e ".[dev]"
uvicorn app.main:app --reload      # http://localhost:8000/docs
```

Workers (scheduled jobs): `python -m app.workers.scheduler`

## Build order (Phase 1)

Follow docs/ARCHITECTURE.md §12 — data ingest → charts → indicators → scanner
(rules.json) → scheduler + Telegram alerts → AI chat. Each phase must be
daily-usable before the next starts (PRD §9).
