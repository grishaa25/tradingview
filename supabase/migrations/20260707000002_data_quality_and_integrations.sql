-- =============================================================
-- Migration 2: data-quality tables + integration support
--   * corporate_actions  — adjust candles on read (PRD §5.3); without this,
--     splits/bonuses silently corrupt indicators and backtests
--   * broker_tokens      — Angel One / Dhan identify instruments by their own
--     numeric tokens, not NSE tickers
--   * market_holidays    — NSE trading calendar for the scheduler
--   * signals outcome columns — forward returns for the AI learning loop
--   * webhook_events     — inbound TradingView (Pro) alert webhooks
-- =============================================================

-- -------------------------------------------------------------
-- Corporate actions (adjust on read; raw candles stay immutable)
-- -------------------------------------------------------------
create table public.corporate_actions (
  id          bigserial primary key,
  symbol_id   int not null references public.symbols(id),
  ex_date     date not null,
  action_type text not null check (action_type in ('split','bonus','dividend','rights','merger')),
  -- price adjustment factor: old prices are multiplied by this for continuity
  -- e.g. 1:5 split → 0.2; 1:1 bonus → 0.5; dividends usually left unadjusted
  adj_factor  numeric(12,6) not null default 1.0,
  details     jsonb not null default '{}',   -- ratio, amount, source notes
  created_at  timestamptz not null default now(),
  unique (symbol_id, ex_date, action_type)
);
create index corporate_actions_symbol_idx on public.corporate_actions (symbol_id, ex_date desc);

-- -------------------------------------------------------------
-- Broker instrument token mapping (Phase 1 week 2, broker adapters)
-- -------------------------------------------------------------
create table public.broker_tokens (
  symbol_id  int not null references public.symbols(id),
  broker     text not null check (broker in ('angelone','dhan')),
  token      text not null,                  -- broker's instrument identifier
  segment    text,                           -- e.g. NSE_EQ, NSE_FNO
  extra      jsonb not null default '{}',    -- expiry/strike for derivatives etc.
  updated_at timestamptz not null default now(),
  primary key (broker, symbol_id),
  unique (broker, token)
);

-- -------------------------------------------------------------
-- NSE trading calendar (populate from the NSE holiday list each year)
-- -------------------------------------------------------------
create table public.market_holidays (
  holiday_date date not null,
  exchange     text not null default 'NSE',
  description  text,
  primary key (exchange, holiday_date)
);

-- -------------------------------------------------------------
-- Signal outcome labels (job: signal_outcomes, 19:45 IST daily)
-- -------------------------------------------------------------
alter table public.signals
  add column return_1d  numeric(8,4),
  add column return_5d  numeric(8,4),
  add column return_20d numeric(8,4),
  add column outcomes_labeled_at timestamptz;

-- -------------------------------------------------------------
-- Inbound webhooks (TradingView Pro alerts → platform pipeline).
-- The backend endpoint verifies a shared secret, stores the raw payload
-- here, then normalizes it into signals/alert_deliveries.
-- -------------------------------------------------------------
create table public.webhook_events (
  id          bigserial primary key,
  source      text not null default 'tradingview',
  received_at timestamptz not null default now(),
  payload     jsonb not null,
  processed   boolean not null default false,
  error       text
);
create index webhook_events_unprocessed_idx
  on public.webhook_events (received_at) where not processed;

-- -------------------------------------------------------------
-- RLS: shared/reference data — authenticated read, service-role write.
-- webhook_events is backend-internal: RLS on, no user policies.
-- -------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array['corporate_actions','broker_tokens','market_holidays'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format(
      'create policy "authenticated read" on public.%I for select to authenticated using (true)', t);
  end loop;
end $$;

alter table public.webhook_events enable row level security;
