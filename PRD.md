# AI Trading Intelligence Platform — PRD & Build Plan (Minimum-Cost Edition)

**Product:** AI-powered trading analyst & research platform for Indian markets (NSE / BSE / MCX)
**Positioning:** TradingView + Sensibull + Trendlyne + Screener + ChatGPT in one app. Decision support only — not a broker, not an auto-trading bot (execution is a later optional module).
**Author:** Grisha Saini · **Date:** 2026-07-07 · **Status:** Draft v1

---

## 1. Executive Summary

Build a standalone web platform (later desktop) with its own backend, database, AI layer, market-data engine, scanner, options analytics, portfolio tracking, news intelligence, and backtesting. TradingView becomes just one optional data source. The AI layer is provider-agnostic: swap Claude / GPT / Gemini / DeepSeek / local Llama by changing one config value.

**The single most important strategic decision:** build in phases where each phase ships a working product you actually use daily. The #1 failure mode for projects of this scope is building all 15 modules at 20% depth. Phase 1 alone (data + charts + scanner + AI chat) already replaces 80% of your daily TradingView/ChartInk usage.

**Minimum-cost philosophy:**
- One VPS, not Kubernetes. Docker Compose, not a cluster. Postgres for everything (queue, cache, search) until scale forces otherwise.
- Free data sources first (NSE bhavcopy, broker APIs that come free with a trading account), paid feeds never in Phase 1–3.
- Pay-per-token AI with cheap models for routine tasks, expensive models only for deep analysis.
- Target running cost: **₹500–1,500/month (~$6–18)** until you have real users.

---

## 2. Goals & Non-Goals

### Goals
1. Real-time-ish and historical market data for NSE equity, F&O, indices (BSE/MCX later).
2. Professional charting with indicators and drawing tools.
3. A scanner engine (ChartInk-class) with multi-timeframe conditions — the `rules.json` momentum scanner is the first built-in strategy.
4. Options analytics: option chain, OI, IV, Greeks, PCR, max pain, strategy builder with payoff diagrams.
5. Nifty Impact Engine (heavyweight move → index points).
6. AI assistant that reasons over structured data produced by the platform (never invents prices).
7. News/earnings/economic-calendar intelligence with sector/stock impact mapping.
8. Portfolio tracking, risk metrics, trade journal.
9. Backtesting with standard performance stats.
10. Alerts via Telegram (free) first; email next; WhatsApp/push later.

### Non-Goals (initially)
- Order execution, broker order routing (Phase 6+, only after explicit go-ahead).
- Mobile native apps (responsive web first).
- 100k concurrent users on day one — architect so scaling is *possible*, don't pay for it now.
- Tick-by-tick market depth storage.

---

## 3. Users & Personas

| Persona | Needs | Priority |
|---|---|---|
| **You (power user / builder)** | Scanner, options analytics, AI analysis, journal | P0 |
| Swing/positional trader | Scans, alerts, watchlists, charts | P0 |
| Options seller | Chain, IV rank, Greeks, payoff, max pain | P1 |
| Investor/researcher | Fundamentals, earnings, news impact | P2 |

Design everything for persona #1 first. You are the customer; if you stop using it, the product is wrong.

---

## 4. Architecture

### 4.1 Principle
Modular monolith first, microservices never (until revenue demands it). Same clean module boundaries as the target architecture, but deployed as one FastAPI app + workers. Each module is a Python package with its own router, models, and services — extraction into a separate service later is mechanical.

