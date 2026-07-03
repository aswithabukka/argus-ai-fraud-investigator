"""Argus Mission Control — analyst-friendly UI over the fraud-triage system.

    streamlit run ui.py --server.port 8502

Design goal: a person who has NEVER seen this project should be able to open any
case and understand (1) what the alert was, (2) what evidence the agents
gathered, (3) what signals and rules fired, (4) how the reasoning was
fact-checked, and (5) how the final decision was reached. Raw JSON stays
available, but only inside an "for auditors" expander.
"""

from __future__ import annotations

import asyncio
import json
import subprocess

import pandas as pd
import streamlit as st

import config

st.set_page_config(page_title="Argus — Fraud Triage", page_icon="🛡️", layout="wide")


# ============================= plain-English lookups ==========================
TYPE_EXPLAIN = {
    "CASH_OUT": "cash withdrawal — money leaves the account for cash",
    "TRANSFER": "transfer — money sent to another account",
    "PAYMENT": "payment to a merchant",
    "CASH_IN": "cash deposit",
    "DEBIT": "debit to a bank account",
}

RULE_EXPLAIN = {
    "large_transfer": "Is the amount above the bank's large-transaction threshold?",
    "exact_balance_drain": "Does the amount equal the sender's balance TO THE CENT? "
                           "(Scripted account-takeover sweeps 'send everything'; real "
                           "customers withdraw round amounts and leave residue.)",
    "near_balance_drain": "Does it empty most (but not exactly all) of the balance? "
                          "Suspicious on its own but common for legitimate cash-outs.",
    "balance_drain": "Does the transaction empty most of the sender's balance?",
    "high_risk_type_drain": "Is it a drain via the high-risk types (TRANSFER/CASH_OUT)?",
    "velocity_burst": "Unusually many outgoing transactions in the recent window?",
    "mule_counterparty": "Does the receiver look like a 'mule' account — money passes "
                         "straight through (balance stays ~zero), many distinct senders, "
                         "not a merchant?",
}

SEV_ICON = {"high": "🔴", "medium": "🟠", "low": "🟡"}


def money(x) -> str:
    try:
        return f"${float(x):,.2f}"
    except (TypeError, ValueError):
        return str(x)


# ============================= cached data access =============================
@st.cache_data(show_spinner=False)
def load_eval_set() -> pd.DataFrame:
    return pd.read_csv(config.EVAL_SET_PATH)


def load_progress() -> pd.DataFrame | None:
    p = config.RESULTS_DIR / "eval_progress.csv"
    return pd.read_csv(p) if p.exists() else None


def load_audits() -> dict[int, dict]:
    out = {}
    for f in sorted(config.AUDIT_DIR.glob("case_*.json")):
        try:
            a = json.loads(f.read_text())
            out[a["txn_id"]] = a
        except Exception:
            continue
    return out


def load_case_file(txn_id: int) -> dict | None:
    f = config.CASES_DIR / f"case_{txn_id}.json"
    return json.loads(f.read_text()) if f.exists() else None


@st.cache_data(show_spinner="gathering evidence from the dataset…")
def case_context(txn_id: int) -> dict:
    """Recompute the deterministic evidence for display — free, no API calls."""
    from tools import data_tools
    txn = data_tools.get_transaction(txn_id)
    return {
        "txn": txn,
        "baseline": data_tools.get_customer_baseline(txn["nameOrig"]),
        "counterparty": data_tools.get_counterparty_risk(txn["nameDest"]),
        "velocity": data_tools.compute_velocity_signals(txn["nameOrig"], as_of_step=txn["step"]),
    }


def eval_running() -> bool:
    out = subprocess.run(["pgrep", "-f", "eval.run_eval"], capture_output=True, text=True)
    return bool(out.stdout.strip())


