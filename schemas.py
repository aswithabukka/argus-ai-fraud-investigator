"""Pydantic schemas — the typed contracts every agent input/output must satisfy.

Structured I/O is a guardrail in its own right: an agent can't return prose where
a decision is expected, and the LLM agents (Analyzer, Critic) are pinned to these
schemas via ADK's `output_schema`, so Gemini must emit conforming JSON.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ---- input ----------------------------------------------------------------
class Alert(BaseModel):
    """A single fraud alert to investigate — just a pointer to the transaction."""
    txn_id: int


# ---- evidence (built deterministically from tool outputs) -----------------
class EvidenceBundle(BaseModel):
    """Canonical, exact evidence for one case. Numbers come straight from the
    data tools, never paraphrased by an LLM — this is the anti-hallucination
    source of truth the Critic checks reasoning against."""
    txn_id: int
    transaction: dict
    origin_baseline: dict
    origin_history: dict
    counterparty_risk: dict
    velocity: dict
    known_patterns: list[str] = Field(default_factory=list)


# ---- analyzer output ------------------------------------------------------
class RiskSignal(BaseModel):
    name: str
    severity: str = Field(description="one of: low, medium, high")
    detail: str
    evidence_ref: str = Field(
        description="which evidence field supports this signal, e.g. 'velocity.txn_count'"
    )


class RiskAssessment(BaseModel):
    risk_score: float = Field(ge=0.0, le=1.0, description="0=benign, 1=near-certain fraud")
    signals: list[RiskSignal]
    rationale: str


# ---- policy output (deterministic rules engine) ---------------------------
class PolicyFlag(BaseModel):
    rule: str
    triggered: bool
    severity: str
    detail: str


class PolicyResult(BaseModel):
    flags: list[PolicyFlag]
    suggested_disposition: str = Field(description="ESCALATE or CLEAR")
    reason: str


# ---- critic output --------------------------------------------------------
class CriticVerdict(BaseModel):
    approved: bool = Field(description="true if the reasoning is fully supported by evidence")
    unsupported_claims: list[str] = Field(
        default_factory=list,
        description="specific claims not backed by the evidence bundle",
    )
    issues: list[str] = Field(default_factory=list)
    revision_request: Optional[str] = Field(
        default=None, description="if not approved, a concrete instruction for the Analyzer"
    )


# ---- final case file ------------------------------------------------------
class CaseFile(BaseModel):
    txn_id: int
    disposition: str = Field(description="ESCALATE or CLEAR")
    confidence: float
    summary: str
    evidence: EvidenceBundle
    risk_assessment: RiskAssessment
    policy_result: PolicyResult
    critic_verdict: CriticVerdict
    matched_patterns: list[str] = Field(default_factory=list)
    status: str = Field(default="PENDING_HUMAN_APPROVAL")
    approver: Optional[str] = None
    audit_trail_path: Optional[str] = None
    routing_tier: Optional[str] = Field(
        default=None, description="standard (cheap model) or elevated (strong model)")
    routing_reason: Optional[str] = None
