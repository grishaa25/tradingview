-- Enable Supabase Realtime on signals so the frontend receives new signals
-- live (RLS still applies — users only receive rows their policies allow).
alter publication supabase_realtime add table public.signals;
