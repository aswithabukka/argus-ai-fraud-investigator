"""Orchestrator — the coordinating agent (explicit custom control flow).

Flow for one alert:
    validate → retrieve (MCP tools) → analyze → policy → critic
             → [one revision if critic rejects] → assemble case → human gate

The orchestration is plain, readable Python on purpose (interview-explainability
is a first-class goal). It owns session memory and the per-case audit trail, and
consults / updates the long-term pattern store.
"""

from __future__ import annotations

import pandas as pd

import config
from agents import analyzer, case_assembler, critic, policy, retriever
from guardrails.pii import PIIMasker
from guardrails.validation import enforce_evidence_citations, validate_alert
from memory.session import SessionMemory
from observability.audit import AuditTrail
from schemas import CaseFile
from tools import data_tools

MAX_REVISIONS = 1


async def triage_alert(txn_id: int,
                       transactions: pd.DataFrame | None = None) -> tuple[CaseFile, AuditTrail]:
    """Run one alert through the full Argus pipeline.

    Returns (case_file, audit_trail). The case file is PENDING_HUMAN_APPROVAL;
    call agents.case_assembler.approve_case to pass the human gate.
    """
    if transactions is None:
        transactions = pd.read_parquet(config.TRANSACTIONS_PATH)

    # --- Guardrail: validate input before any model call --------------------
    alert = validate_alert({"txn_id": txn_id}, transactions)
    memory = SessionMemory(txn_id=alert.txn_id)
    audit = AuditTrail(alert.txn_id)
    masker = PIIMasker()
    sid = f"case-{alert.txn_id}"
    audit.log("orchestrator", "alert validated", {"txn_id": alert.txn_id})

    # --- Retriever: agentic MCP tool use + deterministic evidence bundle ----
    bundle, features, notes, tool_calls = await retriever.retrieve(alert.txn_id, masker, sid)
    memory.evidence = bundle
    audit.log("retriever", "evidence gathered", notes, tool_calls=tool_calls)
    if bundle.known_patterns:
        audit.log("memory", "matched known fraud pattern(s)", bundle.known_patterns)

    # --- Analyzer: risk assessment (with Critic revision loop) --------------
    txn = data_tools.get_transaction(alert.txn_id)  # unmasked, for policy
    critic_feedback = None
    while True:
        assessment = await analyzer.analyze(bundle, sid, critic_feedback=critic_feedback)
        memory.assessment = assessment
        audit.log("analyzer", "risk assessed",
                  {"risk_score": assessment.risk_score,
                   "signals": [s.name for s in assessment.signals]})

        # Guardrail: every signal must cite evidence.
        violations = enforce_evidence_citations(assessment)
        if violations and memory.revision_count < MAX_REVISIONS:
            critic_feedback = "Fix these uncited claims: " + "; ".join(violations)
            memory.revision_count += 1
            audit.log("guardrail", "rejected uncited signals; requesting revision", violations)
            continue

        # --- Policy: deterministic rules engine -----------------------------
        pol = policy.evaluate(txn, bundle.velocity, bundle.counterparty_risk)
        memory.policy = pol
        audit.log("policy", "rules evaluated",
                  {"disposition": pol.suggested_disposition,
                   "fired": [f.rule for f in pol.flags if f.triggered]})

        # --- Critic: fact-check reasoning against evidence ------------------
        verdict = await critic.critique(bundle, assessment, pol, sid)
        memory.critic = verdict
        audit.log("critic", "verdict",
                  {"approved": verdict.approved,
                   "unsupported_claims": verdict.unsupported_claims,
                   "issues": verdict.issues})

        if verdict.approved or memory.revision_count >= MAX_REVISIONS:
            break
        critic_feedback = verdict.revision_request or "; ".join(verdict.issues)
        memory.critic_feedback_history.append(critic_feedback)
        memory.revision_count += 1
        audit.log("orchestrator", "critic requested revision", critic_feedback)

    # --- Assemble case + human gate ----------------------------------------
    audit_path = str(audit.save())
    case = case_assembler.assemble(bundle, assessment, memory.policy, memory.critic,
                                   masker, audit_path=audit_path)
    audit.log("case_assembler", "case assembled",
              {"disposition": case.disposition, "confidence": case.confidence,
               "status": case.status})
    audit.save()

    # Persist the full case file (evidence, cited signals, critic verdict) so the
    # analyst UI can render a complete report without re-running anything.
    config.CASES_DIR.mkdir(parents=True, exist_ok=True)
    (config.CASES_DIR / f"case_{alert.txn_id}.json").write_text(case.model_dump_json(indent=2))
    return case, audit
