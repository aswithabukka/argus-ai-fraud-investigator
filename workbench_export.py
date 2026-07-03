"""Export real Argus artifacts into the workbench UI's case schema.

The analyst workbench (workbench/index.html — ported pixel-for-pixel from the
design handoff in docs/design_handoff_argus_workbench/) consumes cases in the
prototype's shape: alert{}, sender[[k,v]], counter[[k,v]], velocity[[k,v]],
signals[[name,sev]], policy[[rule,fired,check,values]], criticPasses[],
reasoning[[k,v]], flow{}, typical, history[]. This module builds that from the
audit trails, saved case files, and the deterministic data tools — no LLM calls.

Building evidence for ~80 cases takes a couple of minutes over the 6.3M-row
dataset, so results are cached at results/workbench_cases.json; human decisions
are merged fresh from the audit files on every read (they change at runtime).
"""

from __future__ import annotations

import json

import pandas as pd

import config
from agents import policy as policy_engine
from agents.case_assembler import RISK_ESCALATE_THRESHOLD
from tools import data_tools

CACHE = config.RESULTS_DIR / "workbench_cases.json"

RULE_CHECKS = {
    "large_transfer": "Above the large-transaction threshold?",
    "exact_balance_drain": "Amount equals balance to the cent?",
    "near_balance_drain": "Empties most of the balance?",
    "velocity_burst": "Unusually many outgoing txns?",
    "mule_counterparty": "Receiver looks like a mule?",
}

SEV = {"high": "crit", "medium": "warn", "low": "ok"}


def _money(n) -> str:
    return f"${float(n):,.2f}"


def _truth_map() -> dict[int, int]:
    out = {}
    ev = pd.read_csv(config.EVAL_SET_PATH)
    out.update({int(r.txn_id): int(r.isFraud) for _, r in ev.iterrows()})
    p = config.RESULTS_DIR / "eval_progress.csv"
    if p.exists():
        d = pd.read_csv(p)
        out.update({int(r.txn_id): int(r.is_fraud) for _, r in d.iterrows()})
    return out


def _audit_step(audit: dict, agent: str):
    return next((s["detail"] for s in audit["steps"]
                 if s["agent"] == agent and isinstance(s["detail"], dict)), {})