```
┌───────────────────────────────────────────────┐
│  Frontend: Next.js + TS + Tailwind + shadcn   │
│  TradingView Lightweight Charts + Recharts    │
└───────────────┬───────────────────────────────┘
                │ REST + WebSocket (JWT)
┌───────────────▼───────────────────────────────┐
│  FastAPI modular monolith                     │
│  ├─ auth/            (JWT, Google OAuth)      │
│  ├─ marketdata/      (ingest, OHLCV API, WS)  │
│  ├─ indicators/      (pandas-ta / TA-Lib)     │
│  ├─ scanner/         (rule engine, rules.json │
│  │                    compatible schema)      │
│  ├─ options/         (chain, Greeks, IV, PCR) │
│  ├─ impact/          (Nifty Impact Engine)    │
│  ├─ ai/              (LiteLLM provider layer) │
│  ├─ portfolio/       (holdings, P&L, journal) │
│  ├─ risk/            (sizing, VaR, MC sim)    │
│  ├─ news/            (RSS ingest + AI tagging)│
│  ├─ backtest/        (vectorbt engine)        │
│  └─ alerts/          (Telegram, email)        │
├───────────────────────────────────────────────┤
│  Workers: APScheduler / Celery-lite jobs      │
│  (EOD ingest, scans, news poll, alerts)       │
├───────────────────────────────────────────────┤
│  PostgreSQL 16 + TimescaleDB (candles,        │
│  everything else) · Redis (live quotes cache) │
└───────────────────────────────────────────────┘
```

### 4.2 Minimum-cost substitutions vs. the "big" stack

| Big-company choice | Minimum-cost choice | Why | When to upgrade |
|---|---|---|---|
| Kubernetes + AWS | 1 VPS (Hetzner CX32 / Contabo, 4 vCPU 8GB, ~₹600–1,100/mo) + Docker Compose | K8s costs money and time, adds zero value < 1k users | >5k users or need HA |
| Kafka / RabbitMQ | Postgres-backed job table + APScheduler (or Redis + RQ) | A queue with 1 consumer is a cron job | Multi-node workers |
| MinIO/S3 | VPS disk; Cloudflare R2 (free 10GB) for backups | Nothing large to store yet | User uploads at scale |
| Managed Postgres | Postgres in Docker + nightly `pg_dump` to R2 | ₹0 vs ₹2,500+/mo | Revenue exists |
| Microservices | Modular monolith | 10× less ops, same code boundaries | Team > 3 devs |
| Paid data feed (₹3–25k/mo) | NSE bhavcopy + broker API (free w/ account) | Free covers EOD + quotes + chain | True realtime SLA needed |
| CDN/hosting for frontend | Vercel free tier (or serve from VPS via Caddy) | ₹0 | Team plan needs |

### 4.3 AI provider abstraction

Use **LiteLLM** (open source) as the single gateway. Every module calls `ai.complete(task, payload)`; a YAML config maps task → model:

```yaml
ai:
  default_provider: deepseek          # change one line to switch
  tasks:
    news_tagging:    deepseek/deepseek-chat      # cheap, high volume
    chart_analysis:  anthropic/claude-sonnet-5   # quality where it matters
    daily_summary:   gemini/gemini-flash         # free-tier eligible
    chat_assistant:  anthropic/claude-sonnet-5
    embeddings:      local/bge-small             # free, runs on VPS
```

Rules:
- The AI never computes indicators or prices — it receives structured JSON the engines produced and explains/ranks/summarizes.
- Route high-volume/low-stakes tasks (news tagging, summaries) to cheap models (DeepSeek ≈ $0.14/M input tokens; Gemini Flash free tier). Reserve premium models for interactive analysis.
- Cache AI outputs (news tags, daily summaries) in Postgres — never pay twice for the same input.
- Budget guardrail: hard monthly token spend cap in LiteLLM config. Realistic Phase 1–3 AI bill: **$3–15/month**.

---

## 5. Data Strategy (the make-or-break section)

### 5.1 Sources — free tier

