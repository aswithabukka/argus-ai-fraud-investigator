"""Case Assembler + Human Gate.

Deterministically combines the analyzer, policy, and critic outputs into a final
CaseFile and marks it PENDING_HUMAN_APPROVAL. The disposition fuses the LLM risk
score with the deterministic policy result; confidence reflects how strongly they
agree and whether the Critic approved. NOTHING here executes a freeze/block —
`approve_case` is a separate, explicit human step.
"""

from __future__ import annotations

import config
from guardrails.pii import PIIMasker
from schemas import (CaseFile, CriticVerdict, EvidenceBundle, PolicyResult,
                     RiskAssessment)

# The model is confident enough to escalate on its own above this score
# (the analyzer prompt calibrates: lookalikes 0.1-0.4, ambiguous 0.4-0.7,
# confident fraud 0.85+ — so 0.7 = the model genuinely believes it)...
RISK_ESCALATE_THRESHOLD = 0.7
# ...or a high-severity policy rule can escalate if the model corroborates it
# at least this much. Requiring corroboration is the score-fusion step: it stops
# the recall-first policy engine from escalating every legitimate high-value
# cash-out, while still letting policy catch fraud the model under-weights.
POLICY_CORROBORATION_THRESHOLD = 0.35


def assemble(bundle: EvidenceBundle, assessment: RiskAssessment,
             policy: PolicyResult, critic: CriticVerdict,
             masker: PIIMasker, audit_path: str | None = None,
             routing_tier: str | None = None,
             routing_reason: str | None = None) -> CaseFile:
    model_score = assessment.risk_score
    has_high_policy = any(f.triggered and f.severity == "high" for f in policy.flags)
    policy_says_escalate = policy.suggested_disposition == config.ESCALATE

    # Score fusion of the LLM risk assessment and the deterministic policy engine.
    if model_score >= RISK_ESCALATE_THRESHOLD:
        disposition = config.ESCALATE
    elif has_high_policy and model_score >= POLICY_CORROBORATION_THRESHOLD:
        disposition = config.ESCALATE
    else:
        disposition = config.CLEAR

    # Confidence: high when the model and policy agree and the critic approved.
    model_says_escalate = model_score >= RISK_ESCALATE_THRESHOLD
    agree = model_says_escalate == policy_says_escalate
    confidence = 0.9 if (agree and critic.approved) else 0.65 if agree else 0.5

    summary = _summarize(disposition, assessment, policy, bundle)

    case = CaseFile(
        txn_id=bundle.txn_id,
        disposition=disposition,
        confidence=confidence,
        summary=summary,
        evidence=bundle,
        risk_assessment=assessment,
        policy_result=policy,
        critic_verdict=critic,
        matched_patterns=bundle.known_patterns,
        status="PENDING_HUMAN_APPROVAL",
        audit_trail_path=audit_path,
        routing_tier=routing_tier,
        routing_reason=routing_reason,
    )
    # Unmask account ids in the final, local case file for the human analyst.
    return _unmask_case(case, masker)


def _summarize(disposition, assessment, policy, bundle) -> str:
    top = sorted(assessment.signals, key=lambda s: {"high": 0, "medium": 1, "low": 2}
                 .get(s.severity, 3))[:3]
    signal_str = "; ".join(f"{s.name} ({s.severity})" for s in top) or "none"
    fired = [f.rule for f in policy.flags if f.triggered] or ["none"]
    pattern_note = (f" Matches known pattern(s): {', '.join(bundle.known_patterns)}."
                    if bundle.known_patterns else "")
    return (f"Recommendation: {disposition} (risk_score={assessment.risk_score:.2f}). "
            f"Top signals: {signal_str}. Policy rules fired: {', '.join(fired)}."
            f"{pattern_note}")


def _unmask_case(case: CaseFile, masker: PIIMasker) -> CaseFile:
    data = masker.unmask(case.model_dump())
    return CaseFile(**data)


def approve_case(case: CaseFile, approver: str, approved: bool) -> CaseFile:
    """The explicit human-in-the-loop gate. Only here does a case leave PENDING —
    and even an APPROVED escalation only *authorizes* action; Argus never
    executes a freeze/block itself (no real side effects)."""
    case.approver = approver
    case.status = "APPROVED_FOR_ACTION" if approved else "DISMISSED_BY_HUMAN"
    return case
