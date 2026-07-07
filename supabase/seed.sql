-- Local/dev seed data. Applied by `supabase db reset`.
insert into public.symbols (ticker, exchange, name, sector, fno_flag, lot_size) values
  ('RELIANCE', 'NSE', 'Reliance Industries', 'Energy',   true, 250),
  ('HDFCBANK', 'NSE', 'HDFC Bank',           'Banking',  true, 550),
  ('ICICIBANK','NSE', 'ICICI Bank',          'Banking',  true, 700),
  ('INFY',     'NSE', 'Infosys',             'IT',       true, 400),
  ('TCS',      'NSE', 'Tata Consultancy Services', 'IT', true, 175)
on conflict (exchange, ticker) do nothing;