| Data | Source | Cost | Notes |
|---|---|---|---|
| EOD OHLCV + delivery % (all NSE) | NSE bhavcopy (official daily files) | Free | One scheduled download at ~6:30 PM IST |
| Intraday 1-min/5-min/60-min history | Broker API (Angel One SmartAPI / Dhan / Upstox — free with account; Zerodha Kite Connect is ₹2,000/mo, avoid) | Free | Angel One + Dhan both give free historical + live APIs |
| Live quotes (LTP, market feed) | Broker WebSocket feed (same APIs) | Free | 1 connection, subscribe to F&O universe |
| Option chain, OI, IV | Broker API; NSE website JSON as fallback | Free | NSE JSON is unofficial — rate-limit politely, expect breakage; broker API is the reliable path |
| Index constituents & weights | NSE/AMFI monthly files | Free | Needed for the Impact Engine |
| F&O universe + lot sizes + ban list | NSE daily files | Free | Drives scanner universe & liquidity filter |
| Corporate actions, results calendar | NSE/BSE announcements feeds | Free | |
| News | RSS (Moneycontrol, ET Markets, Business Standard, LiveMint, PIB, RBI, SEBI press releases) | Free | Poll every 5–15 min |
| Economic calendar | RBI/MoSPI/Fed published schedules (scrape once per month) | Free | |
| Fundamentals | Quarterly results from NSE filings; screener-style ratios computed in-house later | Free | Phase 4 |

**Decision:** open one account with **Angel One** (free SmartAPI) and one with **Dhan** (free API) — two free, redundant data paths. Total data cost: **₹0/month**.

### 5.2 Storage
- **TimescaleDB** (Postgres extension, free) hypertable `candles(symbol, tf, ts, o, h, l, c, v, oi)` with compression — years of 1-min data for ~200 F&O symbols fits in a few GB.
- Backfill: 2–5 years daily + 1–2 years hourly for F&O universe via broker historical API (rate-limited script, runs over a weekend).
- Redis: last-tick cache + pub/sub fanout to WebSocket clients. (If trimming further, Postgres LISTEN/NOTIFY works too.)

### 5.3 Data quality
- Nightly reconciliation: broker candles vs bhavcopy close; flag mismatches.
- Corporate-action adjustment table; adjust on read, keep raw data immutable.

---

## 6. Module Specifications

### 6.1 Market Data Engine (P0)
- Ingest workers: EOD bhavcopy job, intraday candle poller/builder from broker WS ticks, option-chain snapshotter (every 3–5 min during market hours).
- API: `GET /candles/{symbol}?tf=1D&from=&to=`, `GET /quote/{symbol}`, `WS /stream` (subscribe by symbol list).

### 6.2 Indicator Engine (P0)
- `pandas-ta` (free) for the standard library: EMA, SMA, VWAP, RSI, MACD, Supertrend, ATR, ADX, CCI, OBV, Bollinger, Ichimoku, Donchian, Keltner, Pivots.
- Custom composites implemented in-house: Relative Strength vs Nifty, relative volume, gap detection, Minervini Trend Template, VCP detector (Phase 3 — VCP is genuinely hard; ship a v1 heuristic, iterate), stage analysis, Darvas box, pocket pivot.
- Computed on request + cached; nightly precompute for scanner speed.
- User-defined custom indicators: Phase 4, as a sandboxed expression language (`ema(close,20) > sma(close,50)`) — **not** arbitrary Python from users (security).

### 6.3 Scanner Engine (P0)
- Declarative JSON rule schema — **the `nse-trading-bot/rules.json` in this repo is the reference format**: universe, timeframes, indicator definitions, condition lists with `ALL/ANY` logic, cross-timeframe references, immediate trigger + re-arm semantics.
- Runs on candle-close events (hourly during market hours, EOD after bhavcopy) over the F&O universe with the optional top-50 liquidity filter.
- Built-in scans at launch: the momentum BUY/SELL config, 52-week high/low, EMA crossovers, RSI thresholds, relative-volume spikes, delivery-volume increase.
- Output → `signals` table → alert engine → Telegram.

### 6.4 Charting (P0)
- **TradingView Lightweight Charts** (free, Apache-licensed): candles, line, area, volume, overlays, multi-pane indicators.
- Drawing tools (trendline, S/R, fib, channels, annotations) built on its primitives — budget real frontend time here; this is the biggest frontend lift.
- Heikin Ashi/Renko computed server-side as candle transforms. Layouts/templates/watchlists stored per user.

