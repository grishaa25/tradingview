# AI Trading Intelligence Platform — Technical Architecture

Companion to `docs/PRD.md`. This document goes one level deeper: component design, data flows, folder structure, database DDL, the scanner engine internals, the AI layer, deployment, and the scaling path.

---

## 1. System Context

```
                        ┌─────────────────────────────────────────────┐
                        │                 USERS (browser)             │
                        └──────────────────────┬──────────────────────┘
                                               │ HTTPS / WSS
                        ┌──────────────────────▼──────────────────────┐
                        │        Caddy (TLS, reverse proxy)           │
                        │   app.yourdomain.in  →  Next.js / FastAPI   │
                        └───────┬──────────────────────────┬──────────┘
                                │                          │
                 ┌──────────────▼─────────┐   ┌────────────▼───────────────┐
                 │  Next.js frontend      │   │  FastAPI backend (uvicorn) │
                 │  (SSR + static)        │   │  REST + WebSocket          │
                 └────────────────────────┘   └───────┬────────────────────┘
                                                      │
        ┌──────────────┬──────────────┬───────────────┼────────────────┐
        │              │              │               │                │
┌───────▼──────┐ ┌─────▼──────┐ ┌─────▼─────┐ ┌───────▼──────┐ ┌───────▼───────┐
│ PostgreSQL16 │ │  Redis 7   │ │  Worker   │ │  Scheduler   │ │ LiteLLM proxy │
│ +TimescaleDB │ │ (cache +   │ │ (jobs:    │ │ (APScheduler │ │ (AI gateway)  │
│ +pgvector    │ │  pub/sub)  │ │  ingest,  │ │  cron defs)  │ │               │
│              │ │            │ │  scans,   │ │              │ │               │
└──────────────┘ └────────────┘ │  alerts)  │ └──────────────┘ └───────┬───────┘
                                └─────┬─────┘                          │
                                      │                     ┌──────────▼──────────┐
                 ┌────────────────────┼─────────────┐       │ Claude / DeepSeek / │
                 │                    │             │       │ Gemini / Ollama ... │
        ┌────────▼───────┐  ┌─────────▼──────┐ ┌────▼─────┐ └─────────────────────┘
        │ Broker APIs    │  │ NSE/BSE files  │ │ RSS/News │
        │ (Angel One,    │  │ (bhavcopy, F&O │ │ feeds    │
        │  Dhan: REST+WS)│  │  lists, bans)  │ │          │
        └────────────────┘  └────────────────┘ └──────────┘
```

All backend components run as containers on **one VPS** via Docker Compose. The frontend can live on Vercel's free tier or be served by the same VPS — both paths are supported by the repo layout.

---

## 2. Repository Layout (monorepo)

