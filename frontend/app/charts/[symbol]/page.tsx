"use client";

import { use, useEffect, useState } from "react";
import TVChart, { type Candle } from "@/components/chart/TVChart";
import TradingViewEmbed from "@/components/chart/TradingViewEmbed";
import { backendFetch } from "@/lib/backend";

export default function ChartPage({
  params,
}: {
  params: Promise<{ symbol: string }>;
}) {
  const { symbol } = use(params);
  const ticker = symbol.toUpperCase();
  const [source, setSource] = useState<"platform" | "tradingview">("platform");
  const [tf, setTf] = useState("1D");
  const [candles, setCandles] = useState<Candle[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (source !== "platform") return;
    setCandles(null);
    setError(null);
    backendFetch<Candle[]>(`/marketdata/candles/${ticker}?tf=${tf}`)
      .then(setCandles)
      .catch((e: Error) => setError(e.message));
  }, [ticker, tf, source]);

  return (
    <main className="p-6">
      <div className="mb-4 flex flex-wrap items-center gap-4">
        <h1 className="text-xl font-semibold">{ticker}</h1>

        <div className="flex gap-1">
          {(["platform", "tradingview"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setSource(s)}
              className={`rounded px-3 py-1 text-sm ${
                source === s ? "bg-zinc-100 text-zinc-900" : "bg-zinc-800 text-zinc-300"
              }`}
            >
              {s === "platform" ? "Platform chart" : "TradingView"}
            </button>
          ))}
        </div>

        {source === "platform" && (
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
        )}

        <a
          href={`https://www.tradingview.com/chart/?symbol=NSE:${ticker}`}
          target="_blank"
          rel="noreferrer"
          className="ml-auto text-sm text-zinc-400 underline hover:text-zinc-200"
        >
          Open in TradingView ↗
        </a>
      </div>

      {source === "tradingview" ? (
        <TradingViewEmbed ticker={ticker} />
      ) : (
        <>
          {error && (
            <p className="rounded border border-zinc-800 p-4 text-sm text-zinc-400">
              {error.includes("404")
                ? `No ${tf} candles for ${ticker} yet — POST /marketdata/admin/backfill?tickers=${ticker} to pull free Yahoo data, or use the TradingView tab.`
                : error.includes("Not signed in")
                  ? "Sign in first to load chart data."
                  : `Could not reach the backend: ${error}`}
            </p>
          )}
          {!error && candles === null && (
            <p className="text-sm text-zinc-500">Loading…</p>
          )}
          {candles && <TVChart candles={candles} />}
        </>
      )}
    </main>
  );
}