### 6.5 Options Analytics (P1)
- Chain view with OI, ΔOI, IV, volume, bid/ask; Greeks via Black-76 on futures (`py_vollib`, free); IV rank/percentile from stored IV history (starts accruing the day snapshots begin — start snapshotting early!).
- PCR, max pain, GEX/DEX from chain snapshots.
- Strategy builder: legs → payoff diagram, breakevens, max P/L, POP estimate, margin estimate (broker margin API). Presets: condor, butterfly, straddle, strangle, covered call, CSP, calendars, custom.

### 6.6 Nifty Impact Engine (P1)
Math is simple once weights exist:
`index_points = index_level × weight_i × stock_move_% ` summed over inputs.
- Maintain constituent weights (AMFI/NSE monthly + free-float adjustment).
- API + UI: "RELIANCE +5%, HDFCBANK +2%, ICICIBANK −1% → estimated Nifty ±X points (±Y%)". Support Nifty 50, Bank Nifty, Fin Nifty.
- Clearly labeled as a static estimate (ignores correlation/second-order effects); Phase 5 can add a regression-based estimate.

### 6.7 AI Assistant (P0 minimal → grows every phase)
- Chat UI with **tool-calling against the platform's own APIs**: `run_scan`, `get_candles`, `get_option_chain`, `get_indicators`, `get_news`, `get_portfolio`, `impact_estimate`, `explain_chart`.
- "Show me bullish banking stocks" → AI composes a scanner call, gets JSON, explains results. All numbers come from engines; AI only reasons and writes.
- Every response that touches trades carries a decision-support disclaimer.

### 6.8 News Intelligence (P2)
- RSS/feed pollers → dedupe → cheap-model tagging pipeline: entities (stocks), sectors, event type, sentiment, materiality score → stored + searchable.
- Impact mapping: static knowledge base (sector → stocks, theme → beneficiaries, e.g. "EV subsidy" → Tata Motors, M&M, Exide, Amara Raja) + AI ranking with confidence + expected-direction rationale. Probabilities are framed as qualitative confidence, not fake precision.
- Earnings: results calendar, actual vs estimate where available, historical post-result reaction stats, AI summary of the filing PDF.
- Economic calendar: CPI/GDP/RBI/Fed/PMI events; post-event AI explainer of market reaction.

### 6.9 Portfolio & Risk (P2)
- Manual entry + CSV import first; broker holdings sync (read-only) later.
- Holdings, positions, realized/unrealized P&L, allocation, sector exposure heatmap, margin (broker API).
- Trade journal: every signal you act on links to entry/exit, screenshots, notes, and the signal snapshot (which the AI later mines for what works).
- Risk: position sizing calculator, fixed-fractional & Kelly, R:R, max drawdown, portfolio VaR (historical simulation — simple and honest), correlation matrix, Monte Carlo of portfolio paths. Stress tests: replay 2008/2020/known event days against current portfolio.

### 6.10 Backtesting (P3)
- **vectorbt** (free) for vectorized indicator strategies over TimescaleDB data; walk-forward split support; Monte Carlo resampling of trade sequences.
- Reports: CAGR, Sharpe, Sortino, Calmar, win rate, profit factor, max DD, exposure, equity curve.
- Options backtests (Phase 5) once enough chain-snapshot history has accrued — another reason to start snapshotting on day 1.
- Scanner configs and backtest strategies share the same rule schema → any scan is backtestable.

### 6.11 Alerts (P0 minimal)
- **Telegram bot first** (free, instant, reliable, mobile push for ₹0). Email (SES/Resend free tier) second. WhatsApp Business API is paid — skip until revenue. Discord webhook trivial to add.
- Alert types: scanner signals, price levels, indicator conditions, news mentioning watchlist/portfolio stocks, risk breaches.

### 6.12 Quant Research Lab (P4)
- JupyterHub (or plain Jupyter) on the VPS with a `platform` Python client library exposing all data/engines.
- Experiment registry table (params, dataset hash, metrics, artifacts) — MLflow later if needed.
- Factor analysis, portfolio optimization (`riskfolio-lib`, free), sklearn/xgboost model experiments.
- This is where new ideas graduate into scanner rules or backtest strategies.

