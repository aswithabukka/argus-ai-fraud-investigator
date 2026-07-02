"""Session (case) memory — the working state for one active alert.

Passed between agents so each has the full context gathered so far: the
evidence bundle, the analyzer's assessment, policy flags, and any critic
feedback from a prior revision round.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from schemas import CriticVerdict, EvidenceBundle, PolicyResult, RiskAssessment


@dataclass
class SessionMemory:
    txn_id: int
    evidence: Optional[EvidenceBundle] = None
    assessment: Optional[RiskAssessment] = None
    policy: Optional[PolicyResult] = None
    critic: Optional[CriticVerdict] = None
    revision_count: int = 0
    critic_feedback_history: list[str] = field(default_factory=list)
