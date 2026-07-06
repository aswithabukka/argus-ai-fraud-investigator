"""Generates notebook/argus_capstone.ipynb (Kaggle-ready).

Kept as a builder script so the notebook is regenerable and reviewable in diff.
    python notebook/build_notebook.py
"""

import json
from pathlib import Path

GITHUB_URL = "https://github.com/aswithabukka/argus-ai-fraud-investigator"


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code(text):
    return {"cell_type": "code", "metadata": {}, "execution_count": None,
            "outputs": [], "source": text.splitlines(keepends=True)}


cells = [
    md("""# Argus — Multi-Agent Fraud Triage & Investigation Assistant
### Kaggle AI Agents: Intensive Vibe Coding — *Agents for Business*

Fraud ops teams drown in transaction alerts, most of them false positives. Argus
turns that flood into vetted, audit-ready case files: an **Orchestrator** dispatches
each alert to specialist agents, a **Critic** fact-checks their reasoning against the
actual evidence, and the result is an analyst-ready case file with a recommended
disposition. **No freeze/block ever executes without a human approving it.**

```
Alert → Orchestrator → Retriever → Analyzer → Policy → Critic → Case File → Human Gate
              │            └────── data tools served via MCP ──────┘
              └── session memory + long-term fraud-pattern store
```

**Concepts demonstrated:** multi-agent orchestration (ADK) · MCP server · tool use ·
memory · evaluation (single-agent baseline + LLM-as-judge faithfulness) ·
guardrails/security (PII masking, schema validation, human gate) · observability
(per-case audit trail) · deployability (FastAPI + Docker/Cloud Run)."""),

    md("""## 1. Setup

Install dependencies and pull the code. The full, commented source lives in the
GitHub repo; the notebook clones it so every agent is inspectable.

> **Before running:** (1) attach the PaySim dataset via **+ Add Input →** search
> `ealaxi/paysim1` (the loader reads it straight from `/kaggle/input` — no
> download), (2) turn **Internet ON** in Session options (for `pip` + `git
> clone`), and (3) add your `GOOGLE_API_KEY` under **Add-ons → Secrets**."""),

    code(f"""!pip install -q google-adk google-genai kagglehub mcp scikit-learn nest-asyncio pydantic
!git clone -q {GITHUB_URL} argus_repo || echo "repo already cloned"
%cd argus_repo"""),

    md("""### API key

This notebook uses Google Gemini via a **free** [AI Studio](https://aistudio.google.com/apikey)
key. On Kaggle, add it under **Add-ons → Secrets** as `GOOGLE_API_KEY`; the cell
below loads it. (Locally, put it in a `.env` file instead.)"""),

    code("""import os
try:
    from kaggle_secrets import UserSecretsClient
    os.environ["GOOGLE_API_KEY"] = UserSecretsClient().get_secret("GOOGLE_API_KEY")
    print("Loaded GOOGLE_API_KEY from Kaggle secrets.")
except Exception:
    from dotenv import load_dotenv
    load_dotenv()
    print("Loaded key from environment / .env" if os.getenv("GOOGLE_API_KEY")
          else "WARNING: set GOOGLE_API_KEY before running the agents.")

import nest_asyncio
nest_asyncio.apply()  # allow the ADK async run loop inside the notebook"""),

    md("""## 2. Data — PaySim

Synthetic mobile-money transactions with an `isFraud` ground-truth label (used
only for scoring — the agents never see it). We build a small, balanced,
inspectable eval set of alert-like transactions."""),

    code("""from data.load_data import load_transactions, build_eval_set
df = load_transactions()
eval_set = build_eval_set(df)
print(f"{len(df):,} transactions | eval set: {len(eval_set)} alerts")
eval_set[["txn_id", "type", "amount", "isFraud"]].head()"""),

    md("""## 3. Demo — trace one alert end-to-end

Watch a single fraud alert flow through every agent: evidence gathered over MCP,
risk assessed, policy checked, the **Critic** fact-checking the reasoning, the
case assembled, and the **human approval gate**. The full audit trail prints below."""),

    code("""from agents import orchestrator
from agents.case_assembler import approve_case

fraud_txn = int(eval_set[eval_set.isFraud == 1].iloc[0].txn_id)
case, audit = await orchestrator.triage_alert(fraud_txn)
print(audit.render())"""),

    code("""print("DISPOSITION:", case.disposition, "| confidence:", case.confidence)
print("SUMMARY:", case.summary)
print("CRITIC approved:", case.critic_verdict.approved,
      "| unsupported claims:", case.critic_verdict.unsupported_claims)
print("STATUS:", case.status)

# Human-in-the-loop gate — nothing acts without this explicit step.
decided = approve_case(case, approver="analyst@bank", approved=True)
print("After human approval ->", decided.status)"""),

    md("""## 4. Guardrails in action

PII is masked before anything reaches the model; account ids only reappear in the
final local case file. Every risk signal must cite the evidence that supports it."""),

    code("""from guardrails.pii import PIIMasker
from tools import data_tools
m = PIIMasker()
raw = data_tools.get_transaction(fraud_txn)
masked = m.masked_copy(raw)
print("real id sent to model? ", raw["nameOrig"], "->", masked["nameOrig"])
print("evidence-cited signals:")
for s in case.risk_assessment.signals:
    print(f"  - {s.name} [{s.severity}] cites -> {s.evidence_ref}")"""),

    md("""## 5. Evaluation — single-agent baseline vs. full Argus

The headline result. We run a naive single-prompt baseline (no tools, no critic)
and full Argus on the same alerts, score both against ground truth, and add an
LLM-as-judge **faithfulness** score for Argus. Runs on a subset here to respect
free-tier rate limits; use `run()` with no limit for the full set."""),

    code("""from eval.run_eval import run
metrics = await run(limit=10)
metrics"""),

    md("""## 6. Conclusion

Argus shows that the reliable way to put an LLM near a high-stakes decision is
**not** to trust one prompt, but to surround it with structure: specialist agents
that gather real evidence, a deterministic policy engine, a Critic that refuses
to let unsupported claims through, and a human who approves every action — all on
a full audit trail. The result is fraud triage that is faster, consistent, and
*defensible*.

**Repo (full source + Dockerfile/Cloud Run):** see the GitHub link at the top.""")
]

nb = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

out = Path(__file__).parent / "argus_capstone.ipynb"
out.write_text(json.dumps(nb, indent=1))
print(f"wrote {out}")