### 6.13 AI Learning Loop (P4)
- Every signal + recommendation is logged with full feature snapshot; outcomes labeled automatically (forward returns at 1/5/20 days).
- Dashboards: hit rate per scan, per regime, false-signal analysis.
- Feed aggregate stats back into AI context ("this scan's 20-day hit rate is 54%") — honest, data-backed self-assessment rather than opaque "self-improving AI".

### 6.14 Execution Module (P6 — future, gated)
- Only after explicit confirmation. Paper trading engine first (fills against live quotes, realistic slippage/fees).
- Broker adapters behind one `BrokerInterface`: Zerodha, Angel One, Upstox, Dhan. Order management, pre-trade risk checks (max position, max daily loss, ban-list block), kill switch, full audit log.
- **Compliance note:** offering trade *execution* or *advice* to other users triggers SEBI RIA/RA and broker-API commercial terms. For personal use you're fine; before opening execution or "recommendations" to the public, get regulatory advice. Until then every output is labeled research/decision-support.

---

## 7. Database Schema (core tables, Phase 1–2)

```sql
users(id, email, google_id, pw_hash, plan, created_at)
symbols(id, ticker, exchange, name, isin, sector, fno_flag, lot_size, index_memberships jsonb)
candles(symbol_id, tf, ts, o, h, l, c, v, oi)            -- Timescale hypertable
index_weights(index_name, symbol_id, weight, asof_date)
watchlists(id, user_id, name) / watchlist_items(watchlist_id, symbol_id, sort)
scans(id, user_id, name, rules jsonb, enabled, schedule)  -- rules.json schema
signals(id, scan_id, symbol_id, side, ts, snapshot jsonb, delivered_at)
chain_snapshots(symbol_id, expiry, strike, opt_type, ts, ltp, oi, oi_chg, iv, volume, bid, ask)
news_items(id, source, url, title, body, published_at, hash)
news_tags(news_id, symbol_id, sector, event_type, sentiment, materiality, ai_meta jsonb)
portfolios(id, user_id, name, capital)
trades(id, portfolio_id, symbol_id, side, qty, price, fees, ts, journal_note, signal_id)
positions(portfolio_id, symbol_id, qty, avg_price)        -- materialized from trades
alerts(id, user_id, type, config jsonb, channel, enabled)
alert_deliveries(alert_id, ts, payload jsonb, status)
backtests(id, user_id, strategy jsonb, range, metrics jsonb, equity_curve jsonb, created_at)
ai_conversations(id, user_id, ...) / ai_messages(conv_id, role, content, tool_calls jsonb, tokens, cost)
experiments(id, user_id, name, params jsonb, metrics jsonb, artifact_uri)
audit_log(id, user_id, action, detail jsonb, ts)
```

---

## 8. API Surface (Phase 1–2 sketch)

```
POST /auth/register|login|google        GET  /me
GET  /symbols?fno=true&search=
GET  /candles/{ticker}?tf=&from=&to=    GET  /quote/{ticker}     WS /stream
GET  /indicators/{ticker}?tf=&names=rsi14,sma50
CRUD /watchlists                        CRUD /scans
POST /scans/{id}/run                    GET  /signals?scan_id=&from=
GET  /options/{ticker}/chain?expiry=    GET  /options/{ticker}/analytics
POST /options/strategy/payoff
POST /impact/estimate                   {"moves":[{"ticker":"RELIANCE","pct":5}],"index":"NIFTY"}
POST /ai/chat  (SSE stream, tool-calling)
CRUD /portfolios /trades                GET  /portfolio/{id}/risk
CRUD /alerts
POST /backtests                          GET  /backtests/{id}
```

---

## 9. Phased Roadmap

Each phase ends with a deployed, daily-usable product. Timelines assume solo builder + AI pair-programming, part-time; halve them if full-time.

### Phase 0 — Foundations (Week 1–2)
Repo monorepo (`frontend/`, `backend/`, `infra/`), Docker Compose (Postgres+Timescale, Redis, API, worker, Caddy), CI via GitHub Actions (free), JWT auth + Google OAuth, VPS provisioned, domain + TLS, nightly DB backup to R2.
**Exit:** login works on your domain; hello-world chart renders.

