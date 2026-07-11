"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { backendFetch } from "@/lib/backend";

type Leg = {
  ltp: number | null;
  oi: number | null;
  oi_chg: number | null;
  iv: number | null;
  volume: number | null;
} | null;

type Chain = {
  symbol: string;
  spot: number | null;
  expiry: string | null;
  expiries: string[];
  fetched_at: string | null;
  analytics: {
    pcr: { oi: number | null; volume: number | null };
    max_pain: number | null;
    atm_strike: number | null;
    atm_iv: number | null;
    support: number | null;
    resistance: number | null;
  };
  strikes: { strike: number; ce: Leg; pe: Leg }[];
};

const SYMBOLS = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"];

function fmt(n: number | null | undefined, digits = 0): string {
  if (n == null) return "—";
  return n.toLocaleString("en-IN", { maximumFractionDigits: digits });
}

function OiCell({ leg, maxOi }: { leg: Leg; maxOi: number }) {
  if (!leg?.oi) return <td className="px-2 py-1 text-right text-zinc-600">—</td>;
  const width = maxOi ? Math.round((leg.oi / maxOi) * 100) : 0;
  const chg = leg.oi_chg ?? 0;
  return (
    <td className="relative px-2 py-1 text-right tabular-nums">
      <span
        className="absolute inset-y-0 right-0 bg-zinc-700/30"
        style={{ width: `${width}%` }}
      />
      <span className="relative">
        {fmt(leg.oi)}{" "}
        <span className={chg >= 0 ? "text-emerald-400" : "text-red-400"}>
          {chg >= 0 ? "+" : ""}
          {fmt(chg)}
        </span>
      </span>
    </td>
  );
}

export default function Page({
  params,
}: {
  params: Promise<{ symbol: string }>;
}) {
  const { symbol } = use(params);
  const sym = symbol.toUpperCase();
  const [chain, setChain] = useState<Chain | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(
    async (expiry?: string) => {
      setLoading(true);
      setError(null);
      try {
        const qs = expiry ? `?expiry=${expiry}` : "";
        setChain(await backendFetch<Chain>(`/options/chain/${sym}${qs}`));
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    },
    [sym],
  );

  useEffect(() => {
    load();
  }, [load]);

  const a = chain?.analytics;
  const maxOi = Math.max(
    1,
    ...(chain?.strikes ?? []).flatMap((s) => [s.ce?.oi ?? 0, s.pe?.oi ?? 0]),
  );
  const atm = a?.atm_strike;

  return (
    <main className="mx-auto max-w-5xl p-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">{sym} — Options</h1>
        {SYMBOLS.filter((s) => s !== sym).map((s) => (
          <Link key={s} href={`/options/${s}`} className="text-sm text-zinc-400 underline">
            {s}
          </Link>
        ))}
        <span className="ml-auto text-sm text-zinc-400">
          Spot: <span className="text-zinc-100">{fmt(chain?.spot, 2)}</span>
          {chain?.fetched_at && (
            <span className="ml-2 text-zinc-500">as of {chain.fetched_at}</span>
          )}
        </span>
      </div>

      {error && (
        <p className="mt-4 text-sm text-amber-300">
          {error.includes("Not signed in") ? (
            <>Sign in first — <Link href="/login" className="underline">login</Link>.</>
          ) : (
            error
          )}
        </p>
      )}
      {loading && <p className="mt-4 text-sm text-zinc-500">Loading chain…</p>}

      {chain && (
        <>
          <div className="mt-4 flex flex-wrap gap-2 text-sm">
            {chain.expiries.slice(0, 8).map((e) => (
              <button
                key={e}
                onClick={() => load(e)}
                className={`rounded px-3 py-1 ${
                  e === chain.expiry
                    ? "bg-zinc-200 text-zinc-900"
                    : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
                }`}
              >
                {e}
              </button>
            ))}
          </div>

          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
            {[
              ["PCR (OI)", fmt(a?.pcr.oi, 2)],
              ["Max Pain", fmt(a?.max_pain)],
              ["ATM IV", a?.atm_iv != null ? `${a.atm_iv}%` : "—"],
              ["Support (PE wall)", fmt(a?.support)],
              ["Resistance (CE wall)", fmt(a?.resistance)],
            ].map(([label, value]) => (
              <div key={label} className="rounded-lg border border-zinc-800 p-3">
                <div className="text-xs text-zinc-500">{label}</div>
                <div className="mt-1 text-lg font-medium">{value}</div>
              </div>
            ))}
          </div>

          <table className="mt-6 w-full text-xs sm:text-sm">
            <thead>
              <tr className="border-b border-zinc-800 text-zinc-500">
                <th className="px-2 py-2 text-right">CE OI (chg)</th>
                <th className="px-2 py-2 text-right">CE LTP</th>
                <th className="px-2 py-2 text-right">CE IV</th>
                <th className="px-2 py-2 text-center">Strike</th>
                <th className="px-2 py-2 text-right">PE IV</th>
                <th className="px-2 py-2 text-right">PE LTP</th>
                <th className="px-2 py-2 text-right">PE OI (chg)</th>
              </tr>
            </thead>
            <tbody>
              {chain.strikes.map((s) => (
                <tr
                  key={s.strike}
                  className={`border-b border-zinc-900 ${
                    s.strike === atm ? "bg-zinc-800/40" : ""
                  }`}
                >
                  <OiCell leg={s.ce} maxOi={maxOi} />
                  <td className="px-2 py-1 text-right tabular-nums">{fmt(s.ce?.ltp, 2)}</td>
                  <td className="px-2 py-1 text-right text-zinc-400">{fmt(s.ce?.iv, 1)}</td>
                  <td
                    className={`px-2 py-1 text-center font-medium ${
                      s.strike === atm ? "text-amber-300" : ""
                    }`}
                  >
                    {fmt(s.strike)}
                  </td>
                  <td className="px-2 py-1 text-right text-zinc-400">{fmt(s.pe?.iv, 1)}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{fmt(s.pe?.ltp, 2)}</td>
                  <OiCell leg={s.pe} maxOi={maxOi} />
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-xs text-zinc-600">
            Free NSE feed, ~3 min delayed, cached 3 min server-side. OI bars scale
            to the largest OI in this expiry. Decision support only.
          </p>
        </>
      )}
    </main>
  );
}
