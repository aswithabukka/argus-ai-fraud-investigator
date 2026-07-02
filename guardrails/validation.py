"""Input and output validation guardrails."""

from __future__ import annotations

import pandas as pd

from schemas import Alert, RiskAssessment


class ValidationError(Exception):
    pass


def validate_alert(raw: dict, transactions: pd.DataFrame) -> Alert:
    """Reject malformed alerts before any model call or tool use."""
    try:
        alert = Alert(**raw)
    except Exception as e:  # pydantic ValidationError
        raise ValidationError(f"malformed alert: {e}") from e
    if alert.txn_id not in transactions["txn_id"].values:
        raise ValidationError(f"txn_id {alert.txn_id} not found in dataset")
    return alert


def enforce_evidence_citations(assessment: RiskAssessment) -> list[str]:
    """Every risk signal must cite an evidence field. Returns list of violations
    (empty = clean). The orchestrator treats a non-empty list as grounds to
    request a revision — a conclusion with no evidence pointer is not allowed."""
    violations = []
    for sig in assessment.signals:
        if not sig.evidence_ref or not sig.evidence_ref.strip():
            violations.append(f"signal '{sig.name}' cites no evidence")
    return violations