### Phase 1 — Data + Charts + Scanner MVP (Week 3–8) ← the big one
Broker API integration (Angel One/Dhan), EOD bhavcopy pipeline, historical backfill (2y daily + 1y hourly, F&O universe), candle API + WS quotes, indicator engine (core 15), Lightweight Charts UI with indicator overlays + watchlists, scanner engine executing the **rules.json momentum config**, signals table, Telegram alerts, basic AI chat with `run_scan`/`get_candles`/`explain` tools.
**Exit:** the exact scanner defined in `nse-trading-bot/rules.json` runs every hourly close and pings your Telegram; you stop needing ChartInk.

### Phase 2 — Options + Impact Engine (Week 9–14)
Chain ingestion + snapshots (start day 1 of the phase — history compounds), Greeks/IV/PCR/max pain, chain UI, strategy builder with payoff diagrams, Nifty Impact Engine + UI, options scanner conditions (OI change, IV spike, unusual activity).
**Exit:** you stop needing Sensibull for analysis.

### Phase 3 — Portfolio, Risk, Backtesting (Week 15–20)
Portfolio + journal + CSV import, risk dashboard (sizing, VaR, correlation, Monte Carlo), vectorbt backtesting wired to the scanner rule schema, performance reports, drawing tools on charts.
**Exit:** every rules.json strategy is backtestable; your trades are journaled and risk-scored.

### Phase 4 — News & Earnings Intelligence + Research Lab (Week 21–28)
RSS ingestion + AI tagging pipeline, impact mapping KB, earnings calendar + AI summaries, economic calendar, news-driven alerts, Jupyter research lab + platform client lib, signal outcome tracking (learning-loop groundwork).
**Exit:** "why is X moving?" answered inside the app with sources.

### Phase 5 — Polish & Scale-Ready (Week 29–36)
Custom indicator expression language, dashboard widgets (drag/drop, resizable — dark-first Bloomberg-style), advanced scans (VCP v2, Minervini, stage analysis), IV-history-powered analytics, GEX/DEX, performance hardening, optional: open to first external beta users (this is when you add rate limiting per user, plans table, payments if desired).

### Phase 6 — Execution (gated, future)
Paper trading → broker adapters → live orders with risk checks. Only on explicit go decision + compliance review.

---

## 10. Cost Model (monthly, Phase 1–4)

| Item | Choice | Cost |
|---|---|---|
| VPS (4 vCPU / 8 GB / 160 GB) | Hetzner CX32 or Contabo | ₹700–1,100 |
| Domain | .in/.com | ₹80 (amortized) |
| Frontend hosting | Vercel free tier (or same VPS) | ₹0 |
| Market data | Broker APIs (Angel One/Dhan) + NSE files | ₹0 |
| AI tokens | DeepSeek/Gemini Flash bulk + Claude for interactive | ₹300–1,200 |
| Alerts | Telegram | ₹0 |
| Backups | Cloudflare R2 free tier | ₹0 |
| CI/CD | GitHub Actions free tier | ₹0 |
| TLS | Let's Encrypt via Caddy | ₹0 |
| **Total** | | **≈ ₹1,100–2,400/mo (~$13–29)** |

One-time: broker account opening (free–₹300). Avoid: Zerodha Kite Connect ₹2,000/mo, paid data vendors (₹3k–25k/mo), managed K8s (₹8k+/mo), WhatsApp Business API — none needed before external users exist.

**Scaling path when needed (not before):** VPS → bigger VPS → 2 VPS (app/db split) → managed Postgres + multiple app nodes behind a load balancer → only then containers-orchestration. Each step is triggered by measured load, not anticipation.

---

## 11. Tech Stack (final, minimum-cost)

