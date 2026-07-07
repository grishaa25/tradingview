-- =============================================================
-- AI Trading Intelligence Platform — initial schema (Phase 0/1)
-- Target: Supabase (Postgres 15+). Adapted from docs/ARCHITECTURE.md §4:
--   * TimescaleDB is not available on Supabase → candles/chain_snapshots
--     are plain tables with composite PKs + BRIN/btree indexes.
--     (Native partitioning can be added later if volume demands it.)
--   * Auth is Supabase Auth (auth.users) → user-owned tables reference
--     auth.users(id) uuid and are protected with RLS.
-- =============================================================

create extension if not exists vector with schema extensions;

-- -------------------------------------------------------------
-- Profiles (1:1 with auth.users)
-- -------------------------------------------------------------
create table public.profiles (
  id          uuid primary key references auth.users(id) on delete cascade,
  email       text,
  display_name text,
  plan        text not null default 'free',
  is_admin    boolean not null default false,
  created_at  timestamptz not null default now()
);

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, email)
  values (new.id, new.email)
  on conflict (id) do nothing;
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- -------------------------------------------------------------
-- Market data (written by backend via service role; read by all users)
-- -------------------------------------------------------------
create table public.symbols (
  id            serial primary key,
  ticker        text not null,
  exchange      text not null default 'NSE',
  name          text,
  isin          text,
  sector        text,
  fno_flag      boolean not null default false,
  lot_size      int,
  index_memberships jsonb not null default '[]',
  unique (exchange, ticker)
);

create table public.candles (
  symbol_id  int  not null references public.symbols(id),
  tf         text not null,            -- '1m' | '60' | '1D'
  ts         timestamptz not null,
  o numeric(12,2), h numeric(12,2), l numeric(12,2), c numeric(12,2),
  v bigint, oi bigint,
  primary key (symbol_id, tf, ts)
);
-- ts is append-mostly → BRIN keeps time-range scans cheap without hypertables
create index candles_ts_brin on public.candles using brin (ts);
create index candles_tf_ts_idx on public.candles (tf, ts desc);

create table public.liquidity_stats (      -- drives top_liquid_50 filter
  symbol_id int not null references public.symbols(id),
  asof_date date not null,
  avg_traded_value_30d numeric(18,2),
  rank int,
  primary key (symbol_id, asof_date)
);

create table public.index_weights (
  index_name text not null,
  symbol_id  int not null references public.symbols(id),
  weight     numeric(8,5),
  free_float numeric(8,5),
  asof_date  date not null,
  primary key (index_name, symbol_id, asof_date)
);

-- -------------------------------------------------------------
-- Scanner (rules.json schema lives in scans.rules)
-- -------------------------------------------------------------
create table public.scans (
  id         serial primary key,
  user_id    uuid not null references auth.users(id) on delete cascade,
  name       text not null,
  rules      jsonb not null,              -- nse-trading-bot/rules.json schema
  enabled    boolean not null default true,
  schedule   text not null default 'on_hourly_candle_close',
  created_at timestamptz not null default now()
);

create table public.scan_state (           -- re-arm state machine
  scan_id    int not null references public.scans(id) on delete cascade,
  symbol_id  int not null references public.symbols(id),
  side       text not null check (side in ('buy','sell')),
  state      text not null default 'armed' check (state in ('armed','fired')),
  updated_at timestamptz not null default now(),
  primary key (scan_id, symbol_id, side)
);

create table public.signals (
  id           bigserial primary key,
  scan_id      int not null references public.scans(id) on delete cascade,
  symbol_id    int not null references public.symbols(id),
  side         text not null check (side in ('buy','sell')),
  ts           timestamptz not null default now(),
  snapshot     jsonb,                      -- every condition's actual values
  delivered_at timestamptz
);
create index signals_scan_ts_idx on public.signals (scan_id, ts desc);

-- -------------------------------------------------------------
-- Options (append-only snapshots; analytics derived on read)
-- -------------------------------------------------------------
create table public.chain_snapshots (
  symbol_id int not null references public.symbols(id),
  expiry    date not null,
  strike    numeric(12,2) not null,
  opt_type  char(2) not null check (opt_type in ('CE','PE')),
  ts        timestamptz not null,
  ltp numeric(12,2), oi bigint, oi_chg bigint, iv numeric(8,4),
  volume bigint, bid numeric(12,2), ask numeric(12,2),
  primary key (symbol_id, expiry, strike, opt_type, ts)
);
create index chain_snapshots_ts_brin on public.chain_snapshots using brin (ts);

create table public.iv_history (            -- ATM IV daily close → IV rank
  symbol_id int not null references public.symbols(id),
  asof_date date not null,
  atm_iv    numeric(8,4),
  primary key (symbol_id, asof_date)
);

-- -------------------------------------------------------------
-- News intelligence
-- -------------------------------------------------------------
create table public.news_items (
  id           bigserial primary key,
  source       text,
  url          text,
  title        text,
  body         text,
  published_at timestamptz,
  hash         text unique
);

create table public.news_tags (
  news_id     bigint not null references public.news_items(id) on delete cascade,
  symbol_id   int references public.symbols(id),
  sector      text,
  event_type  text,
  sentiment   text,
  materiality smallint,
  ai_meta     jsonb,
  embedding   extensions.vector(384)
);
create index news_tags_news_idx on public.news_tags (news_id);

-- -------------------------------------------------------------
-- User-owned: watchlists, portfolio, alerts, backtests, AI, audit
-- -------------------------------------------------------------
create table public.watchlists (
  id      serial primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  name    text not null
);
create table public.watchlist_items (
  watchlist_id int not null references public.watchlists(id) on delete cascade,
  symbol_id    int not null references public.symbols(id),
  sort         int not null default 0,
  primary key (watchlist_id, symbol_id)
);

