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
        "history": data_tools.get_customer_history(txn["nameOrig"], n=16),
        "counterparty": data_tools.get_counterparty_risk(txn["nameDest"]),
        "velocity": data_tools.compute_velocity_signals(txn["nameOrig"], as_of_step=txn["step"]),
    }


def eval_running() -> bool:
    out = subprocess.run(["pgrep", "-f", "eval.run_eval"], capture_output=True, text=True)
    return bool(out.stdout.strip())


# ==================== signature components (design handoff) ==================
RISK_RED, AMBER, GREEN, BLUE = "#ff5245", "#f4b13c", "#37d68a", "#6ea2ff"


def risk_color(r) -> str:
    try:
        r = float(r)
    except (TypeError, ValueError):
        return AMBER
    return RISK_RED if r >= 0.7 else AMBER if r >= 0.4 else GREEN


def render_baseline_chart(ctx: dict, risk) -> None:
    """Signature A: the alert amount vs this account's own history — a picture,
    not a number. History bars + glowing alert bar + dashed 'typical' line."""
    txn, base = ctx["txn"], ctx["baseline"]
    alert_amt = float(txn["amount"])
    hist = [float(t["amount"]) for t in ctx.get("history", {}).get("transactions", [])
            if t.get("txn_id") != txn.get("txn_id")][:15]
    typical = base.get("median_amount") or base.get("mean_amount") or 0
    max_val = max([alert_amt, typical or 0] + hist) or 1
    color = risk_color(risk)

    bars = "".join(
        f'<div style="flex:1;min-width:3px;height:{max(3, round(a / max_val * 56))}px;'
        f'background:rgba(255,255,255,.13);border-radius:2px 2px 0 0"></div>'
        for a in hist)
    alert_bar = (f'<div style="flex:1;min-width:6px;height:{max(4, round(alert_amt / max_val * 56))}px;'
                 f'background:{color};border-radius:2px 2px 0 0;'
                 f'box-shadow:0 0 12px rgba(255,82,69,.55)"></div>')
    typ_line = ""
    if typical:
        typ_line = (f'<div style="position:absolute;left:0;right:0;'
                    f'bottom:{round(typical / max_val * 56)}px;'
                    f'border-top:1px dashed rgba(255,255,255,.26)"></div>')

    if typical and typical > 0:
        mult = alert_amt / typical
        mult_txt = f"{mult:,.0f}× typical" if mult >= 2 else f"{mult:,.1f}× typical"
        note = (f"This transaction is <b>{mult_txt}</b> for this account — "
                + ("a classic drain-signature spike." if mult >= 5 and risk and float(risk) >= 0.5
                   else "large, but judged against the full evidence below."))
    else:
        mult_txt = "no prior history"
        note = ("<b>No prior sending history</b> — this is the account's first recorded "
                "transaction, which is itself a risk factor (fraud accounts are often fresh).")

    st.markdown(
        f'<div style="background:#101319;border:1px solid rgba(255,255,255,.07);'
        f'border-radius:14px;padding:16px 18px;margin:4px 0 12px">'
        f'<div style="display:flex;justify-content:space-between;margin-bottom:10px">'
        f'<span style="color:#8a929e;font-size:12px">Amount vs this account\'s own history</span>'
        f'<span style="color:{color};font-weight:600;font-size:13px">{mult_txt}</span></div>'
        f'<div style="position:relative;height:64px;display:flex;align-items:flex-end;gap:3px">'
        f'{typ_line}{bars}{alert_bar}</div>'
        f'<div style="color:#aab2bf;font-size:12px;margin-top:10px">{note} '
        f'<span style="color:#59616e">(grey bars = prior transactions · dashed line = '
        f'typical amount · glowing bar = this alert)</span></div></div>',
        unsafe_allow_html=True)


