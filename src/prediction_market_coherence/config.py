from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal


def _dec(name: str, default: str) -> Decimal:
    return Decimal(os.getenv(name, default))


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """Fail-closed runtime configuration.

    Live trading is disabled unless both `allow_live_trading` and a one-time
    acknowledgement token are explicitly set by the caller. Environment values
    are read only by `from_env`; importing this module has no side effects.
    """

    allow_live_trading: bool = False
    acknowledgement: str | None = None
    min_edge: Decimal = Decimal("0.01")
    max_order_size: Decimal = Decimal(100)
    max_market_exposure: Decimal = Decimal(2500)
    max_total_exposure: Decimal = Decimal(20000)
    min_cash_buffer: Decimal = Decimal(5000)
    max_book_age_seconds: Decimal = Decimal(2)
    max_slippage: Decimal = Decimal("0.01")

    @classmethod
    def from_env(cls) -> RuntimeConfig:
        return cls(
            allow_live_trading=os.getenv("PMC_ALLOW_LIVE_TRADING", "0") == "1",
            acknowledgement=os.getenv("PMC_LIVE_ACK"),
            min_edge=_dec("PMC_MIN_EDGE", "0.01"),
            max_order_size=_dec("PMC_MAX_ORDER_SIZE", "100"),
            max_market_exposure=_dec("PMC_MAX_MARKET_EXPOSURE", "2500"),
            max_total_exposure=_dec("PMC_MAX_TOTAL_EXPOSURE", "20000"),
            min_cash_buffer=_dec("PMC_MIN_CASH_BUFFER", "5000"),
            max_book_age_seconds=_dec("PMC_MAX_BOOK_AGE_SECONDS", "2"),
            max_slippage=_dec("PMC_MAX_SLIPPAGE", "0.01"),
        )

    def live_enabled(self, expected_ack: str) -> bool:
        return self.allow_live_trading and self.acknowledgement == expected_ack