```
platform/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app factory, router mounting
│   │   ├── core/
│   │   │   ├── config.py            # pydantic-settings, .env driven
│   │   │   ├── db.py                # async SQLAlchemy engine/session
│   │   │   ├── redis.py             # redis client + pub/sub helpers
│   │   │   ├── security.py          # JWT, password hashing, Fernet
│   │   │   └── deps.py              # FastAPI dependencies (auth, db)
│   │   ├── auth/        {router,service,models,schemas}.py
│   │   ├── marketdata/
│   │   │   ├── router.py            # /candles /quote /symbols, WS /stream
│   │   │   ├── service.py
│   │   │   ├── models.py            # symbols, candles (hypertable)
│   │   │   ├── ingest/
│   │   │   │   ├── bhavcopy.py      # EOD NSE files → candles + metadata
│   │   │   │   ├── broker_ws.py     # live ticks → 1m candles → Redis
│   │   │   │   ├── backfill.py      # historical API backfill (rate-limited)
│   │   │   │   └── reconcile.py     # nightly broker-vs-bhavcopy check
│   │   │   └── adapters/
│   │   │       ├── base.py          # BrokerDataInterface (ABC)
│   │   │       ├── angelone.py
│   │   │       └── dhan.py
│   │   ├── indicators/
│   │   │   ├── router.py
│   │   │   ├── engine.py            # pandas-ta wrappers, caching
│   │   │   └── custom/              # rel-strength, VCP, Minervini, gaps...
│   │   ├── scanner/
│   │   │   ├── router.py
│   │   │   ├── schema.py            # pydantic models of rules.json format
│   │   │   ├── evaluator.py         # condition tree evaluation
│   │   │   ├── runner.py            # universe iteration, scheduling hooks
│   │   │   └── state.py             # re-arm state machine per (scan,symbol)
│   │   ├── options/
│   │   │   ├── router.py
│   │   │   ├── chain.py             # snapshot ingestion + queries
│   │   │   ├── greeks.py            # py_vollib Black-76
│   │   │   ├── analytics.py         # PCR, max pain, IV rank, GEX/DEX
│   │   │   └── strategy.py          # legs → payoff, breakevens, POP
│   │   ├── impact/                  # Nifty Impact Engine
│   │   │   ├── router.py
│   │   │   ├── weights.py           # constituent weight ingestion
│   │   │   └── engine.py            # move → index points math
│   │   ├── ai/
│   │   │   ├── router.py            # /ai/chat (SSE)
│   │   │   ├── gateway.py           # LiteLLM client, task→model routing
│   │   │   ├── tools.py             # tool registry (run_scan, get_candles…)
│   │   │   ├── prompts/             # system prompts per task, versioned
│   │   │   └── budget.py            # token spend tracking + hard cap
│   │   ├── portfolio/   {router,service,models}.py + journal.py
│   │   ├── risk/        sizing.py, var.py, montecarlo.py, correlation.py
│   │   ├── news/
│   │   │   ├── poller.py            # RSS fetch + dedupe (hash)
│   │   │   ├── tagger.py            # cheap-LLM entity/sector/sentiment
│   │   │   ├── impact_kb.py         # theme → stocks knowledge base (yaml)
│   │   │   └── router.py
│   │   ├── backtest/
│   │   │   ├── router.py
│   │   │   ├── engine.py            # vectorbt harness
│   │   │   └── translate.py         # rules.json → vectorbt signals
│   │   ├── alerts/
│   │   │   ├── router.py
│   │   │   ├── dispatcher.py        # signal/event → channel fanout
│   │   │   └── channels/telegram.py, email.py, discord.py
│   │   └── workers/
│   │       ├── scheduler.py         # APScheduler job definitions (see §6)
│   │       └── jobs.py              # job bodies, all idempotent
│   ├── tests/                       # mirrors app/ structure
│   ├── alembic/                     # migrations
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── app/                         # Next.js App Router
│   │   ├── (auth)/login, register
│   │   ├── charts/[symbol]/
│   │   ├── scanner/                 # scan builder UI + results
│   │   ├── options/[symbol]/        # chain, analytics, strategy builder
│   │   ├── impact/                  # Nifty Impact calculator
│   │   ├── portfolio/               # holdings, journal, risk
│   │   ├── news/
│   │   ├── backtest/
│   │   └── assistant/               # AI chat
│   ├── components/
│   │   ├── chart/                   # Lightweight Charts wrapper + drawings
│   │   ├── ui/                      # shadcn
│   │   └── widgets/                 # dashboard tiles (Phase 5 drag/drop)
│   ├── lib/api.ts                   # typed client (generated from OpenAPI)
│   └── Dockerfile
├── infra/
│   ├── compose.yml
│   ├── Caddyfile
│   ├── litellm.yaml                 # task→model routing config
│   └── backup.sh                    # pg_dump → R2 (cron)
├── nse-trading-bot/
│   └── rules.json                   # reference scanner config (this repo)
└── docs/
    ├── PRD.md
    ├── ARCHITECTURE.md              # this file
    └── modules/                     # one doc per module as it ships
```

---

## 3. Core Data Flows

### 3.1 Market data ingestion

```
[09:15–15:30 IST]
Broker WebSocket (Angel One / Dhan)
   │ ticks (LTP, vol, OI) for subscribed F&O universe
   ▼
broker_ws.py ── aggregates ──► 1-min candles (in-memory bar builder)
   │                                 │ on bar close
   │ every tick                      ▼
   ▼                          INSERT INTO candles (1m)
Redis SET quote:{symbol}             │ rollups on read or scheduled
Redis PUBLISH stream:{symbol}        ▼
   │                          5m/15m/60m/1D derived via time_bucket()
   ▼
WS /stream fanout to browsers

[~18:30 IST daily]
bhavcopy.py: download NSE EOD files ─► upsert daily candles, delivery %,
F&O universe refresh, ban list, lot sizes ─► reconcile.py flags any
mismatch between broker 1D candles and official close.
```

