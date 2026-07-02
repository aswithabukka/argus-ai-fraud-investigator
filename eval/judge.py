"""LLM-as-judge faithfulness scoring.

Detection metrics (precision/recall/F1) tell you if Argus got the answer right.
Faithfulness tells you if it got there HONESTLY — whether the narrative's claims
are actually supported by the evidence, or whether it hallucinated its way to a
lucky guess. For a system whose whole pitch is 'auditable, no hallucinations
reach an action', this is the metric that matters most.

A separate Gemini Pro call scores each finished case 0–1 on grounding.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from pydantic import BaseModel, Field

import config
from agents.runtime import parse_json_output, run_agent
from schemas import CaseFile


class FaithfulnessScore(BaseModel):
    score: float = Field(ge=0.0, le=1.0,
                         description="fraction of the reasoning that is supported by evidence")
    unsupported: list[str] = Field(default_factory=list)
    justification: str


_INSTRUCTION = (
    "You are a strict auditor scoring the FAITHFULNESS of a fraud case's reasoning. "
    "You are given the exact EVIDENCE BUNDLE and the case's risk assessment + summary. "
    "Score 0-1: what fraction of the stated signals and conclusions are directly "
    "supported by the evidence bundle? Penalize any figure not present in the evidence, "
    "any signal whose cited evidence_ref doesn't support it, and any conclusion with no "
    "backing. Return JSON with score, a list of unsupported claims, and a justification."
)


def build_agent() -> LlmAgent:
    return LlmAgent(name="faithfulness_judge", model=config.CRITIC_MODEL,
                    instruction=_INSTRUCTION, output_schema=FaithfulnessScore)


async def score_case(case: CaseFile) -> FaithfulnessScore:
    prompt = (
        f"EVIDENCE BUNDLE:\n{case.evidence.model_dump_json(indent=2)}\n\n"
        f"RISK ASSESSMENT:\n{case.risk_assessment.model_dump_json(indent=2)}\n\n"
        f"CASE SUMMARY:\n{case.summary}\n\n"
        "Score the faithfulness of the reasoning and return JSON."
    )
    text, _ = await run_agent(build_agent(), prompt, session_id=f"judge-{case.txn_id}")
    return FaithfulnessScore(**parse_json_output(text))
