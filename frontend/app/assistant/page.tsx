"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { backendFetch } from "@/lib/backend";

type Msg = { role: "user" | "assistant"; content: string };
type ChatResponse = {
  conv_id: number;
  reply: string;
  cost: number;
  month_spend: number;
  context_tickers: string[];
};
type Usage = { month_spend_usd: number; budget_usd: number; model: string };

const SUGGESTIONS = [
  "How did RELIANCE and HDFCBANK close today?",
  "Summarize the latest scanner signals",
  "Explain what a PCR above 1.2 usually indicates",
];

export default function Page() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [convId, setConvId] = useState<number | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    backendFetch<Usage>("/ai/usage").then(setUsage).catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(text: string) {
    if (!text.trim() || busy) return;
    setError(null);
    setBusy(true);
    setMessages((m) => [...m, { role: "user", content: text }]);
    setInput("");
    try {
      const res = await backendFetch<ChatResponse>("/ai/chat", {
        method: "POST",
        body: JSON.stringify({ message: text, conv_id: convId }),
      });
      setConvId(res.conv_id);
      setMessages((m) => [...m, { role: "assistant", content: res.reply }]);
      setUsage((u) => (u ? { ...u, month_spend_usd: res.month_spend } : u));
    } catch (e) {
      setError((e as Error).message);
      setMessages((m) => m.slice(0, -1)); // roll back optimistic user msg
      setInput(text);
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    send(input);
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-col p-6" style={{ minHeight: "100dvh" }}>
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">AI Assistant</h1>
        {usage && (
          <span className="text-xs text-zinc-500">
            {usage.model} · ${usage.month_spend_usd.toFixed(2)} / $
            {usage.budget_usd.toFixed(0)} this month
          </span>
        )}
      </div>
      <p className="mt-1 text-sm text-zinc-500">
        Grounded in your platform&apos;s quotes and scanner signals. Decision support
        only — not investment advice.
      </p>

      <div className="mt-6 flex-1 space-y-4">
        {messages.length === 0 && (
          <div className="space-y-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => send(s)}
                className="block w-full rounded-lg border border-zinc-800 p-3 text-left text-sm text-zinc-300 hover:border-zinc-600"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`max-w-[85%] whitespace-pre-wrap rounded-lg p-3 text-sm ${
              m.role === "user"
                ? "ml-auto bg-zinc-200 text-zinc-900"
                : "border border-zinc-800 text-zinc-200"
            }`}
          >
            {m.content}
          </div>
        ))}
        {busy && <div className="text-sm text-zinc-500">Thinking…</div>}
        {error && (
          <p className="text-sm text-amber-300">
            {error.includes("Not signed in") ? (
              <>Sign in first — <Link href="/login" className="underline">login</Link>.</>
            ) : (
              error
            )}
          </p>
        )}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={onSubmit} className="sticky bottom-0 mt-6 flex gap-2 bg-inherit py-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about a ticker, signal, or setup…"
          className="flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-500"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="rounded-lg bg-zinc-200 px-4 py-2 text-sm font-medium text-zinc-900 disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </main>
  );
}
