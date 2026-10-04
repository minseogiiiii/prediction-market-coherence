from decimal import Decimal

from prediction_market_coherence.models import RelationType
from prediction_market_coherence.susq_relationships import (
    constraint_from_official,
    relationship_from_official,
)


def node(exchange_id, role="member"):
    return {
        "exchangeId": str(exchange_id),
        "marketId": "1",
        "marketTitle": "x",
        "outcome": "YES",
        "currentPrice": 0.5,
        "role": role,
        "contractId": "market:1",
    }


def test_implication_relationship_maps_roles_to_truth_table():
    raw = {
        "id": "r1",
        "type": "implication",
        "status": "active",
        "nodes": [node(10, "antecedent"), node(11, "consequent")],
        "direction": {"description": "A implies B"},
    }
    rel = relationship_from_official(raw)
    assert rel is not None
    assert rel.kind is RelationType.IMPLIES
    assert rel.exchange_ids == ("10", "11")
    assert rel.source == "super_market_all"


def test_monotonic_relationship_uses_official_direction():
    raw = {
        "id": "r2",
        "type": "monotonic",
        "status": "active",
        "nodes": [node(10), node(11)],
        "direction": {
            "fromExchangeIds": ["11"],
            "toExchangeIds": ["10"],
            "description": "higher threshold implies lower threshold",
        },
    }
    rel = relationship_from_official(raw)
    assert rel is not None
    assert rel.exchange_ids == ("11", "10")


def test_two_member_exhaustive_mutex_maps_to_complement():
    raw = {
        "id": "r3",
        "type": "mutually_exclusive",
        "status": "active",
        "isExhaustive": True,
        "nodes": [node(10), node(11)],
        "label": "exactly one",
    }
    rel = relationship_from_official(raw)
    assert rel is not None
    assert rel.kind is RelationType.COMPLEMENT


def test_complex_relationship_fails_closed():
    raw = {
        "id": "r4",
        "type": "boolean_expression",
        "status": "active",
        "nodes": [node(10), node(11)],
    }
    assert relationship_from_official(raw) is None


def test_constraint_parser_keeps_authoritative_fields():
    raw = {
        "relationshipId": "r1",
        "type": "implication",
        "violationAmount": 0.05,
        "reason": "bound exceeded",
        "suggestedCorrectiveTrades": [
            {
                "exchangeId": "10",
                "outcomeSide": "Yes",
                "action": "Buy",
                "rationale": "restore bound",
                "marketId": "1",
                "marketTitle": "x",
                "outcome": "YES",
                "currentPrice": 0.4,
            }
        ],
        "observedPrices": [
            {
                "exchangeId": "10",
                "price": 0.4,
                "marketId": "1",
                "marketTitle": "x",
                "outcome": "YES",
                "currentPrice": 0.4,
            }
        ],
        "bound": 0.35,
        "lowerBound": None,
        "upperBound": 0.35,
        "currentValue": 0.4,
        "evaluationStatus": "violated",
        "diagnostic": None,
        "tournamentId": "tid",
        "direction": {},
        "constraint": {},
    }
    result = constraint_from_official(raw)
    assert result.violated
    assert result.violation_amount == Decimal("0.05")
    assert result.observed_prices == {"10": Decimal("0.4")}
    assert result.corrective_trades[0].exchange_id == "10"
