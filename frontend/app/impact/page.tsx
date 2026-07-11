"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { backendFetch } from "@/lib/backend";

type Contribution = {
  ticker: string;
  weight: number;
  close: number | null;
  change_pct: number | null;
  impact_points: number | null;
};

type Impact = {
  index: { level: number; prev_close: number; change_pct: number | null; asof: string };
  index_points_change: number;
  explained_points: number;
  contributions: Contribution[];
  missing_data: string[];
};

function Bar({ points, maxAbs }: { points: number; maxAbs: number }) {
  const width = maxAbs ? Math.min(100, Math.round((Math.abs(points) / maxAbs) * 100)) : 0;
  return (
    <div className="h-2 w-full rounded bg-zinc-900">
      <div
        className={`h-2 rounded ${points >= 0 ? "bg-emerald-500/70" : "bg-red-500/70"}`}
        style={{ width: `${width}%` }}
      />
    </div>
  );
}

export default function Page() {
  const [data, setData] = useState<Impact | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    backendFetch<Impact>("/impact/nifty")
      .then(setData)
      .catch((e) => setError((e as Error).message));
  }, []);

  const withImpact = (data?.contributions ?? []).filter(
    (c): c is Contribution & { impact_points: number } => c.impact_points != null,
  );
  const maxAbs = Math.max(1, ...withImpact.map((c) => Math.abs(c.impact_points)));
  const gainers = withImpact.filter((c) => c.impact_points > 0).slice(0, 10);
  const losers = withImpact
    .filter((c) => c.impact_points < 0)
    .slice()
    .reverse()
    .slice(0, 10);

  return (
    <main className="mx-auto max-w-4xl p-6">
      <h1 className="text-xl font-semibold">Nifty Impact Engine</h1>
      <p className="mt-1 text-sm text-zinc-400">
        Which stocks moved NIFTY today — index-point contribution per constituent.
      </p>

      {error && (
        <p className="mt-4 text-sm text-amber-300">
          {error.includes("Not signed in") ? (
            <>Sign in first — <Link href="/login" className="underline">login</Link>.</>
          ) : (
            error
          )}
        </p>
      )}
      {!data && !error && <p className="mt-4 text-sm text-zinc-500">Loading…</p>}

      {data && (
        <>
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-lg border border-zinc-800 p-3">
              <div className="text-xs text-zinc-500">NIFTY</div>
              <div className="mt-1 text-lg font-medium">
                {data.index.level.toLocaleString("en-IN")}
              </div>
            </div>
            <div className="rounded-lg border border-zinc-800 p-3">
              <div className="text-xs text-zinc-500">Change</div>
              <div
                className={`mt-1 text-lg font-medium ${
                  data.index_points_change >= 0 ? "text-emerald-400" : "text-red-400"
                }`}
              >
                {data.index_points_change >= 0 ? "+" : ""}
                {data.index_points_change} ({data.index.change_pct ?? "—"}%)
              </div>
            </div>
            <div className="rounded-lg border border-zinc-800 p-3">
              <div className="text-xs text-zinc-500">Explained by constituents</div>
              <div className="mt-1 text-lg font-medium">
                {data.explained_points >= 0 ? "+" : ""}
                {data.explained_points} pts
              </div>
            </div>
            <div className="rounded-lg border border-zinc-800 p-3">
              <div className="text-xs text-zinc-500">Constituents with data</div>
              <div className="mt-1 text-lg font-medium">
                {withImpact.length}/{data.contributions.length}
              </div>
            </div>
          </div>

          {data.missing_data.length > 0 && (
            <div className="mt-4 rounded border border-amber-900/50 bg-amber-950/30 p-3 text-xs text-amber-200">
              No candle data yet for: {data.missing_data.join(", ")} — backfill via{" "}
              <code>POST /marketdata/admin/backfill?tickers=…</code>
            </div>
          )}

          <div className="mt-6 grid gap-8 sm:grid-cols-2">
            {[
              ["Top boosters", gainers],
              ["Top draggers", losers],
            ].map(([title, rows]) => (
              <div key={title as string}>
                <h2 className="text-sm font-medium text-zinc-300">{title as string}</h2>
                <table className="mt-2 w-full text-sm">
                  <tbody>
                    {(rows as (Contribution & { impact_points: number })[]).map((c) => (
                      <tr key={c.ticker} className="border-b border-zinc-900">
                        <td className="py-2 pr-2">
                          <Link href={`/charts/${c.ticker}`} className="underline">
                            {c.ticker}
                          </Link>
                          <div className="text-xs text-zinc-500">
                            w {c.weight}% · {c.change_pct != null ? `${c.change_pct > 0 ? "+" : ""}${c.change_pct}%` : "—"}
                          </div>
                        </td>
                        <td className="w-1/2 py-2">
                          <Bar points={c.impact_points} maxAbs={maxAbs} />
                        </td>
                        <td
                          className={`py-2 pl-2 text-right tabular-nums ${
                            c.impact_points >= 0 ? "text-emerald-400" : "text-red-400"
                          }`}
                        >
                          {c.impact_points >= 0 ? "+" : ""}
                          {c.impact_points}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
          <p className="mt-4 text-xs text-zinc-600">
            Approximate free-float weights (static snapshot, normalized). Index level
            live from Yahoo Finance; constituent moves from platform candles.
          </p>
        </>
      )}
    </main>
  );
}
