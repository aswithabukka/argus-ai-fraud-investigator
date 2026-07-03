"""Model router — cost-aware tiered escalation.

Most alerts are routine: a fast, cheap model handles them end-to-end. The
expensive model is reserved for the cases where its extra judgment can change
the outcome:

  * AMBIGUOUS  — the analyzer's risk score sits in the uncertain middle band,
  * DISAGREEMENT — the LLM and the deterministic policy engine point in
    opposite directions,
  * HIGH STAKES — very large amounts, where a wrong call is costly either way.

Clear-cut cases (e.g. an exact drain to a mule account: high risk, zero doubt)
do NOT need the strong model — high risk is not the same as high uncertainty.

The routing decision is logged to the audit trail like every other step, so an
auditor can see not just what was decided but which model tier decided it.
"""

from __future__ import annotations

import config
from schemas import PolicyResult, RiskAssessment

# The analyzer prompt calibrates: lookalikes 0.1-0.4, ambiguous 0.4-0.7,
# confident fraud 0.85+. The band between "probably fine" and "certainly fraud"
# is where a second, stronger opinion pays for itself.
AMBIGUOUS_LOW = 0.35
AMBIGUOUS_HIGH = 0.85
HIGH_STAKES_AMOUNT = 1_000_000  # a wrong call on $1M+ justifies the extra cents


def decide_tier(assessment: RiskAssessment, policy: PolicyResult,
                amount: float) -> tuple[str, str]:
    """Return ("standard" | "elevated", human-readable reason)."""
    model_escalates = assessment.risk_score >= AMBIGUOUS_HIGH
    policy_escalates = policy.suggested_disposition == config.ESCALATE

    if AMBIGUOUS_LOW <= assessment.risk_score < AMBIGUOUS_HIGH:
        return ("elevated",
                f"risk score {assessment.risk_score:.2f} is in the ambiguous band "
                f"[{AMBIGUOUS_LOW}, {AMBIGUOUS_HIGH}) — second opinion warranted")
    if model_escalates != policy_escalates:
        return ("elevated",
                f"model ({assessment.risk_score:.2f}) and policy "
                f"({policy.suggested_disposition}) disagree — strong model arbitrates")
    if amount >= HIGH_STAKES_AMOUNT:
        return ("elevated",
                f"amount ${amount:,.0f} exceeds high-stakes threshold "
                f"${HIGH_STAKES_AMOUNT:,} — extra scrutiny is cheap insurance")
    return ("standard",
            "clear-cut case (model and policy agree, outside the ambiguous band) — "
            "standard model is sufficient")
