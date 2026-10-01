from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .execution import consume_asks
from .ledger import Ledger
from .models import ZERO, ExecutionCandidate, OrderBook


@dataclass(frozen=True, slots=True)
class PaperFill:
    market_id: str
    side: str
    quantity: Decimal
    average_price: Decimal
    notional: Decimal


@dataclass(frozen=True, slots=True)
class PaperExecution:
    candidate_id: str
    success: bool
    fills: tuple[PaperFill, ...]
    reason: str = ""


class PaperBroker:
    """Atomic paper executor for research.

    It only commits the ledger after *all* legs have sufficient visible depth,
    preventing paper-only profits from partial synthetic fills.
    """

    def execute(
        self,
        candidate: ExecutionCandidate,
        books: dict[str, OrderBook],
        ledger: Ledger,
        quantity: Decimal | None = None,
    ) -> PaperExecution:
        q = quantity or candidate.max_profitable_quantity
        if q <= ZERO:
            return PaperExecution(candidate.candidate_id, False, (), "non-positive quantity")

        estimates = []
        total = ZERO
        for leg in candidate.legs:
            book = books.get(leg.market_id)
            if book is None:
                return PaperExecution(candidate.candidate_id, False, (), "missing book")
            estimate = consume_asks(book.asks(leg.side), q)
            if not estimate.complete or estimate.average_price is None:
                return PaperExecution(candidate.candidate_id, False, (), "insufficient depth")
            if estimate.worst_price is not None and estimate.worst_price > leg.max_price:
                return PaperExecution(candidate.candidate_id, False, (), "slippage beyond candidate")
            estimates.append((leg, estimate))
            total += estimate.notional

        if total > ledger.cash:
            return PaperExecution(candidate.candidate_id, False, (), "insufficient cash")

        fills: list[PaperFill] = []
        for leg, estimate in estimates:
            ledger.apply_buy(leg.market_id, leg.side, q, estimate.average_price)
            fills.append(
                PaperFill(
                    leg.market_id,
                    leg.side.value,
                    q,
                    estimate.average_price,
                    estimate.notional,
                )
            )
        return PaperExecution(candidate.candidate_id, True, tuple(fills))
