"""Policy agent — a deterministic rules engine, NOT an LLM.

Fraud policy and AML rules must be auditable, versioned, and reproducible: a
regulator wants to see the exact rule that fired, not a model's paraphrase. So
Argus implements policy as transparent Python over the (unmasked) case features
and the alerted transaction. Thresholds live in config.py.
"""

from __future__ import annotations

import config
from schemas import PolicyFlag, PolicyResult


def evaluate(txn: dict, velocity: dict, counterparty: dict) -> PolicyResult:
    flags: list[PolicyFlag] = []

    amount = txn.get("amount", 0)
    old_bal = txn.get("oldbalanceOrg", 0)
    new_bal = txn.get("newbalanceOrig", 0)

    # 1. Large transfer over the reporting threshold.
    flags.append(PolicyFlag(
        rule="large_transfer",
        triggered=amount >= config.LARGE_TRANSFER_THRESHOLD,
        severity="medium",
        detail=f"amount={amount:,.2f} vs threshold {config.LARGE_TRANSFER_THRESHOLD:,}",
    ))

    # 2. EXACT drain — the transaction empties the account to the cent. This is
    # the signature of an account-takeover sweep: a fraudster scripts "send
    # everything", while a legitimate customer cashes out a chosen (usually
    # round) amount and leaves residue. Fuzzy near-drains are only medium.
    exact_drain = old_bal > 0 and amount == old_bal
    flags.append(PolicyFlag(
        rule="exact_balance_drain",
        triggered=bool(exact_drain),
        severity="high",
        detail=f"amount={amount:,.2f} == oldbalanceOrg={old_bal:,.2f}: {exact_drain}",
    ))

    near_drain = old_bal > 0 and not exact_drain and new_bal <= old_bal * (1 - config.BALANCE_DRAIN_RATIO)
    flags.append(PolicyFlag(
        rule="near_balance_drain",
        triggered=bool(near_drain),
        severity="medium",
        detail=f"oldbalanceOrg={old_bal:,.2f} -> newbalanceOrig={new_bal:,.2f}",
    ))

    # 4. Velocity — burst of outgoing transfers in the window.
    vcount = velocity.get("txn_count", 0)
    flags.append(PolicyFlag(
        rule="velocity_burst",
        triggered=vcount >= config.VELOCITY_COUNT_THRESHOLD,
        severity="medium",
        detail=f"{vcount} outgoing txns in {velocity.get('window_steps')} steps",
    ))

    # 5. Mule-like counterparty. Suspicious on its own but common among busy
    # accounts too, so medium — it corroborates a drain rather than convicts.
    zbr = counterparty.get("zero_balance_rate", 0)
    senders = counterparty.get("distinct_senders", 0)
    is_merchant = counterparty.get("is_merchant", False)
    flags.append(PolicyFlag(
        rule="mule_counterparty",
        triggered=bool((not is_merchant) and zbr >= 0.5 and senders >= 2),
        severity="medium",
        detail=f"zero_balance_rate={zbr}, distinct_senders={senders}, merchant={is_merchant}",
    ))

    high_hit = any(f.triggered and f.severity == "high" for f in flags)
    n_hit = sum(f.triggered for f in flags)

    if high_hit:
        disposition, reason = config.ESCALATE, "a high-severity policy rule fired"
    elif n_hit >= 3:
        disposition, reason = config.ESCALATE, f"{n_hit} medium policy rules fired"
    else:
        disposition, reason = config.CLEAR, "no high-severity policy rule fired"

    return PolicyResult(flags=flags, suggested_disposition=disposition, reason=reason)
