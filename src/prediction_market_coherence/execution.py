from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal

from .models import (
    ONE,
    ZERO,
    BookLevel,
    ExecutionCandidate,
    OrderBook,
    Relationship,
    TradeLeg,
)
from .payoff import analyze_payoff, canonical_hedge_sides


@dataclass(frozen=True, slots=True)
class FillEstimate:
    requested: Decimal
    filled: Decimal
    notional: Decimal
    average_price: Decimal | None
    worst_price: Decimal | None

    @property
    def complete(self) -> bool:
        return self.filled == self.requested


def consume_asks(levels: tuple[BookLevel, ...], quantity: Decimal) -> FillEstimate:
    if quantity <= ZERO:
        raise ValueError("quantity must be positive")
    remaining = quantity
    filled = ZERO
    notional = ZERO
    worst: Decimal | None = None
    for level in levels:
        take = min(remaining, level.size)
        if take <= ZERO:
            continue
        filled += take
        notional += take * level.price
        worst = level.price
        remaining -= take
        if remaining == ZERO:
            break
    average = notional / filled if filled > ZERO else None
    return FillEstimate(quantity, filled, notional, average, worst)


def _breakpoints(*level_sets: tuple[BookLevel, ...]) -> list[Decimal]:
    points: set[Decimal] = set()
    for levels in level_sets:
        running = ZERO
        for level in levels:
            running += level.size
            points.add(running)
    return sorted(points)


def build_two_leg_candidate(
    relationship: Relationship,
    books: dict[str, OrderBook],
    *,
    min_edge: Decimal = ZERO,
    max_quantity: Decimal | None = None,
) -> ExecutionCandidate | None:
    if len(relationship.market_ids) != 2:
        raise ValueError("two-leg candidate supports binary relationships only")
    a, b = relationship.market_ids
    if a not in books or b not in books:
        return None

    book_a = books[a]
    book_b = books[b]
    # Explicit Super Market tournament contexts must never be mixed. Legacy
    # replay books have no `received_at` marker and remain context-agnostic.
    if book_a.context_id != book_b.context_id and (
        book_a.context_id is not None or book_b.context_id is not None
    ):
        return None

    official_book = book_a.received_at is not None or book_b.received_at is not None
    unversioned_official = official_book and (
        book_a.source_sequence is None or book_b.source_sequence is None
    )
    implicit_official_context = official_book and (
        book_a.context_id is None or book_b.context_id is None
    )

    sides = canonical_hedge_sides(relationship)
    asks_a = books[a].asks(sides[0])
    asks_b = books[b].asks(sides[1])
    if not asks_a or not asks_b:
        return None

    best_quantity = ZERO
    best_cost_per_bundle: Decimal | None = None
    best_profit = ZERO
    for q in _breakpoints(asks_a, asks_b):
        if max_quantity is not None and q > max_quantity:
            q = max_quantity
        if q <= ZERO:
            continue
        fa = consume_asks(asks_a, q)
        fb = consume_asks(asks_b, q)
        if not fa.complete or not fb.complete:
            continue
        total_cost = fa.notional + fb.notional
        # unit-size synthetic legs only for truth-table analysis
        unit_legs = (
            TradeLeg(a, sides[0], ONE, fa.average_price or ONE),
            TradeLeg(b, sides[1], ONE, fb.average_price or ONE),
        )
        guaranteed = analyze_payoff(relationship, unit_legs).minimum_payout
        cost_per_bundle = total_cost / q
        edge = guaranteed - cost_per_bundle
        if edge >= min_edge:
            profit = edge * q
            if profit > best_profit or (profit == best_profit and q > best_quantity):
                best_quantity = q
                best_cost_per_bundle = cost_per_bundle
                best_profit = profit
        if max_quantity is not None and q == max_quantity:
            break

    if best_quantity <= ZERO or best_cost_per_bundle is None:
        return None

    fa = consume_asks(asks_a, best_quantity)
    fb = consume_asks(asks_b, best_quantity)
    unit_legs = (
        TradeLeg(a, sides[0], ONE, fa.average_price or ONE),
        TradeLeg(b, sides[1], ONE, fb.average_price or ONE),
    )
    guaranteed = analyze_payoff(relationship, unit_legs).minimum_payout
    edge = guaranteed - best_cost_per_bundle
    max_age = max(book_a.age_seconds(), book_b.age_seconds())
    raw_id = f"{relationship.relation_id}|{best_quantity}|{best_cost_per_bundle}"
    candidate_id = hashlib.sha256(raw_id.encode()).hexdigest()[:16]
    return ExecutionCandidate(
        candidate_id=candidate_id,
        relationship_id=relationship.relation_id,
        legs=(
            TradeLeg(a, sides[0], best_quantity, fa.worst_price or fa.average_price or ONE),
            TradeLeg(b, sides[1], best_quantity, fb.worst_price or fb.average_price or ONE),
        ),
        guaranteed_payout_per_bundle=guaranteed,
        cost_per_bundle=best_cost_per_bundle,
        executable_edge_per_bundle=edge,
        max_profitable_quantity=best_quantity,
        expected_profit=edge * best_quantity,
        book_age_seconds=max_age,
        theoretical_only=unversioned_official or implicit_official_context,
        metadata={
            "avg_price_a": str(fa.average_price),
            "avg_price_b": str(fb.average_price),
            "worst_price_a": str(fa.worst_price),
            "worst_price_b": str(fb.worst_price),
            "context_id": book_a.context_id,
            "source_sequence_a": book_a.source_sequence,
            "source_sequence_b": book_b.source_sequence,
            "official_book": official_book,
        },
    )
