"""Pure helpers for the AI assistant: ticker extraction + prompt assembly."""

import re

SYSTEM_PROMPT = """You are the AI assistant inside a personal trading-intelligence \
platform for Indian NSE markets. You help the user interpret market data, scanner \
signals, option-chain analytics, and indicator readings.

Rules:
- Decision support only — never present anything as financial advice; the user \
decides their own trades.
- Ground answers in the MARKET CONTEXT block when one is provided. If the data \
needed isn't there, say so plainly instead of inventing numbers.
- Prices are INR, exchange is NSE, timezone is IST.
- Be concise and concrete; use bullet points for multi-part answers."""

# Ticker-ish tokens: uppercase words ≥2 chars, allowing & and - (M&M, BAJAJ-AUTO)
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z&\-]{1,19}")


def extract_tickers(
    message: str, known: set[str], aliases: dict[str, str] | None = None, cap: int = 8
) -> list[str]:
    """Tickers mentioned in a chat message, resolved through aliases, deduped."""
    aliases = aliases or {}
    seen: list[str] = []
    for token in _TOKEN_RE.findall(message):
        t = aliases.get(token.upper(), token.upper())
        if t in known and t not in seen:
            seen.append(t)
            if len(seen) >= cap:
                break
    return seen


def format_market_context(quotes: list[dict], signals: list[dict]) -> str:
    """Quotes + recent scanner signals → compact block for the system prompt."""
    lines: list[str] = []
    with_data = [q for q in quotes if q.get("has_data")]
    if with_data:
        lines.append("Latest daily closes:")
        for q in with_data:
            chg = f"{q['change_pct']:+.2f}%" if q.get("change_pct") is not None else "n/a"
            lines.append(f"- {q['ticker']}: close {q['close']} ({chg})")
    if signals:
        lines.append("Recent scanner signals (newest first):")
        for s in signals:
            lines.append(f"- {s['ts']}: {s['side'].upper()} {s['ticker']} (scan: {s['scan']})")
    if not lines:
        return ""
    return "MARKET CONTEXT (from the platform's own database):\n" + "\n".join(lines)


def build_messages(
    user_message: str, history: list[dict], market_context: str
) -> list[dict]:
    """Full LLM message list: system (+context), trimmed history, new message."""
    system = SYSTEM_PROMPT + ("\n\n" + market_context if market_context else "")
    msgs = [{"role": "system", "content": system}]
    msgs += [{"role": m["role"], "content": m["content"]} for m in history]
    msgs.append({"role": "user", "content": user_message})
    return msgs
