"use client";

import { use, useEffect, useState } from "react";
import TVChart, { type Candle } from "@/components/chart/TVChart";
import { backendFetch } from "@/lib/backend";

export default function ChartPage({
  params,
}: {
  params: Promise<{ symbol: string }>;
}) {
  const { symbol } = use(params);
  const ticker = symbol.toUpperCase();
  const [tf, setTf] = useState("1D");
  const [candles, setCandles] = useState<Candle[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setCandles(null);
    setError(null);
    backendFetch<Candle[]>(`/marketdata/candles/${ticker}?tf=${tf}`)
      .then(setCandles)
      .catch((e: Error) => setError(e.message));
  }, [ticker, tf]);

  return (
    <main className="p-6">
      <div className="mb-4 flex items-center gap-4">
        <h1 className="text-xl font-semibold">{ticker}</h1>
        <div className="flex gap-1">
          {["1D", "60"].map((t) => (
            <button
              key={t}
              onClick={() => setTf(t)}
              className={`rounded px-3 py-1 text-sm ${
                tf === t ? "bg-zinc-100 text-zinc-900" : "bg-zinc-800 text-zinc-300"
              }`}
            >
              {t === "60" ? "1H" : t}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <p className="rounded border border-zinc-800 p-4 text-sm text-zinc-400">
          {error.includes("404")
            ? `No ${tf} candles for ${ticker} yet — run the bhavcopy ingest or broker backfill first.`
            : error.includes("Not signed in")
              ? "Sign in first to load chart data."
              : `Could not reach the backend: ${error}`}
        </p>
      )}
      {!error && candles === null && (
        <p className="text-sm text-zinc-500">Loading…</p>
      )}
      {candles && <TVChart candles={candles} />}
    </main>
  );
}