def build_case(txn_id: int, truth: int | None) -> dict:
    audit = json.loads((config.AUDIT_DIR / f"case_{txn_id}.json").read_text())
    case_f = config.CASES_DIR / f"case_{txn_id}.json"
    case = json.loads(case_f.read_text()) if case_f.exists() else {}

    txn = data_tools.get_transaction(txn_id)
    base = data_tools.get_customer_baseline(txn["nameOrig"])
    hist = data_tools.get_customer_history(txn["nameOrig"], n=16)
    cp = data_tools.get_counterparty_risk(txn["nameDest"])
    vel = data_tools.compute_velocity_signals(txn["nameOrig"], as_of_step=txn["step"])
    pol = policy_engine.evaluate(txn, vel, cp)

    analyzer = _audit_step(audit, "analyzer")
    final = _audit_step(audit, "case_assembler")
    risk = float(case.get("risk_assessment", {}).get("risk_score",
                 analyzer.get("risk_score", 0.5)))
    conf = float(case.get("confidence", final.get("confidence", 0.5)))
    rec = case.get("disposition") or final.get("disposition", "CLEAR")

    # --- signals -------------------------------------------------------------
    if case.get("risk_assessment", {}).get("signals"):
        signals = [[s["name"], SEV.get(s["severity"], "warn")]
                   for s in case["risk_assessment"]["signals"]]
    else:
        signals = [[n, "warn"] for n in analyzer.get("signals", [])] or [["No signals", "ok"]]

    # --- policy rows -----------------------------------------------------------
    policy_rows = [[f.rule, bool(f.triggered), RULE_CHECKS.get(f.rule, ""),
                    f.detail.replace("$", "")] for f in pol.flags]

    # --- critic passes ---------------------------------------------------------
    passes = []
    for s in audit["steps"]:
        if s["action"] in ("critic requested revision",
                           "rejected uncited signals; requesting revision"):
            passes.append({"flag": True,
                           "text": f"The Critic rejected the draft: {str(s['detail'])[:320]}"})
    cv = case.get("critic_verdict") or _audit_step(audit, "critic")
    if cv.get("approved"):
        passes.append({"flag": False,
                       "text": "Every remaining claim checks out against the evidence "
                               "bundle — no hallucinated figures, no uncited conclusions. "
                               "Approved."})
    elif cv:
        why = "; ".join(map(str, cv.get("unsupported_claims") or cv.get("issues") or []))
        passes.append({"flag": True, "text": f"Approval withheld: {why[:280]}"})

    # --- flow ------------------------------------------------------------------
    zbr = cp.get("zero_balance_rate") or 0
    fan = int(cp.get("distinct_senders") or 0)
    kind = ("merchant" if cp.get("is_merchant")
            else "mule" if zbr >= 0.5 and fan >= 2 else "internal")

    # --- reasoning + routing -----------------------------------------------------
    model_line = (f"risk {risk:.2f} vs {RISK_ESCALATE_THRESHOLD:.2f} → "
                  + ("confident fraud" if risk >= RISK_ESCALATE_THRESHOLD else
                     "below the escalation bar"))
    fired_high = any(f.triggered and f.severity == "high" for f in pol.flags)
    fusion = ("both confident → ESCALATE" if risk >= RISK_ESCALATE_THRESHOLD and fired_high
              else f"fusion of model + rules → {rec}")
    reasoning = [["Model", model_line],
                 ["Policy", f"{pol.suggested_disposition} — {pol.reason}"],
                 ["Fusion", fusion]]
    if case.get("routing_tier") == "elevated":
        reasoning.append(["Router", f"elevated to {config.STRONG_MODEL} — "
                                    f"{case.get('routing_reason', '')}"])

    # --- baseline history ---------------------------------------------------------
    priors = [float(t["amount"]) for t in hist.get("transactions", [])
              if t.get("txn_id") != txn_id][:15]
    typical = float(base.get("median_amount") or base.get("mean_amount") or 0)

    first = base.get("first_step")
    n_recv = cp.get("n_received") or 0
    avg_in = (cp.get("total_received") or 0) / n_recv if n_recv else 0

    return {
        "id": str(txn_id),
        "truth": ("fraud" if truth == 1 else "legit" if truth == 0 else "unknown"),
        "rec": rec, "risk": round(risk, 2), "conf": round(conf, 2),
        "alert": {"account": txn["nameOrig"], "type": txn["type"],
                  "amount": float(txn["amount"]), "dest": txn["nameDest"],
                  "hour": int(txn["step"]), "before": float(txn["oldbalanceOrg"]),
                  "after": float(txn["newbalanceOrig"])},
        "sender": [["typical amount", _money(typical) if typical else "no history"],
                   ["largest ever sent", _money(base.get("max_amount") or 0)],
                   ["transactions seen", str(base.get("n_sent", 0))],
                   ["first seen", f"hour {first}" if first is not None else "—"]],
        "counter": [["merchant", "yes" if cp.get("is_merchant") else "no"],
                    ["distinct senders in", str(fan)],
                    ["zero-bal rate", f"{zbr:.2f}"],
                    ["avg incoming", _money(avg_in)]],
        "velocity": [["out txns / window", str(vel.get("txn_count", 0))],
                     ["moved in window", _money(vel.get("total_amount") or 0)],
                     ["window", f"{vel.get('window_steps', '?')}h"],
                     ["as of hour", str(vel.get("as_of_step", "?"))]],
        "signals": signals,
        "policy": policy_rows,
        "policyVerdict": pol.suggested_disposition,
        "policyNote": pol.reason,
        "critic": {"ok": bool(cv.get("approved")), "text": "Approved."},
        "criticPasses": passes,
        "reasoning": reasoning,
        "typical": typical if typical else float(txn["amount"]),
        "noHistory": not priors,
        "flow": {"destKind": kind, "fanIn": fan, "zeroBal": f"{zbr:.2f}",
                 "isCashOut": txn["type"] == "CASH_OUT"},
        "history": priors,
    }


