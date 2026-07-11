"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { backendFetch } from "@/lib/backend";

type Quote = {
  ticker: string;
  ts: string | null;
  close: number | null;
  prev_close: number | null;
  change_pct: number | null;
  has_data: boolean;
};

const DEFAULT_WATCHLIST = [
  "VEDL", "TMPV", "SHRIRAMFIN", "SBIN", "MARUTI", "KOTAKBANK", "INDIGO",
  "ETERNAL", "BEL", "ADANIENSOL", "GODREJPROP", "M&M", "EICHERMOT", "IOC",
  "RELIANCE", "ASHOKLEY", "HDFCBANK", "BHEL",
];

export default function WatchlistPage() {
  const [tickers, setTickers] = useState<string[]>(DEFAULT_WATCHLIST);
  const [quotes, setQuotes] = useState<Quote[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function load(list: string[]) {
    setError(null);
    setLoading(true);
    try {
      const data = await backendFetch<Quote[]>(
        `/marketdata/quotes?tickers=${list.map(encodeURIComponent).join(",")}`,
      );
      setQuotes(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load(tickers);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const missing = quotes?.filter((q) => !q.has_data).map((q) => q.ticker) ?? [];

  return (
    <main className="mx-auto max-w-3xl p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Watchlist</h1>
        <button
          onClick={() => load(tickers)}
          className="rounded bg-zinc-800 px-3 py-1 text-sm text-zinc-200"
        >
          Refresh
        </button>
      </div>

      {error && (
        <p className="mt-4 text-sm text-zinc-400">{error}</p>
      )}

      {missing.length > 0 && (
        <div className="mt-4 rounded border border-amber-900/50 bg-amber-950/30 p-4 text-sm text-amber-200">
          <p className="font-medium">No data yet for: {missing.join(", ")}</p>
          <p className="mt-1 text-amber-300/80">
            Run these once against the backend (see /docs on your API):
          </p>
          <pre className="mt-2 overflow-x-auto rounded bg-black/30 p-2 text-xs">
{`POST /marketdata/admin/seed-universe
POST /marketdata/admin/backfill?tickers=${missing.map(encodeURIComponent).join(",")}`}
          </pre>
        </div>
      )}

      <table className="mt-6 w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-800 text-left text-zinc-500">
            <th className="pb-2">Symbol</th>
            <th className="pb-2 text-right">Close</th>
            <th className="pb-2 text-right">Chg %</th>
            <th className="pb-2 text-right">As of</th>
          </tr>
        </thead>
        <tbody>
          {(quotes ?? tickers.map((t) => ({ ticker: t }) as Quote)).map((q) => (
            <tr key={q.ticker} className="border-b border-zinc-900">
              <td className="py-2">
                <Link href={`/charts/${q.ticker}`} className="font-medium underline">
                  {q.ticker}
                </Link>
              </td>
              <td className="py-2 text-right">{q.close ?? (loading ? "…" : "—")}</td>
              <td
                className={`py-2 text-right ${
                  q.change_pct == null
                    ? "text-zinc-500"
                    : q.change_pct >= 0
                      ? "text-emerald-400"
                      : "text-red-400"
                }`}
              >
                {q.change_pct == null ? "—" : `${q.change_pct > 0 ? "+" : ""}${q.change_pct}%`}
              </td>
              <td className="py-2 text-right text-zinc-500">
                {q.ts ? new Date(q.ts).toLocaleDateString() : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
