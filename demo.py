"""Demo — trace one alert end-to-end for the video / notebook.

    python demo.py            # picks a fraud alert from the eval set
    python demo.py 6102387    # a specific txn_id

Prints the readable audit trail (every agent, tool call, decision, critic
verdict), the final case file, then simulates the human approval gate.
"""

from __future__ import annotations

import asyncio
import sys

import pandas as pd

import config
from agents import orchestrator
from agents.case_assembler import approve_case


def _pick_default_txn() -> int:
    eval_set = pd.read_csv(config.EVAL_SET_PATH)
    fraud = eval_set[eval_set["isFraud"] == 1]
    return int((fraud if not fraud.empty else eval_set).iloc[0]["txn_id"])


async def main(txn_id: int) -> None:
    print(f"\n>>> ARGUS — triaging alert for transaction {txn_id}\n")
    case, audit = await orchestrator.triage_alert(txn_id)

    print(audit.render())

    print("\n" + "=" * 60)
    print("CASE FILE")
    print("=" * 60)
    print(f"txn_id:      {case.txn_id}")
    print(f"disposition: {case.disposition}  (confidence {case.confidence})")
    print(f"status:      {case.status}")
    print(f"summary:     {case.summary}")
    if case.matched_patterns:
        print(f"patterns:    {case.matched_patterns}")
    print(f"critic:      approved={case.critic_verdict.approved} "
          f"unsupported={case.critic_verdict.unsupported_claims}")
    print(f"audit trail: {case.audit_trail_path}")

    # --- Human-in-the-loop gate (simulated) --------------------------------
    print("\n" + "=" * 60)
    print("HUMAN APPROVAL GATE")
    print("=" * 60)
    print("Argus never freezes/blocks on its own. A human must approve.")
    decided = approve_case(case, approver="analyst@bank", approved=True)
    print(f"-> analyst approved. status is now: {decided.status}")
    print("   (in production this would AUTHORIZE — not execute — a block/freeze)")


if __name__ == "__main__":
    txn_id = int(sys.argv[1]) if len(sys.argv) > 1 else _pick_default_txn()
    asyncio.run(main(txn_id))