create table public.portfolios (
  id      serial primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  name    text not null,
  capital numeric(18,2)
);
create table public.trades (
  id           bigserial primary key,
  portfolio_id int not null references public.portfolios(id) on delete cascade,
  symbol_id    int not null references public.symbols(id),
  side         text not null check (side in ('buy','sell')),
  qty          numeric(18,4) not null,
  price        numeric(12,2) not null,
  fees         numeric(12,2) not null default 0,
  ts           timestamptz not null default now(),
  journal_note text,
  signal_id    bigint references public.signals(id)
);
create table public.positions (             -- materialized from trades
  portfolio_id int not null references public.portfolios(id) on delete cascade,
  symbol_id    int not null references public.symbols(id),
  qty          numeric(18,4) not null,
  avg_price    numeric(12,2) not null,
  primary key (portfolio_id, symbol_id)
);

create table public.alerts (
  id      serial primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  type    text not null,
  config  jsonb not null default '{}',
  channel text not null default 'telegram',
  enabled boolean not null default true
);
create table public.alert_deliveries (
  id       bigserial primary key,
  alert_id int not null references public.alerts(id) on delete cascade,
  ts       timestamptz not null default now(),
  payload  jsonb,
  status   text
);

create table public.backtests (
  id           serial primary key,
  user_id      uuid not null references auth.users(id) on delete cascade,
  strategy     jsonb not null,             -- same rules.json schema
  range        jsonb,
  metrics      jsonb,
  equity_curve jsonb,
  created_at   timestamptz not null default now()
);

create table public.ai_conversations (
  id         serial primary key,
  user_id    uuid not null references auth.users(id) on delete cascade,
  title      text,
  created_at timestamptz not null default now()
);
create table public.ai_messages (
  id         bigserial primary key,
  conv_id    int not null references public.ai_conversations(id) on delete cascade,
  role       text not null check (role in ('user','assistant','tool','system')),
  content    text,
  tool_calls jsonb,
  tokens     int,
  cost       numeric(10,6),
  created_at timestamptz not null default now()
);

create table public.audit_log (
  id      bigserial primary key,
  user_id uuid references auth.users(id),
  action  text not null,
  detail  jsonb,
  ts      timestamptz not null default now()
);

create table public.job_runs (              -- worker observability
  id          bigserial primary key,
  job_name    text not null,
  started_at  timestamptz not null default now(),
  finished_at timestamptz,
  status      text,
  detail      jsonb
);
create index job_runs_name_idx on public.job_runs (job_name, started_at desc);

-- -------------------------------------------------------------
-- Row Level Security
-- Backend workers use the service-role key and bypass RLS.
-- -------------------------------------------------------------

-- Shared/market data: readable by any signed-in user, writable only by service role
do $$
declare t text;
begin
  foreach t in array array[
    'symbols','candles','liquidity_stats','index_weights',
    'chain_snapshots','iv_history','news_items','news_tags','job_runs'
  ] loop
    execute format('alter table public.%I enable row level security', t);
    execute format(
      'create policy "authenticated read" on public.%I for select to authenticated using (true)', t);
  end loop;
end $$;

-- Profiles: owner read/update
alter table public.profiles enable row level security;
create policy "own profile read"   on public.profiles for select using (auth.uid() = id);
create policy "own profile update" on public.profiles for update using (auth.uid() = id);

-- Directly user-owned tables: full CRUD for the owner
do $$
declare t text;
begin
  foreach t in array array[
    'scans','watchlists','portfolios','alerts','backtests','ai_conversations'
  ] loop
    execute format('alter table public.%I enable row level security', t);
    execute format(
      'create policy "owner all" on public.%I for all using (auth.uid() = user_id) with check (auth.uid() = user_id)', t);
  end loop;
end $$;

-- Child tables: ownership via parent
alter table public.watchlist_items enable row level security;
create policy "owner all" on public.watchlist_items for all
  using (exists (select 1 from public.watchlists w where w.id = watchlist_id and w.user_id = auth.uid()))
  with check (exists (select 1 from public.watchlists w where w.id = watchlist_id and w.user_id = auth.uid()));

alter table public.trades enable row level security;
create policy "owner all" on public.trades for all
  using (exists (select 1 from public.portfolios p where p.id = portfolio_id and p.user_id = auth.uid()))
  with check (exists (select 1 from public.portfolios p where p.id = portfolio_id and p.user_id = auth.uid()));

alter table public.positions enable row level security;
create policy "owner read" on public.positions for select
  using (exists (select 1 from public.portfolios p where p.id = portfolio_id and p.user_id = auth.uid()));

alter table public.signals enable row level security;
create policy "owner read" on public.signals for select
  using (exists (select 1 from public.scans s where s.id = scan_id and s.user_id = auth.uid()));

alter table public.scan_state enable row level security;
create policy "owner read" on public.scan_state for select
  using (exists (select 1 from public.scans s where s.id = scan_id and s.user_id = auth.uid()));

alter table public.alert_deliveries enable row level security;
create policy "owner read" on public.alert_deliveries for select
  using (exists (select 1 from public.alerts a where a.id = alert_id and a.user_id = auth.uid()));

alter table public.ai_messages enable row level security;
create policy "owner all" on public.ai_messages for all
  using (exists (select 1 from public.ai_conversations c where c.id = conv_id and c.user_id = auth.uid()))
  with check (exists (select 1 from public.ai_conversations c where c.id = conv_id and c.user_id = auth.uid()));

alter table public.audit_log enable row level security;
create policy "owner read" on public.audit_log for select using (auth.uid() = user_id);
