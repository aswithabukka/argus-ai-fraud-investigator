"""Single-agent baseline — the 'before' in the before/after comparison.

One Gemini call, one prompt: "here is a transaction, is it fraud?" No specialist
agents, no evidence tools, no critic, no policy engine. This is what a naive
"just ask the LLM" fraud triage looks like, and it's the bar the full Argus
pipeline must clear on precision, recall, and faithfulness.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from pydantic import BaseModel, Field

import config
from agents.runtime import parse_json_output, run_agent
from guardrails.pii import PIIMasker
from tools import data_tools


class BaselineVerdict(BaseModel):
    disposition: str = Field(description="ESCALATE or CLEAR")
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


_INSTRUCTION = (
    "You are a fraud analyst. Given a single mobile-money transaction, decide "
    "whether it should be ESCALATE (likely fraud) or CLEAR (likely legitimate). "
    "You only see the transaction itself — no history, no tools. Return JSON with "
    "disposition, confidence (0-1), and a one-line rationale."
)


def build_agent() -> LlmAgent:
    return LlmAgent(name="baseline", model=config.WORKHORSE_MODEL,
                    instruction=_INSTRUCTION, output_schema=BaselineVerdict)


async def classify(txn_id: int) -> BaselineVerdict:
    masker = PIIMasker()
    txn = masker.masked_copy(data_tools.get_transaction(txn_id))
    prompt = f"Transaction:\n{txn}\n\nReturn your verdict as JSON."
    text, _ = await run_agent(build_agent(), prompt, session_id=f"baseline-{txn_id}")
    return BaselineVerdict(**parse_json_output(text))