def render_money_flow(ctx: dict) -> None:
    """Signature B: sender → amount → destination (mule/merchant/internal) →
    optional cash-out. Makes 'mule account' visible instead of a label."""
    txn, cp = ctx["txn"], ctx["counterparty"]
    zbr = cp.get("zero_balance_rate") or 0
    fan_in = cp.get("distinct_senders") or 0
    if cp.get("is_merchant"):
        kind, kcolor, badge = "Merchant", GREEN, "VERIFIED"
        note = "Established merchant account — normal destination for payments."
    elif zbr >= 0.5 and fan_in >= 2:
        kind, kcolor, badge = "Mule-like account", RISK_RED, "PASS-THRU"
        note = (f"{zbr:.0%} of inflow passes straight through and {fan_in} different "
                f"senders feed it — textbook mule profile.")
    else:
        kind, kcolor, badge = "Customer account", BLUE, "HOLDS BAL"
        note = (f"Receives from {fan_in} sender(s); balance is retained "
                f"({zbr:.0%} pass-through) — not mule-like.")
    dots = "".join(f'<span style="display:inline-block;width:5px;height:5px;'
                   f'border-radius:50%;background:{kcolor};margin-right:3px"></span>'
                   for _ in range(min(6, max(1, fan_in))))
    cashout = ""
    if txn["type"] == "CASH_OUT":
        cashout = (
            f'<div style="display:flex;align-items:center;color:{RISK_RED};font-size:11px;'
            f'padding:0 8px">cash&nbsp;▶</div>'
            f'<div style="flex:none;width:170px;background:rgba(255,82,69,.07);'
            f'border:1px solid {RISK_RED};border-radius:12px;padding:12px 14px">'
            f'<div style="color:{RISK_RED};font-weight:600;font-size:12px">Cash-out</div>'
            f'<div style="color:#aab2bf;font-size:11px;margin-top:4px">funds exit the '
            f'system — unrecoverable once withdrawn</div></div>')
    st.markdown(
        f'<div style="background:#101319;border:1px solid rgba(255,255,255,.07);'
        f'border-radius:14px;padding:16px;overflow-x:auto;margin:4px 0 12px">'
        f'<div style="display:flex;align-items:stretch;min-width:600px;gap:0">'
        f'<div style="flex:none;width:150px;background:#0c0e13;border:1px solid '
        f'rgba(255,255,255,.09);border-radius:12px;padding:12px 14px">'
        f'<div style="color:#8a929e;font-size:10px;letter-spacing:.8px">SENDER</div>'
        f'<div style="color:#eef1f6;font-family:monospace;font-size:12px;margin-top:4px">'
        f'{txn["nameOrig"]}</div>'
        f'<div style="color:#6b7381;font-size:11px;margin-top:4px">flagged account</div></div>'
        f'<div style="flex:1;display:flex;flex-direction:column;justify-content:center;'
        f'padding:0 10px;min-width:120px">'
        f'<div style="text-align:center;background:#14181f;border-radius:8px;color:#eef1f6;'
        f'font-family:monospace;font-size:12px;padding:4px 8px;margin-bottom:5px">'
        f'{money(txn["amount"])}</div>'
        f'<div style="height:2px;background:linear-gradient(90deg,rgba(255,255,255,.06),'
        f'{kcolor})"></div>'
        f'<div style="text-align:right;color:{kcolor};font-size:11px;margin-top:5px">'
        f'{txn["type"]}&nbsp;▶</div></div>'
        f'<div style="flex:none;width:184px;background:rgba(255,255,255,.02);'
        f'border:1px solid {kcolor};border-radius:12px;padding:12px 14px">'
        f'<div style="display:flex;justify-content:space-between">'
        f'<span style="color:{kcolor};font-weight:600;font-size:12px">{kind}</span>'
        f'<span style="color:{kcolor};font-size:9px;border:1px solid {kcolor};'
        f'border-radius:6px;padding:1px 5px">{badge}</span></div>'
        f'<div style="color:#eef1f6;font-family:monospace;font-size:12px;margin-top:4px">'
        f'{txn["nameDest"]}</div>'
        f'<div style="margin-top:6px">{dots}<span style="color:#8a929e;font-size:11px">'
        f'&nbsp;×{fan_in} senders in</span></div>'
        f'<div style="color:#aab2bf;font-size:11px;margin-top:6px">{note}</div></div>'
        f'{cashout}</div></div>',
        unsafe_allow_html=True)


