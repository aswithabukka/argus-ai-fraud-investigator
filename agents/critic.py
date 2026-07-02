"""Critic agent — the quality gate that fact-checks reasoning against evidence.

Runs on the stronger model (Gemini Pro) because catching another agent's
hallucinated figure or missed signal is harder than producing the assessment in
the first place. Returns a structured verdict; if it rejects, the orchestrator
sends the Analyzer back for exactly one revision using `revision_request`.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

import config
from agents.runtime import load_prompt, parse_json_output, run_agent
from schemas import CriticVerdict, EvidenceBundle, PolicyResult, RiskAssessment


def build_agent() -> LlmAgent:
    return LlmAgent(
        name="critic",
        model=config.CRITIC_MODEL,
        instruction=load_prompt("critic"),
        output_schema=CriticVerdict,
    )


async def critique(bundle: EvidenceBundle, assessment: RiskAssessment,
                   policy: PolicyResult, session_id: str) -> CriticVerdict:
    prompt = (
        f"EVIDENCE BUNDLE:\n{bundle.model_dump_json(indent=2)}\n\n"
        f"ANALYZER RISK ASSESSMENT:\n{assessment.model_dump_json(indent=2)}\n\n"
        f"POLICY RESULT:\n{policy.model_dump_json(indent=2)}\n\n"
        "Fact-check the reasoning against the evidence and return your verdict as JSON."
    )
    text, _ = await run_agent(build_agent(), prompt, session_id)
    return CriticVerdict(**parse_json_output(text))
