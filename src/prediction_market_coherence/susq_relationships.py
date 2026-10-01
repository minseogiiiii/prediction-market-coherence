from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .models import Relationship
from .relationships import complement, implication, mutually_exclusive


@dataclass(frozen=True, slots=True)
class CorrectiveTrade:
    exchange_id: str
    outcome_side: str
    action: str
    rationale: str
    current_price: Decimal | None


@dataclass(frozen=True, slots=True)
class ConstraintEvaluation:
    relationship_id: str
    relationship_type: str
    status: str
    violation_amount: Decimal
    reason: str
    tournament_id: str | None
    corrective_trades: tuple[CorrectiveTrade, ...]
    observed_prices: dict[str, Decimal]
    raw: dict[str, Any]

    @property
    def violated(self) -> bool:
        return self.status == "violated" and self.violation_amount > 0


def relationship_from_official(raw: dict[str, Any]) -> Relationship | None:
    """Translate simple canonical ALL relationships into local truth tables.

    Complex boolean-expression relationships stay authoritative-only for now;
    returning None is safer than inventing truth semantics.
    """
    if raw.get("status") != "active":
        return None
    relation_id = str(raw.get("id") or "")
    relation_type = str(raw.get("type") or "")
    if not relation_id:
        raise ValueError("official relationship is missing id")

    nodes = raw.get("nodes")
    if not isinstance(nodes, list):
        raise TypeError("official relationship nodes must be a list")
    node_ids = [str(node.get("exchangeId")) for node in nodes if isinstance(node, dict)]
    evidence = _evidence(raw)

    if relation_type == "implication":
        antecedents = _role_ids(nodes, "antecedent")
        consequents = _role_ids(nodes, "consequent")
        if len(antecedents) == len(consequents) == 1:
            rel = implication(relation_id, antecedents[0], consequents[0], evidence=evidence)
            return _official(rel)
        return None

    if relation_type == "monotonic":
        direction = raw.get("direction")
        if not isinstance(direction, dict):
            return None
        from_ids = tuple(str(x) for x in direction.get("fromExchangeIds", []))
        to_ids = tuple(str(x) for x in direction.get("toExchangeIds", []))
        if len(from_ids) == len(to_ids) == 1:
            rel = implication(relation_id, from_ids[0], to_ids[0], evidence=evidence)
            return _official(rel)
        return None

    if relation_type == "complementary" and len(node_ids) == 2:
        rel = complement(relation_id, node_ids[0], node_ids[1], evidence=evidence)
        return _official(rel)

    if relation_type == "mutually_exclusive" and len(node_ids) == 2:
        if bool(raw.get("isExhaustive")):
            rel = complement(relation_id, node_ids[0], node_ids[1], evidence=evidence)
        else:
            rel = mutually_exclusive(relation_id, node_ids[0], node_ids[1], evidence=evidence)
        return _official(rel)

    return None


def constraint_from_official(raw: dict[str, Any]) -> ConstraintEvaluation:
    relationship_id = str(_required(raw, "relationshipId"))
    relationship_type = str(_required(raw, "type"))
    status = str(_required(raw, "evaluationStatus"))
    violation_amount = _decimal(_required(raw, "violationAmount"))
    tournament = raw.get("tournamentId")

    corrective: list[CorrectiveTrade] = []
    for item in raw.get("suggestedCorrectiveTrades") or []:
        if not isinstance(item, dict):
            raise TypeError("suggestedCorrectiveTrades entries must be objects")
        price = item.get("currentPrice")
        corrective.append(
            CorrectiveTrade(
                exchange_id=str(_required(item, "exchangeId")),
                outcome_side=str(_required(item, "outcomeSide")),
                action=str(_required(item, "action")),
                rationale=str(_required(item, "rationale")),
                current_price=None if price is None else _decimal(price),
            )
        )

    observed: dict[str, Decimal] = {}
    for item in raw.get("observedPrices") or []:
        if not isinstance(item, dict):
            raise TypeError("observedPrices entries must be objects")
        observed[str(_required(item, "exchangeId"))] = _decimal(_required(item, "price"))

    return ConstraintEvaluation(
        relationship_id=relationship_id,
        relationship_type=relationship_type,
        status=status,
        violation_amount=violation_amount,
        reason=str(_required(raw, "reason")),
        tournament_id=None if tournament is None else str(tournament),
        corrective_trades=tuple(corrective),
        observed_prices=observed,
        raw=raw,
    )


def parse_constraints_response(payload: dict[str, Any]) -> tuple[ConstraintEvaluation, ...]:
    data = payload.get("data")
    if not isinstance(data, list):
        raise TypeError("constraints response data must be a list")
    return tuple(constraint_from_official(item) for item in data if isinstance(item, dict))


def _role_ids(nodes: list[Any], role: str) -> tuple[str, ...]:
    return tuple(
        str(node["exchangeId"])
        for node in nodes
        if isinstance(node, dict) and node.get("role") == role and node.get("exchangeId") is not None
    )


def _evidence(raw: dict[str, Any]) -> str:
    direction = raw.get("direction")
    if isinstance(direction, dict) and direction.get("description"):
        return str(direction["description"])
    if raw.get("label"):
        return str(raw["label"])
    constraint = raw.get("constraint")
    if isinstance(constraint, dict) and constraint.get("description"):
        return str(constraint["description"])
    return "Super Market canonical ALL relationship"


def _official(rel: Relationship) -> Relationship:
    return Relationship(
        relation_id=rel.relation_id,
        kind=rel.kind,
        market_ids=rel.market_ids,
        allowed_states=rel.allowed_states,
        source="super_market_all",
        evidence=rel.evidence,
    )


def _required(payload: dict[str, Any], key: str) -> Any:
    if key not in payload:
        raise KeyError(f"missing required field {key!r}")
    return payload[key]


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise TypeError(f"expected numeric value, got {value!r}") from exc
