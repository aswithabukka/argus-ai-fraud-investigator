"""Long-term fraud-pattern store.

A simple JSON-backed list of confirmed fraud patterns. The Analyzer consults it
so lessons from past cases sharpen future triage; when a case is confirmed
fraudulent (in the eval loop, via the ground-truth label at approval time) a new
pattern can be recorded. This demonstrates memory that actually influences later
cases, not just storage.

A pattern is a small, matchable descriptor:
    {"id", "description", "match": {"type": "TRANSFER", "balance_drained": true,
                                     "counterparty_zero_balance": true}}
"""

from __future__ import annotations

import json
from typing import Any

import config

# Seed patterns: the two canonical PaySim fraud shapes, so the store is useful
# from the first case even before anything is learned at runtime. Both key on the
# EXACT-to-the-cent drain — the scripted "send everything" sweep — not fuzzy
# near-drains, which legitimate large cash-outs also produce.
_SEED = [
    {
        "id": "exact_drain_to_mule",
        "description": "TRANSFER that empties the origin balance to the exact cent into "
                       "a counterparty whose recorded balance stays at zero (pass-through mule).",
        "match": {"type": "TRANSFER", "exact_drain": True, "counterparty_zero_balance": True},
    },
    {
        "id": "exact_cashout_drain",
        "description": "CASH_OUT of the entire origin balance to the exact cent in a single move.",
        "match": {"type": "CASH_OUT", "exact_drain": True},
    },
]


def _load() -> list[dict[str, Any]]:
    if config.PATTERN_STORE_PATH.exists():
        return json.loads(config.PATTERN_STORE_PATH.read_text())
    _save(_SEED)
    return list(_SEED)


def _save(patterns: list[dict]) -> None:
    config.PATTERN_STORE_PATH.write_text(json.dumps(patterns, indent=2))


def match_patterns(features: dict[str, Any]) -> list[str]:
    """Return descriptions of stored patterns whose match-conditions all hold
    for the given case features."""
    hits = []
    for p in _load():
        if all(features.get(k) == v for k, v in p["match"].items()):
            hits.append(p["description"])
    return hits


def add_pattern(pattern: dict[str, Any]) -> None:
    patterns = _load()
    if any(p["id"] == pattern["id"] for p in patterns):
        return
    patterns.append(pattern)
    _save(patterns)


def reset() -> None:
    """Restore the store to seed patterns (used at the start of an eval run)."""
    _save(_SEED)
