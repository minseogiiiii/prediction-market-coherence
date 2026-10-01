from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .models import ZERO, Side


@dataclass(slots=True)
class Ledger:
    cash: Decimal
    positions: dict[tuple[str, Side], Decimal] = field(default_factory=dict)

    def apply_buy(self, market_id: str, side: Side, quantity: Decimal, price: Decimal) -> None:
        if quantity <= ZERO or price <= ZERO:
            raise ValueError("quantity and price must be positive")
        cost = quantity * price
        if cost > self.cash:
            raise ValueError("insufficient cash")
        self.cash -= cost
        key = (market_id, side)
        opposite = (market_id, side.opposite)
        # Opposite shares pair and immediately return 1 per pair on the platform.
        pair = min(quantity, self.positions.get(opposite, ZERO))
        if pair > ZERO:
            self.positions[opposite] = self.positions.get(opposite, ZERO) - pair
            self.cash += pair
            quantity -= pair
        if quantity > ZERO:
            self.positions[key] = self.positions.get(key, ZERO) + quantity
        self._drop_zeros()

    def settle(self, market_id: str, outcome: Side) -> Decimal:
        win = self.positions.pop((market_id, outcome), ZERO)
        self.positions.pop((market_id, outcome.opposite), None)
        self.cash += win
        return win

    def _drop_zeros(self) -> None:
        for key in list(self.positions):
            if self.positions[key] == ZERO:
                del self.positions[key]

    def reconcile_positions(self, remote: dict[tuple[str, Side], Decimal]) -> tuple[str, ...]:
        mismatches: list[str] = []
        keys = set(self.positions) | set(remote)
        for key in sorted(keys, key=lambda k: (k[0], k[1].value)):
            local = self.positions.get(key, ZERO)
            actual = remote.get(key, ZERO)
            if local != actual:
                mismatches.append(f"{key[0]}:{key[1].value} local={local} remote={actual}")
        return tuple(mismatches)
