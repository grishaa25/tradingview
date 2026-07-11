"""NIFTY 50 constituents with approximate free-float weights (% of index).

Static snapshot — NSE publishes exact weights monthly in the "Index Factsheet"
PDF but offers no free JSON API, and weights drift slowly (rebalanced
semi-annually). compute_contributions() normalizes by the sum, so small
staleness shifts every contribution proportionally instead of breaking math.
Refresh by pasting from https://www.niftyindices.com factsheet when needed.
"""

NIFTY50_WEIGHTS: dict[str, float] = {
    "HDFCBANK": 13.0,
    "ICICIBANK": 9.0,
    "RELIANCE": 8.2,
    "INFY": 5.0,
    "BHARTIARTL": 4.5,
    "LT": 4.0,
    "TCS": 3.8,
    "ITC": 3.6,
    "SBIN": 3.1,
    "AXISBANK": 3.0,
    "M&M": 2.6,
    "KOTAKBANK": 2.5,
    "BAJFINANCE": 2.3,
    "HINDUNILVR": 1.9,
    "SUNPHARMA": 1.8,
    "NTPC": 1.5,
    "HCLTECH": 1.5,
    "MARUTI": 1.5,
    "TITAN": 1.3,
    "ULTRACEMCO": 1.3,
    "TMPV": 1.2,          # Tata Motors PV (post-2025 demerger listing)
    "POWERGRID": 1.2,
    "ASIANPAINT": 1.1,
    "BAJAJFINSV": 1.0,
    "ONGC": 1.0,
    "ADANIPORTS": 1.0,
    "ETERNAL": 1.0,       # ex-Zomato, joined NIFTY 50 in 2025
    "TATASTEEL": 0.9,
    "GRASIM": 0.9,
    "TRENT": 0.9,
    "BEL": 0.9,
    "BAJAJ-AUTO": 0.9,
    "COALINDIA": 0.9,
    "NESTLEIND": 0.8,
    "JSWSTEEL": 0.8,
    "ADANIENT": 0.8,
    "HINDALCO": 0.8,
    "JIOFIN": 0.8,
    "WIPRO": 0.7,
    "TECHM": 0.7,
    "CIPLA": 0.7,
    "SBILIFE": 0.6,
    "EICHERMOT": 0.6,
    "SHRIRAMFIN": 0.6,
    "DRREDDY": 0.6,
    "HDFCLIFE": 0.6,
    "APOLLOHOSP": 0.6,
    "TATACONSUM": 0.5,
    "HEROMOTOCO": 0.5,
    "INDUSINDBK": 0.4,
}