def render_critic_loop(audit: dict | None, case: dict | None) -> None:
    """Signature C: the Critic's passes — show the catch, not just the consensus."""
    revisions = []
    approved = None
    if audit:
        for s in audit["steps"]:
            if s["action"] in ("critic requested revision",
                               "rejected uncited signals; requesting revision"):
                revisions.append(str(s["detail"]))
            if s["agent"] == "critic" and isinstance(s["detail"], dict):
                approved = s["detail"]
    cv = (case or {}).get("critic_verdict") or approved or {}

    def pass_box(n, flagged, body):
        color, bg, icon = ((AMBER, "rgba(244,177,60,.07)", "⚠") if flagged
                           else (GREEN, "rgba(55,214,138,.06)", "✓"))
        title = ("flagged — sent back for revision" if flagged else "approved")
        return (f'<div style="display:flex;gap:12px;background:{bg};border:1px solid {color};'
                f'border-radius:12px;padding:12px 14px;margin-bottom:8px">'
                f'<div style="flex:none;width:24px;height:24px;border:1.5px solid {color};'
                f'border-radius:7px;color:{color};text-align:center;line-height:22px">{icon}</div>'
                f'<div><div style="color:{color};font-weight:600;font-size:12.5px">'
                f'Pass {n} · {title}</div>'
                f'<div style="color:#aab2bf;font-size:12px;margin-top:3px">{body}</div>'
                f'</div></div>')

    html = ""
    n = 1
    for rev in revisions:
        html += pass_box(n, True, f"The Critic rejected the draft: <i>{rev[:400]}</i>")
        n += 1
    if cv.get("approved"):
        body = ("Every remaining claim checks out against the evidence bundle — no "
                "hallucinated figures, no uncited conclusions.")
        if cv.get("issues"):
            body += f" Notes: {'; '.join(map(str, cv['issues']))[:200]}"
        html += pass_box(n, False, body)
    elif cv:
        html += pass_box(n, True,
                         "Final verdict withheld approval: "
                         + "; ".join(map(str, cv.get("unsupported_claims") or
                                         cv.get("issues") or ["see audit trail"]))[:300])
    if not html:
        st.caption("no critic verdict recorded")
        return
    if revisions:
        st.markdown(f"🔥 **The Critic caught something on this case** — it sent the "
                    f"analysis back before approving. This is the quality gate doing its job.")
    st.markdown(html, unsafe_allow_html=True)


def render_agreement(risk, pol, case: dict | None) -> None:
    """Signature D: show whether the LLM and the rules agreed — disagreement is
    information, not noise."""
    try:
        model_flags = float(risk) >= 0.5
    except (TypeError, ValueError):
        model_flags = False
    policy_escalates = pol.suggested_disposition == config.ESCALATE
    a_color = RISK_RED if model_flags else GREEN
    p_color = RISK_RED if policy_escalates else GREEN
    agree = model_flags == policy_escalates
    pill = (f'<span style="background:rgba(55,214,138,.12);color:{GREEN};border:1px solid '
            f'{GREEN};border-radius:8px;padding:5px 12px;font-size:12px">✓ Both judges '
            f'agree</span>' if agree else
            f'<span style="background:rgba(244,177,60,.1);color:{AMBER};border:1px solid '
            f'{AMBER};border-radius:8px;padding:5px 12px;font-size:12px">⚠ Judges disagree '
            f'— resolved by the fusion rule'
            + (" + strong-model arbitration" if (case or {}).get("routing_tier") == "elevated"
               else "") + '</span>')
    st.markdown(
        f'<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:4px 0 10px">'
        f'<span style="background:#14181f;border:1px solid {a_color};color:{a_color};'
        f'border-radius:8px;padding:5px 12px;font-size:12px">Analyzer · LLM — '
        f'{"FLAGS FRAUD" if model_flags else "READS BENIGN"}</span>'
        f'<span style="background:#14181f;border:1px solid {p_color};color:{p_color};'
        f'border-radius:8px;padding:5px 12px;font-size:12px">Policy · RULES — '
        f'{pol.suggested_disposition}</span>{pill}</div>',
        unsafe_allow_html=True)


