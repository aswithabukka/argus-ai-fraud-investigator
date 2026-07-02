"""Retriever agent — gathers evidence via the MCP data tools.

Design note (interview-relevant): the Retriever is an ADK LlmAgent that calls the
data tools over MCP, so tool use is genuinely agent-driven. But the canonical
EvidenceBundle is assembled deterministically from direct tool outputs, so the
figures downstream agents reason over are EXACT — never an LLM paraphrase. The
agent decides *what to investigate*; the code guarantees *accurate numbers*.
This decouples correctness from LLM reliability and kills a whole class of
hallucinated-evidence bugs at the source.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

import config
from agents.runtime import load_prompt, make_mcp_toolset, run_agent
from memory import pattern_store
from schemas import EvidenceBundle
from tools import data_tools


def build_agent() -> tuple[LlmAgent, object]:
    """Returns (agent, toolset). Caller must close the toolset when done."""
    toolset = make_mcp_toolset()
    agent = LlmAgent(
        name="retriever",
        model=config.WORKHORSE_MODEL,
        instruction=load_prompt("retriever"),
        tools=[toolset],
    )
    return agent, toolset


def _case_features(txn: dict, counterparty: dict) -> dict:
    """Compact, matchable descriptor of the case for the pattern store."""
    drained = txn.get("oldbalanceOrg", 0) > 0 and txn.get("newbalanceOrig", 0) == 0
    return {
        "type": txn.get("type"),
        "balance_drained": bool(drained),
        "counterparty_zero_balance": counterparty.get("zero_balance_rate", 0) >= 0.5,
    }


def build_evidence_bundle(txn_id: int, masker) -> tuple[EvidenceBundle, dict]:
    """Deterministically assemble the exact, PII-masked evidence bundle.

    Returns (bundle, raw_features). `raw_features` is the UNMASKED feature dict
    used for pattern matching and policy checks.
    """
    txn = data_tools.get_transaction(txn_id)
    origin, dest = txn["nameOrig"], txn["nameDest"]

    baseline = data_tools.get_customer_baseline(origin)
    history = data_tools.get_customer_history(origin, n=10)
    counterparty = data_tools.get_counterparty_risk(dest)
    velocity = data_tools.compute_velocity_signals(origin, as_of_step=txn["step"])

    features = _case_features(txn, counterparty)
    known = pattern_store.match_patterns(features)

    bundle = EvidenceBundle(
        txn_id=txn_id,
        transaction=masker.masked_copy(txn),
        origin_baseline=masker.masked_copy(baseline),
        origin_history=masker.masked_copy(history),
        counterparty_risk=masker.masked_copy(counterparty),
        velocity=masker.masked_copy(velocity),
        known_patterns=known,
    )
    return bundle, features


async def retrieve(txn_id: int, masker, session_id: str) -> tuple[EvidenceBundle, dict, str, list[dict]]:
    """Run the Retriever agent (agentic MCP tool use) and build the canonical
    bundle. Returns (bundle, features, agent_notes, tool_calls)."""
    txn = data_tools.get_transaction(txn_id)
    masked_txn = masker.masked_copy(txn)
    prompt = (
        f"Investigate transaction {txn_id}. Alerted transaction:\n"
        f"  type={masked_txn['type']}, amount={masked_txn['amount']}, "
        f"origin={masked_txn['nameOrig']}, dest={masked_txn['nameDest']}, "
        f"step={masked_txn['step']}\n"
        "Gather the evidence by calling the tools."
    )

    notes, tool_calls = "", []
    agent, toolset = build_agent()
    try:
        notes, tool_calls = await run_agent(agent, prompt, session_id)
    except Exception as e:  # resilience: never let the LLM step break retrieval
        notes = f"(retriever agent unavailable, used deterministic retrieval: {e})"
    finally:
        try:
            await toolset.close()
        except Exception:
            pass

    bundle, features = build_evidence_bundle(txn_id, masker)
    return bundle, features, notes, tool_calls
