import Link from "next/link";

const modules = [
  { href: "/watchlist", label: "Watchlist", phase: "live" },
  { href: "/charts/RELIANCE", label: "Charts", phase: "live" },
  { href: "/scanner", label: "Scanner", phase: "live" },
  { href: "/assistant", label: "AI Assistant", phase: "live" },
  { href: "/options/NIFTY", label: "Options", phase: "live" },
  { href: "/impact", label: "Nifty Impact", phase: "live" },
  { href: "/portfolio", label: "Portfolio & Risk", phase: "P2" },
  { href: "/news", label: "News", phase: "P2" },
  { href: "/backtest", label: "Backtest", phase: "P3" },
];

export default function Home() {
  return (
    <main className="mx-auto max-w-4xl p-8">
      <h1 className="text-2xl font-semibold">Trading Intelligence Platform</h1>
      <p className="mt-2 text-sm text-zinc-400">
        Decision support only — not investment advice. See docs/PRD.md for the
        roadmap.
      </p>
      <ul className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
        {modules.map((m) => (
          <li key={m.href}>
            <Link
              href={m.href}
              className="block rounded-lg border border-zinc-800 p-4 hover:border-zinc-600"
            >
              <span className="block font-medium">{m.label}</span>
              <span className="text-xs text-zinc-500">{m.phase}</span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