# ======================= human gate with real weight ==========================
def human_decisions(audit: dict | None) -> list[dict]:
    return [s for s in (audit or {}).get("steps", []) if s.get("agent") == "human_gate"]


def append_human_decision(txn_id: int, action: str, rationale: str) -> None:
    from datetime import datetime
    f = config.AUDIT_DIR / f"case_{txn_id}.json"
    a = json.loads(f.read_text())
    a["steps"].append({
        "seq": len(a["steps"]) + 1, "agent": "human_gate", "action": action,
        "detail": {"actor": "analyst@bank", "rationale": rationale,
                   "ts": datetime.now().isoformat(timespec="seconds")},
        "tool_calls": [],
    })
    f.write_text(json.dumps(a, indent=2, default=str))


def undo_human_decision(txn_id: int) -> None:
    f = config.AUDIT_DIR / f"case_{txn_id}.json"
    a = json.loads(f.read_text())
    if a["steps"] and a["steps"][-1].get("agent") == "human_gate":
        a["steps"].pop()
        f.write_text(json.dumps(a, indent=2, default=str))


def render_gate(txn_id: int, disposition: str, audit: dict | None) -> None:
    """The approval gate with real weight: confirm step, required rationale,
    decision written to the persistent audit trail (who/when/why), undo."""
    decided = human_decisions(audit)
    if decided:
        last = decided[-1]
        d = last["detail"]
        color = GREEN if "DISMISS" in last["action"] or "CLEAR" in last["action"] else RISK_RED
        st.markdown(
            f'<div style="background:#101319;border:1px solid {color};border-radius:12px;'
            f'padding:14px 16px;margin:4px 0 8px">'
            f'<div style="color:{color};font-weight:600;font-size:13px">DECISION LOGGED — '
            f'{last["action"]}</div>'
            f'<div style="color:#aab2bf;font-size:12.5px;margin-top:6px">'
            f'“{d.get("rationale", "")}”</div>'
            f'<div style="color:#6b7381;font-size:11px;margin-top:6px">'
            f'{d.get("actor")} · {d.get("ts")} · written to the case audit trail</div></div>',
            unsafe_allow_html=True)
        if st.button("↩︎ Undo decision", key=f"undo_{txn_id}"):
            undo_human_decision(txn_id)
            st.toast("Decision reverted and removed from the audit trail")
            st.rerun()
        return

    pending_key = f"gate_pending_{txn_id}"
    pending = st.session_state.get(pending_key)
    esc_label = ("▲ Approve escalation" if disposition == config.ESCALATE
                 else "▲ Override → escalate")
    clr_label = ("✓ Dismiss alert" if disposition == config.ESCALATE
                 else "✓ Confirm clear")
    if not pending:
        st.markdown("**Argus only recommends — nothing freezes or clears without your "
                    "explicit sign-off, and every decision is logged with a rationale.**")
        c1, c2 = st.columns(2)
        if c1.button(esc_label, key=f"esc_{txn_id}", type="primary",
                     use_container_width=True):
            st.session_state[pending_key] = "ESCALATION_APPROVED"
            st.rerun()
        if c2.button(clr_label, key=f"clr_{txn_id}", use_container_width=True):
            st.session_state[pending_key] = "DISMISSED_AS_FALSE_ALARM"
            st.rerun()
    else:
        action_h = ("freezes the account pending investigation"
                    if pending == "ESCALATION_APPROVED" else
                    "closes this alert as a false alarm")
        st.warning(f"**Confirm: {pending.replace('_', ' ').title()}** — this {action_h} "
                   f"for txn {txn_id}. A rationale is required; it becomes part of the "
                   f"permanent audit record.")
        rat = st.text_area("Your rationale (min 8 characters — who reviews this later "
                           "should understand your reasoning)", key=f"rat_{txn_id}")
        ok = len((rat or "").strip()) >= 8
        st.caption(("✅ " if ok else "") + f"{len((rat or '').strip())} / 8 min chars")
        c1, c2 = st.columns(2)
        if c1.button("Confirm decision", key=f"conf_{txn_id}", type="primary",
                     disabled=not ok, use_container_width=True):
            append_human_decision(txn_id, pending, rat.strip())
            del st.session_state[pending_key]
            st.toast(f"{pending.replace('_', ' ').title()} · logged to audit trail")
            st.rerun()
        if c2.button("Cancel", key=f"canc_{txn_id}", use_container_width=True):
            del st.session_state[pending_key]
            st.rerun()


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
    render_baseline_chart(ctx, risk)
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

    # ---- 3. money flow ----------------------------------------------------------
    st.markdown("#### ③ Where the money went")
    render_money_flow(ctx)

    # ---- 4. analyzer signals --------------------------------------------------
    st.markdown("#### ④ Risk signals the Analyzer found *(LLM reasoning over the evidence)*")
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

    # ---- 5. policy rules ------------------------------------------------------
    st.markdown("#### ⑤ Policy rules *(deterministic code — same input, same answer, "
                "auditable by a regulator)*")
    from agents import policy as policy_engine
    pol = policy_engine.evaluate(txn, vel, cp)
    rows = [{"rule": f.rule,
             "fired": "🔴 YES" if f.triggered else "— no",
             "what it checks": RULE_EXPLAIN.get(f.rule, ""),
             "values seen": f.detail} for f in pol.flags]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption(f"Policy engine verdict: **{pol.suggested_disposition}** — {pol.reason}")

    # ---- 6. critic ------------------------------------------------------------
    st.markdown("#### ⑥ The Critic's fact-check *(a second model verifies every claim "
                "against the evidence before anything is finalized)*")
    render_critic_loop(audit, case)

    # ---- 7. how the decision was made ------------------------------------------
    st.markdown("#### ⑦ How the final decision was made")
    render_agreement(risk, pol, case)
    rt = (case or {}).get("routing_tier")
    if rt:
        if rt == "elevated":
            st.info(f"🔀 **Model routing: ELEVATED** — this case was re-examined by the "
                    f"strong model (`{config.STRONG_MODEL}`). Why: "
                    f"{(case or {}).get('routing_reason', '')}")
        else:
            st.caption(f"🔀 Model routing: standard tier — "
                       f"{(case or {}).get('routing_reason', '')}")
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

    # ---- 8. your decision (the human gate) --------------------------------------
    st.markdown("#### ⑧ Your decision")
    render_gate(txn_id, disp, audit)

    # ---- 9. audit trail -----------------------------------------------------------
    if audit:
        st.markdown("#### ⑨ Audit trail")
        st.caption("Every step of this investigation, in order — including your decision. "
                   "This is the record a regulator or dispute reviewer would read.")
        with st.expander("Open the full trail"):
            icons = {"orchestrator": "🎯", "retriever": "🔎", "analyzer": "🧠",
                     "policy": "📏", "critic": "⚖️", "case_assembler": "📁",
                     "memory": "💾", "guardrail": "🛡️", "router": "🔀",
                     "human_gate": "👤"}
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
            "| 🔀 Router | sends ambiguous/high-stakes cases to the strong model, keeps "
            "routine ones on the cheap one (cost-aware) | code |\n"
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