Key decisions:
- 1-minute bars are the atomic stored unit intraday; everything coarser is derived with TimescaleDB `time_bucket()` (no duplicate storage).
- The official bhavcopy always wins for daily candles (broker data corrected nightly).
- Backfill runs the same code path as live ingestion → one write path, one schema.

### 3.2 Scan cycle (the rules.json loop)

```
Scheduler: cron on hourly candle close (10:15, 11:15 … 15:15 IST)
   │
   ▼
runner.py
   1. Resolve universe (full F&O  or  top-50 by 30d avg traded value;
      minus ban-period stocks)                      ← symbols + nightly stats
   2. Bulk-load candles for both timeframes (1D, 60) for all symbols
   3. Compute indicators once per (symbol, tf): rsi_daily, rsi_hourly,
      sma50_hourly                                  ← indicators/engine.py
   4. evaluator.py: for each symbol, evaluate BUY tree then SELL tree
      (ALL logic → short-circuit on first false condition)
   5. state.py re-arm check:
        armed  + all true  → FIRE signal, state=fired
        fired  + any false → state=armed  (re-armed, no signal)
        fired  + all true  → no-op        (prevents duplicate alerts)
   6. INSERT signals (with full condition snapshot JSON)
   7. Redis PUBLISH signals.new
   ▼
alerts/dispatcher.py (subscribed) → Telegram sendMessage
   "🟢 BUY RELIANCE | RSI(D) 64.2 >60 ✓ | RSI(1H) 61.8 >60 ✓ |
    Close 2,912 > PrevClose 2,871 ✓ | 2,912 > SMA50(1H) 2,867 ✓"
```

The evaluator understands the exact `nse-trading-bot/rules.json` schema:
- `indicator/operator/value` conditions (threshold checks),
- `left/right` operand conditions with `{timeframe, field, offset}` or `{indicator}` operands (cross-references like close[0] > close[1], close > sma50),
- `logic: ALL|ANY` grouping, per-side triggers with `immediate` mode and re-arm semantics.

The same schema compiles to vectorbt boolean arrays in `backtest/translate.py` — **any scan is backtestable with zero re-authoring**.

### 3.3 AI chat with tool-calling

```
Browser ── POST /ai/chat (SSE) ──► ai/router.py
   │                                  │
   │                                  ▼
   │                     gateway.py: task=chat_assistant → model from
   │                     litellm.yaml (e.g. claude-sonnet-5)
   │                                  │  system prompt + tool schemas
   │                                  ▼
   │                     LLM responds with tool_call, e.g.
   │                     run_scan({"universe":"BANKNIFTY_CONSTITUENTS",
   │                               "conditions":[...rsi>60...]})
   │                                  │
   │                                  ▼
   │                     tools.py executes against internal services
   │                     (never raw SQL, never external calls)
   │                                  │ structured JSON result
   │                                  ▼
   │                     LLM writes the explanation over real numbers
   ▼                                  │
 SSE stream: tokens + tool-status events + final structured payload
 (frontend renders tables/charts from the payload, not from prose)
```

Guardrails: tool registry is an allowlist; results are truncated/paginated before hitting the context; per-user and global monthly token budgets enforced in `budget.py`; every message logged with token cost.

### 3.4 News intelligence pipeline

```
poller.py (every 5–15 min) ─► fetch RSS feeds ─► SHA-256 dedupe ─► news_items
    ▼
tagger.py batch job: cheap model (DeepSeek/Gemini Flash) with a strict JSON
schema → {symbols[], sectors[], event_type, sentiment, materiality 0–5}
    ▼ stored in news_tags (+ embedding into pgvector for semantic search)
impact_kb.py: theme→beneficiary mapping (YAML, human-curated, e.g.
"ev_subsidy" → [TATAMOTORS, M&M, EXIDEIND, ARE&M, SONACOMS])
    ▼
materiality ≥ threshold AND symbol ∈ user watchlist/portfolio → alert
```

### 3.5 Option chain snapshots

```
Every 3–5 min during market hours, per F&O symbol batch:
broker option-chain API ─► normalize ─► chain_snapshots (append-only)
                                            │
             ┌──────────────────────────────┤ derived on read/cron
             ▼                              ▼
   IV history table (per symbol,      analytics: PCR, max pain,
   ATM IV daily close → IV rank/      OI buildup classification,
   percentile after history accrues)  GEX/DEX curves
```

Append-only snapshots are the raw truth; all analytics are derived views. Start this on day one of Phase 2 — IV rank needs months of history and it can't be bought for free.

---

