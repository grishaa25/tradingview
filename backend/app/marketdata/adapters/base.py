"""Broker data adapter interface.

Concrete adapters (angelone.py, dhan.py) implement this; everything else in
the platform talks to BrokerDataInterface only, so swapping brokers is a
one-file change (PRD §14).
"""

from abc import ABC, abstractmethod
from datetime import datetime


class BrokerDataInterface(ABC):
    @abstractmethod
    async def get_historical_candles(
        self, ticker: str, tf: str, start: datetime, end: datetime
    ) -> list[dict]:
        """Returns [{ts, o, h, l, c, v, oi}] for the ticker/timeframe."""

    @abstractmethod
    async def get_quote(self, ticker: str) -> dict:
        """Returns the latest quote (ltp, volume, oi...)."""

    @abstractmethod
    async def get_option_chain(self, ticker: str, expiry: str) -> list[dict]:
        """Returns normalized chain rows (strike, opt_type, ltp, oi, iv...)."""