# ============================= the case report ================================
def render_case_report(txn_id: int, audit: dict | None, truth: int | None) -> None:
    """The star of the UI: one alert explained end-to-end for a newcomer."""
    ctx = case_context(txn_id)
    txn, base, cp, vel = ctx["txn"], ctx["baseline"], ctx["counterparty"], ctx["velocity"]
    case = load_case_file(txn_id)

    def audit_detail(agent: str) -> dict:
        if not audit:
            return {}
        return next((s["detail"] for s in audit["steps"]
                     if s["agent"] == agent and isinstance(s["detail"], dict)), {})

    final = audit_detail("case_assembler")
    analyzer = audit_detail("analyzer")
    critic = audit_detail("critic")

    # ---- verdict banner -----------------------------------------------------
    disp = (case or {}).get("disposition") or final.get("disposition", "?")
    conf = (case or {}).get("confidence") or final.get("confidence", "?")
    status = (case or {}).get("status") or final.get("status", "?")
    risk = (case or {}).get("risk_assessment", {}).get("risk_score", analyzer.get("risk_score"))

    if disp == "ESCALATE":
        st.error(f"### 🚨 Recommendation: **ESCALATE** — send to a fraud analyst  \n"
                 f"model risk score: **{risk}** · confidence: **{conf}** · status: `{status}`")
    else:
        st.success(f"### ✅ Recommendation: **CLEAR** — looks legitimate  \n"
                   f"model risk score: **{risk}** · confidence: **{conf}** · status: `{status}`")
    if truth is not None:
        ok = (disp == "ESCALATE") == bool(truth)
        st.caption(("ground truth: **actually FRAUD**" if truth else
                    "ground truth: **actually legitimate**")
                   + ("  →  Argus got it ✅ right" if ok else "  →  Argus got it ❌ wrong"))
    if case and case.get("summary"):
        st.markdown(f"> {case['summary']}".replace("$", "\\$"))

    # ---- 1. the alert ---------------------------------------------------------
    st.markdown("#### ① The alert")
    t = txn["type"]
    st.markdown(
        f"Account **{txn['nameOrig']}** initiated a **{t}** "
        f"({TYPE_EXPLAIN.get(t, t)}) of **{money(txn['amount'])}** to "
        f"**{txn['nameDest']}** at simulation hour {txn['step']}."
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Amount", money(txn["amount"]))
    c2.metric("Sender balance before", money(txn["oldbalanceOrg"]))
    c3.metric("Sender balance after", money(txn["newbalanceOrig"]),
              delta=f"-{money(txn['oldbalanceOrg'] - txn['newbalanceOrig'])}",
              delta_color="inverse")
    c4.metric("Type", t)
    if txn["oldbalanceOrg"] > 0 and txn["amount"] == txn["oldbalanceOrg"]:
        st.error("⚠️ **The amount equals the sender's balance to the exact cent — the "
                 "account was swept empty.** This is the classic signature of a scripted "
                 "account takeover; legitimate customers usually withdraw round amounts "
                 "and leave something behind.")

    # ---- 2. the evidence ------------------------------------------------------
    st.markdown("#### ② Evidence the Retriever gathered *(via MCP data tools)*")
    e1, e2, e3 = st.columns(3)
    with e1:
        st.markdown("**Sender's normal behavior**")
        typ = base.get("typical_amount") or base.get("mean_amount")
        st.write(f"- typical amount: **{money(typ)}**" if typ is not None else "- no history")
        if base.get("max_amount") is not None:
            st.write(f"- largest ever sent: **{money(base['max_amount'])}**")
        if base.get("n_sent") is not None:
            st.write(f"- transactions on record: **{base['n_sent']}**")
        try:
            ratio = float(txn["amount"]) / float(typ)
            if ratio > 1:
                st.write(f"- this alert is **{ratio:,.1f}×** their typical amount")
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    with e2:
        st.markdown("**Receiver (counterparty) profile**")
        st.write(f"- merchant account: **{'yes' if cp.get('is_merchant') else 'no'}**")
        st.write(f"- distinct senders into it: **{cp.get('distinct_senders', '?')}**")
        zbr = cp.get("zero_balance_rate")
        if zbr is not None:
            st.write(f"- money passes straight through **{zbr:.0%}** of the time "
                     "(high = 'mule'-like)")
    with e3:
        st.markdown("**Recent activity (velocity)**")
        st.write(f"- outgoing txns in last {vel.get('window_steps', '?')}h: "
                 f"**{vel.get('txn_count', '?')}**")
        if vel.get("total_amount") is not None:
            st.write(f"- total moved in window: **{money(vel['total_amount'])}**")

    # ---- 3. analyzer signals --------------------------------------------------
    st.markdown("#### ③ Risk signals the Analyzer found *(LLM reasoning over the evidence)*")
    signals = (case or {}).get("risk_assessment", {}).get("signals")
    if signals:
        for s in signals:
            st.markdown((f"{SEV_ICON.get(s['severity'], '⚪')} **{s['name']}** "
                         f"({s['severity']}) — {s['detail']}  \n"
                         f"&nbsp;&nbsp;&nbsp;↳ *evidence cited:* `{s['evidence_ref']}`")
                        .replace("$", "\\$"))
        if case.get("risk_assessment", {}).get("rationale"):
            st.caption("Analyzer's rationale: "
                       + case["risk_assessment"]["rationale"].replace("$", "\\$"))
    elif analyzer.get("signals"):
        st.write(", ".join(f"`{s}`" for s in analyzer["signals"]))
        st.caption("(full signal details are saved for newly-run cases)")
    else:
        st.caption("no signals recorded")

    # ---- 4. policy rules ------------------------------------------------------
    st.markdown("#### ④ Policy rules *(deterministic code — same input, same answer, "
                "auditable by a regulator)*")
    from agents import policy as policy_engine
    pol = policy_engine.evaluate(txn, vel, cp)
    rows = [{"rule": f.rule,
             "fired": "🔴 YES" if f.triggered else "— no",
             "what it checks": RULE_EXPLAIN.get(f.rule, ""),
             "values seen": f.detail} for f in pol.flags]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption(f"Policy engine verdict: **{pol.suggested_disposition}** — {pol.reason}")

    # ---- 5. critic ------------------------------------------------------------
    st.markdown("#### ⑤ The Critic's fact-check *(a second model verifies every claim "
                "against the evidence before anything is finalized)*")
    cv = (case or {}).get("critic_verdict") or critic
    if cv:
        if cv.get("approved"):
            st.success("✅ Approved — every claim in the risk assessment is supported by "
                       "the gathered evidence. No hallucinated numbers found.")
        else:
            st.warning("✋ The Critic pushed back and requested a revision.")
        if cv.get("unsupported_claims"):
            st.write("Unsupported claims flagged:", cv["unsupported_claims"])
        if cv.get("issues"):
            st.write("Issues raised:", cv["issues"])
    else:
        st.caption("no critic verdict recorded")

    # ---- 6. how the decision was made ------------------------------------------
    st.markdown("#### ⑥ How the final decision was made")
    st.markdown(
        f"Argus fuses two independent judgments — **escalate if either is confident**:\n"
        f"1. **Model judgment**: the Analyzer's risk score **{risk}** vs. the confidence "
        f"threshold **{__import__('agents.case_assembler', fromlist=['x']).RISK_ESCALATE_THRESHOLD}** "
        f"(scores above it mean the model genuinely believes it's fraud)\n"
        f"2. **Policy judgment**: **{pol.suggested_disposition}** — with a high-severity rule, "
        f"the model only needs to weakly agree to corroborate\n\n"
        f"**Result: {disp}.** The case was then marked `{status}` — **no freeze or block "
        f"happens unless a human approves it.**"
    )

    # ---- raw trail for auditors -------------------------------------------------
    if audit:
        with st.expander("🗃 Raw audit trail — every step in order (for auditors)"):
            icons = {"orchestrator": "🎯", "retriever": "🔎", "analyzer": "🧠",
                     "policy": "📏", "critic": "⚖️", "case_assembler": "📁",
                     "memory": "💾", "guardrail": "🛡️"}
            for s in audit["steps"]:
                st.markdown(f"**{s['seq']:02d}. {icons.get(s['agent'], '•')} "
                            f"{s['agent']}** — {s['action']}")
                for tc in s.get("tool_calls", []):
                    st.code(f"{tc.get('name')}({json.dumps(tc.get('args', {}))})",
                            language=None)
                if s.get("detail") is not None:
                    st.json(s["detail"], expanded=False)
            st.download_button("⬇️ download audit JSON",
                               json.dumps(audit, indent=2, default=str),
                               file_name=f"case_{txn_id}_audit.json")


# ============================= sidebar ========================================
with st.sidebar:
    st.title("🛡️ Argus")
    st.caption("Multi-agent fraud triage — Kaggle AI Agents capstone")
    running = eval_running()
    st.metric("Evaluation process", "RUNNING 🟢" if running else "idle ⚪")
    d = load_progress()
    if d is not None:
        st.progress(min(len(d) / 80, 1.0), text=f"benchmark progress: {len(d)}/80 alerts")
    st.metric("Investigated cases on disk", len(list(config.AUDIT_DIR.glob("case_*.json"))))
    st.caption(f"models: {config.WORKHORSE_MODEL} · critic: {config.CRITIC_MODEL}")
    st.divider()
    st.caption("💰 Dashboard & Case Files are **free** (read from disk). "
               "Live Triage ≈ 1–2¢. Ask Argus <1¢ per question.")

tab_dash, tab_cases, tab_triage, tab_ask = st.tabs(
    ["📊 Dashboard", "📁 Case Files", "🚨 Live Triage", "💬 Ask Argus"])


# ============================= 1. dashboard ===================================
with tab_dash:
    st.header("What is Argus?")
    st.markdown(
        "Banks generate thousands of fraud **alerts**; most are false alarms, but every "
        "one needs a human to investigate. **Argus does the investigation automatically** "
        "and hands the analyst a finished, fact-checked case file — the human only makes "
        "the final call."
    )
    st.code("Alert → Orchestrator → Retriever → Analyzer → Policy → Critic "
            "→ Case File → 👤 Human approves/dismisses", language=None)
    with st.expander("Meet the agents (what each one does)"):
        st.markdown(
            "| Agent | Job | Type |\n|---|---|---|\n"
            "| 🎯 Orchestrator | plans the investigation, coordinates everyone | code |\n"
            "| 🔎 Retriever | pulls transaction history & risk stats via **MCP tools** | LLM + tools |\n"
            "| 🧠 Analyzer | weighs the evidence, produces a 0–1 risk score with cited signals | LLM |\n"
            "| 📏 Policy | fixed, auditable fraud rules (thresholds, drain patterns) | code |\n"
            "| ⚖️ Critic | fact-checks every claim against the evidence — rejects hallucinations | LLM |\n"
            "| 📁 Case Assembler | fuses model + policy into the final recommendation | code |\n"
            "| 👤 Human gate | nothing freezes/blocks without an analyst's approval | human |"
        )

    d = load_progress()
    if d is not None and len(d):
        st.header(f"Benchmark results so far — {len(d)}/80 alerts")
        st.markdown("We replay historical alerts **where the true answer is known** and "
                    "compare Argus against a naive one-prompt baseline.")
        from sklearn.metrics import precision_recall_fscore_support
        y = d["is_fraud"].astype(int)
        rows = []
        for name, col in [("one-prompt baseline", "baseline"), ("Argus (full)", "argus")]:
            pred = [1 if x == "ESCALATE" else 0 for x in d[col]]
            p, r, f, _ = precision_recall_fscore_support(y, pred, average="binary",
                                                         zero_division=0)
            rows.append({"system": name, "precision": round(p, 2), "recall": round(r, 2),
                         "F1": round(f, 2)})
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        c1, c2, c3 = st.columns(3)
        caught = int(sum((d["argus"] == "ESCALATE") & (y == 1)))
        c1.metric("Frauds caught by Argus", f"{caught}/{int(y.sum())}",
                  help="Out of the alerts that were truly fraud, how many Argus escalated.")
        dis = d[d["argus"] != d["baseline"]]
        aright = int(sum((dis["argus"] == "ESCALATE").astype(int) == dis["is_fraud"]))
        c2.metric("Head-to-head disagreements won", f"{aright}/{len(dis)}",
                  help="Cases where Argus and the baseline disagreed — and which one "
                       "matched the ground truth.")
        c3.metric("Faithfulness (0–1)", f"{d['faith'].mean():.2f}",
                  help="An independent LLM judge scores whether each case's reasoning is "
                       "actually supported by its evidence. High = no made-up facts.")
        with st.expander("How to read these numbers (plain English)"):
            st.markdown(
                "- **Recall** — *of the real frauds, how many did we catch?* Missing fraud "
                "loses money directly, so this is the metric a fraud team protects first.\n"
                "- **Precision** — *of the alerts we escalated, how many were really fraud?* "
                "Low precision = analysts waste time on false alarms.\n"
                "- **F1** — the balance of the two.\n"
                "- **Faithfulness** — unique to LLM systems: is the *explanation* honest? "
                "A system can guess right for made-up reasons; the faithfulness judge and "
                "the Critic exist to prevent exactly that."
            )
    else:
        st.info("No benchmark results yet — run `python -m eval.run_eval`.")


# ============================= 2. case files ==================================
with tab_cases:
    audits = load_audits()
    if not audits:
        st.info("No investigated cases yet — run Live Triage or the benchmark first.")
    else:
        prog = load_progress()
        truth_map = ({int(r.txn_id): int(r.is_fraud) for _, r in prog.iterrows()}
                     if prog is not None else {})
        ids = sorted(audits)
        labels = {}
        for t in ids:
            g = truth_map.get(t)
            labels[t] = f"txn {t}" + ("  ·  truth: FRAUD" if g == 1
                                      else "  ·  truth: legit" if g == 0 else "")
        sel = st.selectbox("Pick a case to open its investigation report",
                           ids, format_func=lambda t: labels[t])
        st.divider()
        render_case_report(sel, audits[sel], truth_map.get(sel))


# ============================= 3. live triage =================================
with tab_triage:
    st.markdown("Run the **full agent pipeline live** on an alert (~30–60s, costs a "
                "cent or two). You'll get the same step-by-step report as Case Files, "
                "and **you** make the final call at the human gate.")
    ev = load_eval_set()
    meta = ev.set_index("txn_id")
    pick = int(st.selectbox(
        "Choose an alert from the queue", ev.txn_id.astype(int),
        format_func=lambda t: (lambda r: f"txn {t} — {r.type} {money(r.amount)}"
                               + ("  · known fraud" if r.isFraud else "  · legit"))(meta.loc[t])))
    if st.button("🚨 Investigate this alert", type="primary"):
        with st.spinner("Argus investigating… Retriever → Analyzer → Policy → Critic"):
            from agents import orchestrator
            case, audit = asyncio.run(orchestrator.triage_alert(pick))
        st.session_state["last_triaged"] = pick
    if (t := st.session_state.get("last_triaged")):
        audits = load_audits()
        prog = load_progress()
        truth_map = ({int(r.txn_id): int(r.is_fraud) for _, r in prog.iterrows()}
                     if prog is not None else {})
        truth_map.update({int(r.txn_id): int(r.isFraud) for _, r in ev.iterrows()})
        st.divider()
        render_case_report(t, audits.get(t), truth_map.get(t))
        st.divider()
        st.markdown("### 👤 Human approval gate — Argus only recommends. **You decide:**")
        c1, c2 = st.columns(2)
        if c1.button("✅ Approve escalation", use_container_width=True):
            st.success("Case **APPROVED_FOR_ACTION** — in production this would *authorize* "
                       "(never auto-execute) an account freeze. Simulated here.")
        if c2.button("❌ Dismiss as false alarm", use_container_width=True):
            st.info("Case **DISMISSED_BY_HUMAN** — recorded in the audit trail.")


# ============================= 4. ask argus ===================================
with tab_ask:
    st.markdown("Ask questions about any investigated case in plain English. Answers are "
                "**grounded only in that case's evidence and audit trail** — if the answer "
                "isn't in the record, Argus says so instead of guessing.")
    audits = load_audits()
    if not audits:
        st.info("No cases to ask about yet.")
    else:
        sel = st.selectbox("Case", sorted(audits), key="ask_case")
        st.caption("Try one of these:")
        cols = st.columns(3)
        suggestions = ["Why was this alert escalated (or cleared)?",
                       "What did the Critic verify before approving?",
                       "Explain this case to a non-technical manager in 3 sentences."]
        for col, s in zip(cols, suggestions):
            if col.button(s, use_container_width=True):
                st.session_state["ask_q"] = s
        q = st.text_input("Your question", value=st.session_state.get("ask_q", ""),
                          placeholder="e.g. What evidence pointed to a mule account?")
        if q and st.button("Ask Argus", type="primary"):
            from google import genai
            client = genai.Client()
            ctx = case_context(sel)
            payload = {"audit_trail": audits[sel], "case_file": load_case_file(sel),
                       "evidence": {k: v for k, v in ctx.items()}}
            prompt = (
                "You are Argus, a fraud-investigation assistant talking to a bank analyst. "
                "Answer the question using ONLY the case record below. Be concise and "
                "plain-English; cite the specific evidence or step that supports each "
                "point. If the record doesn't contain the answer, say so.\n\n"
                f"CASE RECORD:\n{json.dumps(payload, default=str)[:60000]}\n\n"
                f"QUESTION: {q}"
            )
            with st.spinner("checking the case record…"):
                r = client.models.generate_content(model=config.WORKHORSE_MODEL,
                                                   contents=prompt)
            # escape $ so Streamlit doesn't render dollar amounts as LaTeX math
            st.markdown((r.text or "").replace("$", "\\$"))
            st.caption("⚠️ grounded answer — sourced from this case's audit trail and "
                       "evidence only")