- **Frontend:** Next.js 15, React, TypeScript, Tailwind, shadcn/ui, TradingView Lightweight Charts, Recharts, TanStack Query, Zustand.
- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, pandas, pandas-ta, py_vollib, vectorbt, riskfolio-lib, APScheduler.
- **Data:** PostgreSQL 16 + TimescaleDB, Redis 7.
- **AI:** LiteLLM gateway; DeepSeek + Gemini Flash (bulk), Claude Sonnet (interactive), Ollama-ready for local models; bge-small local embeddings + pgvector for news/doc search.
- **Infra:** Docker Compose, Caddy (TLS), GitHub Actions, Hetzner/Contabo VPS, Cloudflare (DNS/CDN free) + R2 backups.
- **Auth:** JWT + Google OAuth (authlib). Secrets in `.env` + SOPS-encrypted in repo.
- **Observability:** structured logs + Uptime Kuma (self-hosted, free) + Sentry free tier.

---

## 12. Development Workflow

1. **Monorepo:** `backend/app/<module>/{router,service,models,schemas}.py`, `frontend/`, `infra/compose.yml`, `docs/`.
2. **Branch → PR → CI (ruff, mypy, pytest, tsc, eslint, build) → merge → auto-deploy** to VPS via GitHub Action + `docker compose up -d` over SSH. One command, zero-cost pipeline.
3. **Testing strategy:** unit tests for every indicator against known-good values (TA-Lib reference), golden-file tests for scanner rule evaluation (feed synthetic candles, assert signals), contract tests per broker adapter with recorded fixtures, Playwright smoke test for login→chart→scan.
4. **Definition of done per module:** deployed, tested, documented in `docs/modules/<name>.md`, and used by you for one real trading week.
5. **AI-assisted build loop:** for each module — write the spec section → generate schema + router + service with Claude Code → write tests → integrate → verify against live market for a session.

---

## 13. Security & Compliance

- Broker API keys encrypted at rest (Fernet, key outside DB); never sent to the AI layer.
- Rate limiting (slowapi) on auth + AI endpoints; audit log for every auth/config/execution-adjacent action.
- Role model: single `user` role now; `admin` flag; RBAC table when multi-user.
- Disclaimers on every AI/trade-adjacent surface: research & education, not investment advice.
- Before any public "recommendations" or execution features: SEBI RIA/RA assessment.
- Respect NSE website terms — prefer broker APIs over scraping; back off on 429s.

---

## 14. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Scope explosion (15 modules, 0 finished) | Fatal | Phase gates; each phase must be *used daily* before next starts |
| Free NSE endpoints break | High | Broker API is primary; NSE files/JSON are secondary; 2 broker accounts for redundancy |
| Broker API terms change | Medium | Adapter interface makes swapping brokers a 1-file change |
| IV/options history takes months to accrue | Medium | Start chain snapshots in Phase 2 week 1; buy nothing — patience is free |
| AI hallucinating market facts | High (trust) | AI only sees engine-produced JSON; all numbers rendered from data, not from the model's text |
| Burnout as solo builder | High | Working product every phase; automate ops to near-zero |
| Regulatory (advice to others) | High later | Personal-use posture until legal review; disclaimers everywhere |

---

## 15. Success Metrics

- **Phase 1:** scanner signal latency < 60 s after hourly close; you personally use it every market day for 2 weeks.
- **Phase 2:** option chain snapshot every ≤5 min, 99% market-hour coverage; payoff builder used for every options trade you place.
- **Phase 3:** ≥3 strategies backtested; journal has 100% of your trades.
- **Phase 4:** ≥80% of major market-moving news tagged within 15 min; "why is X moving" answerable in-app.
- **Cost:** infra + AI ≤ ₹2,500/mo throughout Phases 1–4.

---

## Appendix A — Relationship to the TradingView MCP setup

The Claude × TradingView MCP setup (see `nse-trading-bot/rules.json`) is the **Phase-0 prototype** of this platform: it validates the rule schema, the dual-timeframe momentum strategy, and the scan→signal→alert loop using TradingView as the data source. The platform replaces TradingView with broker/NSE data and turns the same `rules.json` schema into the native scanner format — so everything learned and configured there carries forward unchanged.
