"""Analyzer agent — reasons over the evidence bundle to produce a risk assessment.

An ADK LlmAgent pinned to the RiskAssessment schema, so Gemini must return a
score + evidence-cited signals as structured JSON. No tools: the evidence is
already gathered, and keeping the reasoning step tool-free means it can only work
from the bundle it's given (harder to hallucinate new "facts").
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

import config
from agents.runtime import load_prompt, parse_json_output, run_agent
from schemas import EvidenceBundle, RiskAssessment


def build_agent(model: str | None = None) -> LlmAgent:
    return LlmAgent(
        name="analyzer",
        model=model or config.WORKHORSE_MODEL,
        instruction=load_prompt("analyzer"),
        output_schema=RiskAssessment,
    )


async def analyze(bundle: EvidenceBundle, session_id: str,
                  critic_feedback: str | None = None,
                  model: str | None = None) -> RiskAssessment:
    prompt = f"EVIDENCE BUNDLE:\n{bundle.model_dump_json(indent=2)}\n"
    if critic_feedback:
        prompt += (
            f"\nCRITIC FEEDBACK from the previous round — address this specifically:\n"
            f"{critic_feedback}\n"
        )
    prompt += "\nReturn your risk assessment as JSON."

    text, _ = await run_agent(build_agent(model), prompt, session_id)
    return RiskAssessment(**parse_json_output(text))
