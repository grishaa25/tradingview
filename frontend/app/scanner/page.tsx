"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";

type Scan = { id: number; name: string; enabled: boolean };
type Signal = {
  id: number;
  scan_id: number;
  side: string;
  ts: string;
  snapshot: { conditions?: { id: string; left: number; operator: string; right: number }[] };
  symbols: { ticker: string } | null;
};

// Reads scans + signals straight from Supabase (RLS scopes rows to the owner).
// Live updates arrive via Supabase Realtime on the signals table.
export default function ScannerPage() {
  const [scans, setScans] = useState<Scan[] | null>(null);
  const [signals, setSignals] = useState<Signal[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const supabase = createClient();

    async function load() {
      const { data: scanRows, error: scanErr } = await supabase
        .from("scans")
        .select("id, name, enabled")
        .order("id");
      if (scanErr) {
        setError(scanErr.message);
        return;
      }
      setScans(scanRows ?? []);

      const { data: sigRows } = await supabase
        .from("signals")
        .select("id, scan_id, side, ts, snapshot, symbols(ticker)")
        .order("ts", { ascending: false })
        .limit(50);
      setSignals((sigRows as unknown as Signal[]) ?? []);
    }
    load();

    const channel = supabase
      .channel("signals-live")
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "signals" },
        () => load(),
      )
      .subscribe();
    return () => {
      supabase.removeChannel(channel);
    };
  }, []);

  return (
    <main className="mx-auto max-w-4xl p-6">
      <h1 className="text-xl font-semibold">Scanner</h1>

      {error && (
        <p className="mt-4 text-sm text-zinc-400">
          {error} — are you <Link href="/login" className="underline">signed in</Link>?
        </p>
      )}

      <section className="mt-6">
        <h2 className="text-sm font-medium text-zinc-400">Your scans</h2>
        {scans && scans.length === 0 && (
          <p className="mt-2 text-sm text-zinc-500">
            No scans yet. Create one via <code>POST /scans</code> with your
            rules.json body (see the API docs at <code>/docs</code> on the backend).
          </p>
        )}
        <ul className="mt-2 space-y-1">
          {scans?.map((s) => (
            <li key={s.id} className="rounded border border-zinc-800 px-4 py-2 text-sm">
              #{s.id} {s.name} {s.enabled ? "· enabled" : "· disabled"}
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-8">
        <h2 className="text-sm font-medium text-zinc-400">Latest signals (live)</h2>
        {signals && signals.length === 0 && (
          <p className="mt-2 text-sm text-zinc-500">
            No signals yet — they appear here the moment a scan pass fires one.
          </p>
        )}
        <ul className="mt-2 space-y-1">
          {signals?.map((sig) => (
            <li
              key={sig.id}
              className="flex items-center gap-3 rounded border border-zinc-800 px-4 py-2 text-sm"
            >
              <span className={sig.side === "buy" ? "text-emerald-400" : "text-red-400"}>
                {sig.side.toUpperCase()}
              </span>
              <Link href={`/charts/${sig.symbols?.ticker ?? ""}`} className="font-medium underline">
                {sig.symbols?.ticker ?? "?"}
              </Link>
              <span className="text-zinc-500">{new Date(sig.ts).toLocaleString()}</span>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