## 4. Database DDL (core, Phase 1–2)

```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE symbols (
  id            serial PRIMARY KEY,
  ticker        text NOT NULL,
  exchange      text NOT NULL DEFAULT 'NSE',
  name          text,
  isin          text,
  sector        text,
  fno_flag      boolean DEFAULT false,
  lot_size      int,
  index_memberships jsonb DEFAULT '[]',
  UNIQUE (exchange, ticker)
);

CREATE TABLE candles (
  symbol_id  int  NOT NULL REFERENCES symbols(id),
  tf         text NOT NULL,            -- '1m','60','1D'
  ts         timestamptz NOT NULL,
  o numeric(12,2), h numeric(12,2), l numeric(12,2), c numeric(12,2),
  v bigint, oi bigint,
  PRIMARY KEY (symbol_id, tf, ts)
);
SELECT create_hypertable('candles', 'ts', chunk_time_interval => INTERVAL '7 days');
ALTER TABLE candles SET (timescaledb.compress,
  timescaledb.compress_segmentby = 'symbol_id, tf');
SELECT add_compression_policy('candles', INTERVAL '30 days');

CREATE TABLE liquidity_stats (           -- drives top_liquid_50 filter
  symbol_id int REFERENCES symbols(id),
  asof_date date,
  avg_traded_value_30d numeric(18,2),
  rank int,
  PRIMARY KEY (symbol_id, asof_date)
);

CREATE TABLE index_weights (
  index_name text, symbol_id int REFERENCES symbols(id),
  weight numeric(8,5), free_float numeric(8,5), asof_date date,
  PRIMARY KEY (index_name, symbol_id, asof_date)
);

CREATE TABLE scans (
  id serial PRIMARY KEY,
  user_id int REFERENCES users(id),
  name text, rules jsonb NOT NULL,       -- rules.json schema
  enabled boolean DEFAULT true,
  schedule text DEFAULT 'on_hourly_candle_close'
);

CREATE TABLE scan_state (                -- re-arm state machine
  scan_id int, symbol_id int, side text, -- 'buy'|'sell'
  state text DEFAULT 'armed',            -- 'armed'|'fired'
  updated_at timestamptz,
  PRIMARY KEY (scan_id, symbol_id, side)
);

CREATE TABLE signals (
  id bigserial PRIMARY KEY,
  scan_id int REFERENCES scans(id),
  symbol_id int REFERENCES symbols(id),
  side text, ts timestamptz,
  snapshot jsonb,                        -- every condition's actual values
  delivered_at timestamptz
);

CREATE TABLE chain_snapshots (
  symbol_id int, expiry date, strike numeric(12,2), opt_type char(2),
  ts timestamptz,
  ltp numeric(12,2), oi bigint, oi_chg bigint, iv numeric(8,4),
  volume bigint, bid numeric(12,2), ask numeric(12,2),
  PRIMARY KEY (symbol_id, expiry, strike, opt_type, ts)
);
SELECT create_hypertable('chain_snapshots', 'ts');

CREATE TABLE news_items (
  id bigserial PRIMARY KEY,
  source text, url text, title text, body text,
  published_at timestamptz, hash text UNIQUE
);
CREATE TABLE news_tags (
  news_id bigint REFERENCES news_items(id),
  symbol_id int NULL REFERENCES symbols(id),
  sector text, event_type text, sentiment text,
  materiality smallint, ai_meta jsonb,
  embedding vector(384)
);

-- users, watchlists, portfolios, trades, alerts, backtests,
-- ai_conversations, audit_log: as listed in PRD §7.
```

---

## 5. Scanner Engine Internals

### 5.1 Rule schema (pydantic mirror of rules.json)

```python
class Operand(BaseModel):
    timeframe: str | None = None   # '1D' | '60'
    field: str | None = None       # 'close','open','high','low','volume'
    offset: int = 0                # 0 = current, 1 = previous bar
    indicator: str | None = None   # id from indicators[] block

class Condition(BaseModel):
    id: str
    indicator: str | None = None   # shorthand: indicator OP value
    operator: Literal['>','<','>=','<=','==','crosses_above','crosses_below']
    value: float | None = None
    left: Operand | None = None    # general: left OP right
    right: Operand | None = None

class SignalSide(BaseModel):
    logic: Literal['ALL','ANY']
    conditions: list[Condition]
    trigger: Trigger               # mode: immediate; re-arm semantics
```

### 5.2 Evaluation

