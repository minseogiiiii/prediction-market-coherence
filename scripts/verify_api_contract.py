from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from prediction_market_coherence.susq_client import OFFICIAL_BASE_URL, EndpointMap

REQUIRED_OPERATIONS = {
    "GET /markets",
    "GET /markets/{id}",
    "GET /markets/{id}/orderbook",
    "GET /exchanges",
    "GET /exchanges/{id}/price",
    "GET /exchanges/{id}/orderbook",
    "GET /exchanges/prices",
    "POST /orders",
    "POST /orders/multi-leg",
    "GET /orders/{id}",
    "DELETE /orders/{id}",
    "GET /orders/{id}/fills",
    "GET /portfolio/collateral",
    "GET /portfolio/positions",
    "GET /portfolio/pnl",
    "GET /account",
    "GET /tournaments",
    "GET /tournaments/{slug}",
    "GET /tournaments/{slug}/markets",
    "POST /realtime/token",
    "GET /relationships",
    "GET /relationships/graph",
    "GET /relationships/constraints",
}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Verify code assumptions against extracted OpenAPI audit")
    p.add_argument("audit", type=Path)
    return p


def main() -> int:
    args = parser().parse_args()
    payload = json.loads(args.audit.read_text())
    errors: list[str] = []

    if payload.get("openapi") != "3.1.0":
        errors.append(f"unexpected OpenAPI version: {payload.get('openapi')!r}")

    servers = payload.get("servers") or []
    urls = {row.get("url") for row in servers if isinstance(row, dict)}
    if OFFICIAL_BASE_URL not in urls:
        errors.append(f"official base URL {OFFICIAL_BASE_URL!r} not present in servers")

    schemes = payload.get("security_schemes") or {}
    bearer = schemes.get("bearerAuth") if isinstance(schemes, dict) else None
    if not isinstance(bearer, dict) or bearer.get("type") != "http" or bearer.get("scheme") != "bearer":
        errors.append("bearerAuth is no longer HTTP bearer auth")

    operations = payload.get("operations") or {}
    missing = sorted(REQUIRED_OPERATIONS - set(operations))
    if missing:
        errors.append("missing operations: " + ", ".join(missing))

    endpoints = EndpointMap()
    expected_paths = {
        endpoints.markets,
        endpoints.market,
        endpoints.market_orderbook,
        endpoints.exchanges,
        endpoints.exchange_price,
        endpoints.exchange_orderbook,
        endpoints.bulk_prices,
        endpoints.orders,
        endpoints.multi_leg_orders,
        endpoints.order,
        endpoints.order_fills,
        endpoints.account,
        endpoints.positions,
        endpoints.pnl,
        endpoints.collateral,
        endpoints.tournaments,
        endpoints.tournament,
        endpoints.tournament_markets,
        endpoints.relationships,
        endpoints.relationship_graph,
        endpoints.relationship_constraints,
        endpoints.realtime_token,
    }
    operation_paths = {key.split(" ", 1)[1] for key in operations}
    missing_paths = sorted(expected_paths - operation_paths)
    if missing_paths:
        errors.append("EndpointMap paths missing from OpenAPI: " + ", ".join(missing_paths))

    refs = payload.get("referenced_components") or {}
    order_input = _ref(refs, "OrderInput", errors)
    if isinstance(order_input, dict):
        required = set(order_input.get("required") or [])
        if required != {"exchangeId", "side", "action", "quantity"}:
            errors.append(f"OrderInput required fields changed: {sorted(required)}")
        props = order_input.get("properties") or {}
        price = props.get("price") if isinstance(props, dict) else None
        if not isinstance(price, dict) or price.get("minimum") != 0 or price.get("maximum") != 1:
            errors.append("OrderInput.price bounds changed")

    single = _ref(refs, "SingleOrderInput", errors)
    if isinstance(single, dict):
        text = json.dumps(single)
        if "idempotencyKey" not in text:
            errors.append("SingleOrderInput no longer requires idempotencyKey")

    level = _ref(refs, "ExchangeOrderbookLevel", errors)
    if isinstance(level, dict):
        props = level.get("properties") or {}
        if set(props) != {"price", "quantity"}:
            errors.append(f"ExchangeOrderbookLevel fields changed: {sorted(props)}")

    multi = operations.get("POST /orders/multi-leg")
    if isinstance(multi, dict):
        description = str(multi.get("description") or "")
        if "All legs succeed or none are persisted" not in description:
            errors.append("multi-leg atomicity guarantee text changed or disappeared")
        body = multi.get("requestBody") or {}
        body_text = json.dumps(body)
        for field in ("legs", "idempotencyKey", "relationshipConstraint"):
            if field not in body_text:
                errors.append(f"multi-leg request no longer exposes {field}")

    if errors:
        print("API_CONTRACT status=FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        "API_CONTRACT status=OK "
        f"openapi={payload.get('openapi')} operations={len(operations)} base={OFFICIAL_BASE_URL}"
    )
    return 0


def _ref(refs: Any, name: str, errors: list[str]) -> Any:
    key = f"#/components/schemas/{name}"
    if not isinstance(refs, dict) or key not in refs:
        errors.append(f"missing referenced component {name}")
        return None
    return refs[key]


if __name__ == "__main__":
    raise SystemExit(main())
