"use client";

// Official TradingView embed widget (free) — full TradingView chart with
// your Pro account's indicators/layouts once you're logged in to
// tradingview.com in the same browser.
export default function TradingViewEmbed({ ticker }: { ticker: string }) {
  const params = new URLSearchParams({
    symbol: `NSE:${ticker}`,
    interval: "60",
    theme: "dark",
    style: "1",
    locale: "en",
    timezone: "Asia/Kolkata",
    withdateranges: "1",
    hide_side_toolbar: "0",
    allow_symbol_change: "1",
  });
  return (
    <iframe
      key={ticker}
      src={`https://s.tradingview.com/widgetembed/?${params.toString()}`}
      className="h-[480px] w-full rounded border border-zinc-800"
      allow="fullscreen"
      title={`TradingView chart for ${ticker}`}
    />
  );
}