- All indicator series for the scan pass are computed **once per (symbol, timeframe)** and shared across conditions (memoized in the pass context).
- `ALL` logic short-circuits; the snapshot still records every condition's actual value for fired signals (evaluate-all on fire, short-circuit on reject — rejects are the hot path across ~190 F&O symbols).
- `crosses_above/below` compare bar N and N-1 relations — needed for EMA-cross scans, free to support in the same schema.
- Deterministic and pure: `(candles, rules) → signals`. This is what makes the backtest translation trivial and the engine unit-testable with golden files.

### 5.3 Performance envelope

~190 F&O symbols × 2 timeframes × ≤300 bars ≈ trivial for pandas on a 4-vCPU VPS: a full scan pass completes in well under 10 seconds. No distributed anything required. The nightly EOD pass over years of history for backtests uses vectorbt's vectorized path instead.

---

## 6. Scheduled Jobs (APScheduler, IST)

| Job | Schedule | Body |
|---|---|---|
| `broker_ws_supervisor` | market hours, watchdog | keep tick stream alive, resubscribe on drop |
| `hourly_scan_pass` | 10:15…15:15 + 15:30 | run all enabled scans (rules.json loop) |
| `chain_snapshot` | every 5 min, market hours | option chains for F&O universe |
| `eod_bhavcopy` | 18:30 daily | EOD ingest, universe/ban/lot refresh |
| `liquidity_rank` | 19:00 daily | 30-day avg traded value → top-50 ranks |
| `reconcile` | 19:30 daily | broker vs bhavcopy close check |
| `news_poll` | every 10 min | RSS fetch + dedupe |
| `news_tag_batch` | every 15 min | LLM tagging of untagged items |
| `iv_daily_close` | 15:35 daily | ATM IV close → IV history |
| `signal_outcomes` | 19:45 daily | label past signals with 1/5/20-day returns |
| `db_backup` | 02:00 daily | pg_dump → Cloudflare R2 |

All jobs idempotent (safe to re-run) and logged to `job_runs` with duration + status; Uptime Kuma pings a heartbeat URL per critical job.

---

## 7. AI Layer Design

```yaml
# infra/litellm.yaml
model_list:
  - model_name: bulk        # high-volume, low-stakes
    litellm_params: { model: deepseek/deepseek-chat }
  - model_name: interactive # user-facing analysis
    litellm_params: { model: anthropic/claude-sonnet-5 }
  - model_name: free-tier
    litellm_params: { model: gemini/gemini-2.0-flash }
router_settings:
  budget: { max_monthly_usd: 20, alert_at_pct: 80 }
task_routing:            # consumed by gateway.py
  news_tagging: bulk
  daily_summary: free-tier
  chat_assistant: interactive
  chart_analysis: interactive
  filing_summary: bulk
```

Design rules (enforced in code review, not just convention):
1. **No business logic in prompts.** Indicators, Greeks, VaR, impact math live in Python; the model explains, ranks, and converses.
2. **Structured in, structured out.** Tools return JSON; user-facing numbers are rendered by the frontend from tool payloads, never parsed out of model prose.
3. **Every task has a versioned prompt file** under `ai/prompts/` — prompt changes are code-reviewed diffs.
4. **Cache aggressively.** Tag results, summaries, and explanations are keyed by input hash in Postgres.
5. **Provider swap = config change.** Nothing imports an AI SDK except `gateway.py`.

---

## 8. Frontend Architecture

- **State:** TanStack Query for all server state (candles, chains, signals); Zustand only for UI state (layout, selected symbol, drawing mode).
- **Charts:** one `<TVChart>` wrapper around Lightweight Charts owning series lifecycle; indicator panes as stacked chart instances synced by a shared time-scale controller; drawings stored as normalized shapes `{type, points[{time, price}], style}` in the DB and re-hydrated onto the chart — this is the largest single frontend component, budget it accordingly.
- **Live data:** one multiplexed WebSocket (`/stream`), subscribe/unsubscribe messages per symbol; TanStack Query cache patched on tick.
- **AI chat:** SSE consumption with incremental rendering; tool-call events render as inline result cards (scan tables, mini-charts) from the structured payload.
- **Type safety:** OpenAPI schema → generated TS client (`openapi-typescript`), so backend refactors surface as frontend compile errors.
- **Theming:** dark-first, CSS variables; Bloomberg-ish density toggle later.

---

## 9. Deployment

### 9.1 docker-compose (sketch)

