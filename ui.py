"""Argus Mission Control — a simple Streamlit UI over the fraud-triage system.

    streamlit run ui.py

Four tabs:
  1. Dashboard    — is anything running? eval progress, metrics so far (free: reads disk)
  2. Case Files   — browse every investigated case + its full audit trail (free)
  3. Live Triage  — pick an alert, watch Argus investigate it (costs ~1-2 cents)
  4. Ask Argus    — ask questions about a case in plain English (costs <1 cent/question)
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import pandas as pd
import streamlit as st

import config

st.set_page_config(page_title="Argus — Fraud Triage", page_icon="🛡️", layout="wide")

AUDIT_DIR = config.AUDIT_DIR
PROGRESS = config.RESULTS_DIR / "eval_progress.csv"


# ---------- helpers ----------------------------------------------------------
def eval_running() -> bool:
    out = subprocess.run(["pgrep", "-f", "eval.run_eval"], capture_output=True, text=True)
    return bool(out.stdout.strip())


def load_progress() -> pd.DataFrame | None:
    return pd.read_csv(PROGRESS) if PROGRESS.exists() else None


def load_cases() -> dict[int, dict]:
    cases = {}
    for f in sorted(AUDIT_DIR.glob("case_*.json")):
        try:
            a = json.loads(f.read_text())
            cases[a["txn_id"]] = a
        except Exception:
            continue
    return cases


def metrics_from_progress(d: pd.DataFrame) -> pd.DataFrame:
    from sklearn.metrics import precision_recall_fscore_support
    y = d["is_fraud"].astype(int)
    rows = []
    for name, col in [("Argus (full)", "argus"), ("single-agent baseline", "baseline")]:
        pred = [1 if x == "ESCALATE" else 0 for x in d[col]]
        p, r, f, _ = precision_recall_fscore_support(y, pred, average="binary", zero_division=0)
        rows.append({"system": name, "precision": round(p, 3), "recall": round(r, 3),
                     "f1": round(f, 3),
                     "faithfulness": round(d["faith"].mean(), 3) if col == "argus" else None})
    return pd.DataFrame(rows)


def render_trail(a: dict) -> None:
    icons = {"orchestrator": "🎯", "retriever": "🔎", "analyzer": "🧠", "policy": "📏",
             "critic": "⚖️", "case_assembler": "📁", "memory": "💾", "guardrail": "🛡️"}
    for s in a["steps"]:
        icon = icons.get(s["agent"], "•")
        with st.expander(f"{icon} **{s['agent']}** — {s['action']}", expanded=False):
            if s.get("tool_calls"):
                st.caption("tool calls:")
                for tc in s["tool_calls"]:
                    st.code(f"{tc.get('name')}({json.dumps(tc.get('args', {}))})", language=None)
            if s.get("detail") is not None:
                st.write(s["detail"])


# ---------- sidebar: live status ---------------------------------------------
with st.sidebar:
    st.title("🛡️ Argus")
    st.caption("Multi-agent fraud triage — Kaggle AI Agents capstone")

    running = eval_running()
    st.metric("Evaluation process", "RUNNING 🟢" if running else "idle ⚪")
    d = load_progress()
    if d is not None:
        st.progress(min(len(d) / 80, 1.0), text=f"eval progress: {len(d)}/80 alerts")
    st.metric("Investigated cases on disk", len(list(AUDIT_DIR.glob("case_*.json"))))
    st.caption(f"models: {config.WORKHORSE_MODEL} / critic: {config.CRITIC_MODEL}")
    st.caption("Dashboard & Case Files are free (read from disk). "
               "Live Triage ≈ 1–2¢. Ask Argus <1¢ per question.")

tab_dash, tab_cases, tab_triage, tab_ask = st.tabs(
    ["📊 Dashboard", "📁 Case Files", "🚨 Live Triage", "💬 Ask Argus"])


# ---------- 1. dashboard ------------------------------------------------------
with tab_dash:
    st.subheader("What is Argus?")
    st.markdown(
        "An alert comes in → the **Orchestrator** plans the investigation → the "
        "**Retriever** pulls transaction history & risk signals via **MCP tools** → the "
        "**Analyzer** scores the risk → the **Policy** engine applies auditable rules → the "
        "**Critic** fact-checks everything against the evidence → an analyst-ready **case "
        "file** goes to a **human approval gate**. No freeze/block ever executes on its own."
    )
    st.code("Alert → Orchestrator → Retriever → Analyzer → Policy → Critic → Case File → Human Gate",
            language=None)

    if d is not None and len(d):
        st.subheader(f"Evaluation so far — {len(d)}/80 alerts (ground-truth scored)")
        st.dataframe(metrics_from_progress(d), hide_index=True, use_container_width=True)
        c1, c2, c3 = st.columns(3)
        y = d["is_fraud"].astype(int)
        caught = sum((d["argus"] == "ESCALATE") & (y == 1))
        c1.metric("Frauds caught by Argus", f"{caught}/{y.sum()}")
        dis = d[d["argus"] != d["baseline"]]
        argus_right = sum((dis["argus"] == "ESCALATE").astype(int) == dis["is_fraud"])
        c2.metric("Argus vs baseline disagreements won", f"{argus_right}/{len(dis)}")
        c3.metric("Mean faithfulness (LLM judge)", f"{d['faith'].mean():.2f}")
    else:
        st.info("No evaluation results yet — run `python -m eval.run_eval` to populate this.")


# ---------- 2. case files -----------------------------------------------------
with tab_cases:
    cases = load_cases()
    if not cases:
        st.info("No investigated cases yet. Run Live Triage or the eval first.")
    else:
        prog = load_progress()
        truth = ({int(r.txn_id): int(r.is_fraud) for _, r in prog.iterrows()}
                 if prog is not None else {})
        ids = sorted(cases)
        sel = st.selectbox("Pick a case (txn_id)", ids,
                           format_func=lambda t: f"{t}"
                           + ("  ·  ground truth: FRAUD" if truth.get(t) == 1
                              else "  ·  ground truth: legit" if truth.get(t) == 0 else ""))
        a = cases[sel]
        final = next((s["detail"] for s in reversed(a["steps"])
                      if s["agent"] == "case_assembler"), {})
        c1, c2, c3 = st.columns(3)
        c1.metric("Disposition", final.get("disposition", "?"))
        c2.metric("Confidence", final.get("confidence", "?"))
        c3.metric("Status", final.get("status", "?"))
        st.subheader("Full audit trail")
        render_trail(a)


# ---------- 3. live triage ----------------------------------------------------
with tab_triage:
    st.markdown("Run the **full agent pipeline live** on an alert from the eval set. "
                "Takes ~30–60s and costs a cent or two.")
    ev = pd.read_csv(config.EVAL_SET_PATH)
    pick = st.selectbox(
        "Alert", ev.txn_id.astype(int),
        format_func=lambda t: (lambda r: f"txn {t} — {r.type} ${r.amount:,.0f}"
                               + ("  (known fraud)" if r.isFraud else "  (legit)"))(
                                   ev.set_index("txn_id").loc[t]))
    if st.button("🚨 Investigate this alert", type="primary"):
        with st.spinner("Argus agents investigating… (Retriever → Analyzer → Policy → Critic)"):
            from agents import orchestrator
            case, audit = asyncio.run(orchestrator.triage_alert(int(pick)))
        st.success(f"**{case.disposition}** (confidence {case.confidence}) — {case.status}")
        st.write(case.summary)
        if case.matched_patterns:
            st.warning("Matched known fraud pattern(s): " + "; ".join(case.matched_patterns))
        st.caption(f"Critic approved: {case.critic_verdict.approved} · "
                   f"unsupported claims: {case.critic_verdict.unsupported_claims or 'none'}")
        st.subheader("Audit trail")
        render_trail(json.loads(Path(case.audit_trail_path).read_text()))
        st.divider()
        st.markdown("**Human approval gate** — Argus only recommends. You decide:")
        c1, c2 = st.columns(2)
        if c1.button("✅ Approve escalation"):
            st.success("Case APPROVED_FOR_ACTION (simulated — no real side effects).")
        if c2.button("❌ Dismiss"):
            st.info("Case DISMISSED_BY_HUMAN.")


# ---------- 4. ask argus ------------------------------------------------------
with tab_ask:
    st.markdown("Ask questions about any investigated case — answers are **grounded in that "
                "case's evidence and audit trail** (one cheap Gemini call per question).")
    cases = load_cases()
    if not cases:
        st.info("No cases to ask about yet.")
    else:
        sel = st.selectbox("Case", sorted(cases), key="ask_case")
        q = st.text_input("Your question",
                          placeholder="e.g. Why was this escalated? What did the critic check?")
        if q and st.button("Ask", type="primary"):
            from google import genai
            client = genai.Client()
            context = json.dumps(cases[sel], default=str)[:60000]
            prompt = (
                "You are Argus, a fraud-investigation assistant. Answer the analyst's "
                "question using ONLY this case's audit trail JSON. Cite the specific "
                "evidence/steps that support your answer; if the trail doesn't contain "
                f"the answer, say so.\n\nCASE AUDIT TRAIL:\n{context}\n\n"
                f"ANALYST QUESTION: {q}"
            )
            with st.spinner("thinking…"):
                r = client.models.generate_content(model=config.WORKHORSE_MODEL,
                                                   contents=prompt)
            st.markdown(r.text)
