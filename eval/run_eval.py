"""Evaluation runner — the headline result.

Runs both the single-agent baseline and full Argus on the curated eval set,
scores them against the PaySim `isFraud` ground truth, adds an LLM-judged
faithfulness score for Argus, and prints/saves the before-vs-after metrics table.

    python -m eval.run_eval            # full eval set
    python -m eval.run_eval --limit 10 # quick subset

The `isFraud` label is used ONLY here for scoring; it is never exposed to the
agents (the data tools strip it).
"""

from __future__ import annotations

import argparse
import asyncio

import pandas as pd
from sklearn.metrics import precision_recall_fscore_support

import config
from agents import orchestrator
from eval import baseline, judge
from memory import pattern_store


def _labels(dispositions: list[str]) -> list[int]:
    """ESCALATE -> predicted fraud (1), CLEAR -> predicted legit (0)."""
    return [1 if d == config.ESCALATE else 0 for d in dispositions]


def _prf(y_true: list[int], y_pred: list[int]) -> dict:
    p, r, f, _ = precision_recall_fscore_support(
        y_true, y_pred, average="binary", zero_division=0
    )
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3)}


async def run(limit: int | None = None) -> pd.DataFrame:
    eval_set = pd.read_csv(config.EVAL_SET_PATH)
    if limit:
        eval_set = eval_set.head(limit)
    transactions = pd.read_parquet(config.TRANSACTIONS_PATH)
    pattern_store.reset()  # start every eval from the same seed memory

    y_true = eval_set["isFraud"].tolist()
    argus_pred, base_pred, faith_scores, pattern_hits = [], [], [], 0

    for i, row in eval_set.iterrows():
        txn_id = int(row["txn_id"])

        case, _ = await orchestrator.triage_alert(txn_id, transactions)
        argus_pred.append(case.disposition)
        if case.matched_patterns:
            pattern_hits += 1

        base = await baseline.classify(txn_id)
        base_pred.append(base.disposition)

        faith = await judge.score_case(case)
        faith_scores.append(faith.score)

        print(f"[{i+1}/{len(eval_set)}] txn {txn_id}: "
              f"truth={'FRAUD' if row['isFraud'] else 'legit'} | "
              f"argus={case.disposition} | baseline={base.disposition} | "
              f"faith={faith.score:.2f}")

    argus_metrics = _prf(y_true, _labels(argus_pred))
    base_metrics = _prf(y_true, _labels(base_pred))
    mean_faith = round(sum(faith_scores) / len(faith_scores), 3) if faith_scores else 0.0

    table = pd.DataFrame([
        {"system": "single-agent baseline", **base_metrics, "faithfulness": "n/a"},
        {"system": "Argus (full)", **argus_metrics, "faithfulness": mean_faith},
    ])
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(config.METRICS_PATH, index=False)

    print("\n" + "=" * 60)
    print("RESULTS — single-agent baseline vs. full Argus")
    print("=" * 60)
    print(table.to_string(index=False))
    print(f"\nCases matching a known fraud pattern (memory): {pattern_hits}/{len(eval_set)}")
    print(f"Metrics saved to {config.METRICS_PATH}")
    return table


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="evaluate only the first N alerts")
    args = ap.parse_args()
    asyncio.run(run(limit=args.limit))