def build_all(force: bool = False) -> list[dict]:
    if CACHE.exists() and not force:
        return json.loads(CACHE.read_text())
    truth = _truth_map()
    cases = []
    for f in sorted(config.AUDIT_DIR.glob("case_*.json")):
        txn_id = int(f.stem.split("_")[1])
        try:
            cases.append(build_case(txn_id, truth.get(txn_id)))
        except Exception as e:  # skip corrupt/partial cases rather than dying
            print(f"skip case {txn_id}: {e}")
    # escalations first, highest risk on top — the analyst's natural queue order
    cases.sort(key=lambda c: (c["rec"] != "ESCALATE", -c["risk"]))
    CACHE.write_text(json.dumps(cases))
    return cases


def refresh_case(txn_id: int) -> list[dict]:
    """Rebuild one case (after a live triage) and update the cache."""
    cases = build_all()
    truth = _truth_map()
    fresh = build_case(txn_id, truth.get(txn_id))
    cases = [c for c in cases if c["id"] != str(txn_id)] + [fresh]
    cases.sort(key=lambda c: (c["rec"] != "ESCALATE", -c["risk"]))
    CACHE.write_text(json.dumps(cases))
    return cases


def human_log(txn_id: int) -> list[dict]:
    """Fresh read of the human decisions from the audit file."""
    f = config.AUDIT_DIR / f"case_{txn_id}.json"
    if not f.exists():
        return []
    audit = json.loads(f.read_text())
    return [{"ts": s["detail"].get("ts", ""), "action":
             ("approved" if "APPROV" in s["action"] else "dismissed"),
             "rationale": s["detail"].get("rationale", "")}
            for s in audit["steps"] if s.get("agent") == "human_gate"]


def stats() -> dict:
    p = config.RESULTS_DIR / "eval_progress.csv"
    out = {"nEval": 0, "fraudsCaught": 0, "totalFraud": 0, "recallPct": 0,
           "faith": 0.0, "h2hWon": 0, "h2hTotal": 0,
           "baseline": {"p": 0, "r": 0, "f1": 0}, "argus": {"p": 0, "r": 0, "f1": 0}}
    if p.exists():
        from sklearn.metrics import precision_recall_fscore_support
        d = pd.read_csv(p)
        y = d["is_fraud"].astype(int)
        for name, col in [("baseline", "baseline"), ("argus", "argus")]:
            pred = [1 if x == "ESCALATE" else 0 for x in d[col]]
            pr, rc, f1, _ = precision_recall_fscore_support(
                y, pred, average="binary", zero_division=0)
            out[name] = {"p": round(pr, 2), "r": round(rc, 2), "f1": round(f1, 2)}
        out["nEval"] = len(d)
        out["totalFraud"] = int(y.sum())
        out["fraudsCaught"] = int(sum((d["argus"] == "ESCALATE") & (y == 1)))
        out["recallPct"] = round(100 * out["argus"]["r"])
        out["faith"] = round(float(d["faith"].mean()), 2)
        dis = d[d["argus"] != d["baseline"]]
        out["h2hTotal"] = len(dis)
        out["h2hWon"] = int(sum((dis["argus"] == "ESCALATE").astype(int) == dis["is_fraud"]))
    out["casesOnDisk"] = len(list(config.AUDIT_DIR.glob("case_*.json")))
    out["queueDepth"] = max(0, 80 - out["nEval"])
    out["model"] = config.WORKHORSE_MODEL
    out["critic"] = config.CRITIC_MODEL
    out["strong"] = config.STRONG_MODEL
    return out
