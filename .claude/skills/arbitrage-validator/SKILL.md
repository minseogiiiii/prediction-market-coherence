# Arbitrage Validator

Separate three claims: logical inconsistency, top-of-book edge, executable edge.

- Never call midpoint mispricing executable.
- Consume visible asks through depth and calculate VWAP, worst price, max profitable size, expected profit.
- Enumerate every allowed settlement state and verify minimum payoff mechanically.
- Require fresh timestamps.
- Report insufficient depth, stale quotes and leg risk explicitly.
- Do not include a trade in the live candidate set if guaranteed edge after configured buffers is non-positive.