```yaml
services:
  db:
    image: timescale/timescaledb-ha:pg16
    volumes: [dbdata:/home/postgres/pgdata]
    env_file: .env
  redis:
    image: redis:7-alpine
  api:
    build: ../backend
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
    depends_on: [db, redis]
    env_file: .env
  worker:
    build: ../backend
    command: python -m app.workers.scheduler
    depends_on: [db, redis]
    env_file: .env
  litellm:
    image: ghcr.io/berriai/litellm:main-latest
    volumes: [./litellm.yaml:/app/config.yaml]
    env_file: .env
  frontend:            # omit if using Vercel
    build: ../frontend
  caddy:
    image: caddy:2
    ports: ["80:80", "443:443"]
    volumes: [./Caddyfile:/etc/caddy/Caddyfile, caddydata:/data]
volumes: { dbdata: {}, caddydata: {} }
```

### 9.2 CI/CD (GitHub Actions, free tier)

```
PR:    ruff + mypy + pytest  |  tsc + eslint + next build  → required checks
main:  build images → push GHCR → ssh VPS →
       docker compose pull && docker compose up -d && alembic upgrade head
```

Rollback = redeploy previous image tag. Migrations are always backward-compatible for one release (expand → migrate → contract).

### 9.3 Backups & DR

- Nightly `pg_dump -Fc` → Cloudflare R2 (free 10 GB), 14-day retention; weekly restore-test job into a scratch container (a backup that's never restored is a hope, not a backup).
- `.env` secrets mirrored in a password manager; infra is rebuildable from repo + backup in under an hour.

---

## 10. Security Architecture

| Layer | Control |
|---|---|
| Transport | TLS everywhere (Caddy/Let's Encrypt); HSTS |
| AuthN | JWT access (15 min) + refresh (30 d, rotating, httpOnly cookie); Google OAuth via authlib |
| AuthZ | per-user row ownership enforced in services; `admin` flag; RBAC table when multi-user |
| Secrets | `.env` on VPS (root-only) + SOPS-encrypted copy in repo; broker keys Fernet-encrypted at rest, decrypted only in adapter processes |
| AI boundary | allowlisted tools; no raw SQL/file/network tools; broker credentials never enter model context |
| Rate limiting | slowapi: auth 5/min, AI 20/hr/user, API 120/min |
| Audit | `audit_log` rows for auth events, config changes, alert changes, (later) anything execution-adjacent |
| Supply chain | dependabot + `pip-audit`/`npm audit` in CI |

---

## 11. Scaling Path (trigger-based, not speculative)

| Trigger (measured) | Action | New cost |
|---|---|---|
| API p95 > 500 ms sustained | Bigger VPS (vertical) | +₹500–1k/mo |
| DB CPU-bound during scans | Split DB to second VPS | +₹700/mo |
| >~50 concurrent WS users | Dedicated stream process + Redis pub/sub fanout (already the design — just scale the container) | ~₹0 |
| Multi-node workers needed | Redis + RQ replaces in-process APScheduler executors (job bodies unchanged) | ~₹0 |
| Real HA requirement (paying users) | Managed Postgres + 2 app nodes + LB | +₹4–6k/mo |
| Team > 3, deploy contention | Then and only then: k8s/nomad conversation | — |

The modular-monolith boundaries (§2) are what make each step mechanical: every module already owns its models, services, and router; extraction is a repo move plus an HTTP/queue boundary, not a rewrite.

---

## 12. Build Order Inside Phase 1 (first 6 weeks, concrete)

1. **Week 1:** compose stack up on VPS; auth; symbols table seeded from NSE F&O list; bhavcopy job writing daily candles.
2. **Week 2:** broker adapter (historical): backfill 2y daily + 1y hourly for F&O universe; candle API; first chart on screen.
3. **Week 3:** indicator engine (RSI, SMA/EMA, MACD, ATR, Bollinger, Supertrend) + tests against known-good values; chart overlays.
4. **Week 4:** scanner schema + evaluator + golden-file tests; `nse-trading-bot/rules.json` loaded as scan #1; manual `POST /scans/1/run` works end-to-end.
5. **Week 5:** scheduler + hourly passes; re-arm state; Telegram alerts; liquidity-rank job (top-50 filter live).
6. **Week 6:** live quotes WS + streaming chart; AI chat v1 with `run_scan`/`get_candles`/`get_indicators` tools; hardening + a full trading week of daily use (Definition of Done).
