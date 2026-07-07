export default async function Page({
  params,
}: {
  params: Promise<{ symbol: string }>;
}) {
  const { symbol } = await params;
  return (
    <main className="p-8">
      <h1 className="text-xl font-semibold">{symbol.toUpperCase()} — Options</h1>
      <p className="mt-2 text-sm text-zinc-400">
        Phase 2 — chain, analytics, strategy builder.
      </p>
    </main>
  );
}
