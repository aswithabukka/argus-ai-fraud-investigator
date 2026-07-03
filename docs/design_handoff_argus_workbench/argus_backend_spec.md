# ARGUS — Multi-Agent Fraud Triage & Investigation Assistant
### Claude Code Build Prompt / Project Spec

---

## 0. Your task

You are building a project called **Argus**: a multi-agent system that triages and investigates fraud alerts and produces analyst-ready case files, with a human approval gate before any action. It is my submission for the Kaggle *AI Agents: Intensive Vibe Coding* capstone.

Build it in **Python**, using the **Anthropic Claude API** as the model layer (not Gemini). Work **phase by phase** per the Build Plan in section 13. After each phase, summarize what you did, run a quick smoke test, and wait for my go-ahead before moving on. Prefer clear, well-commented, transparent code over framework magic — I need to explain this system in interviews.

---

## 1. Context — the Kaggle capstone requirements this must satisfy

This is a **hackathon**, judged by a human panel against a rubric. There is **no leaderboard and no automated scoring** — the judges read a writeup, watch a demo video, and may open the notebook. So the code must be **reproducible, runnable end-to-end on a small sample, and self-evaluating** (it produces its own metrics).

The final submission (which this code supports) will be a **Kaggle Writeup** under the **"Agents for Business"** track, containing:
- Title, subtitle, and a project description (~250 words) covering the problem, how it was built, and its impact.
- A **public notebook** with the code and evaluation.
- A **≤2-minute demo video**, publicly viewable, tracing one alert through the system.
- All links public (no login/paywall) so judges can access them.

The rubric rewards demonstrating the full agent stack, so the build must clearly exercise: **tool use, memory, multi-agent orchestration, evaluation, and guardrails/security.** Data and tools must be **free and publicly accessible.**

---

## 2. Problem statement

Fraud operations teams are flooded with transaction alerts, the large majority of which are false positives. Each still needs a human to gather context, check patterns and policy, and write up a decision — slow, expensive, and inconsistent. A single LLM prompt can't do this reliably or auditably.

**Argus** ingests a transaction alert, orchestrates specialist agents to investigate it, fact-checks its own reasoning, and outputs a structured, analyst-ready case file with a recommended disposition (escalate / clear) and the evidence behind it. No blocking or freezing action is ever executed automatically — Argus only recommends, and a human approves.

---

## 3. Architecture — what to build

A coordinating **Orchestrator** dispatches an alert to specialist agents, collects their findings, has a **Critic** verify them, assembles a case file, and routes it to a **human approval gate**.

```
Alert ──► Orchestrator ──► Retriever ──► Analyzer ──► Policy ──► Critic ──► Case File ──► Human Gate
                │              (tools)     (signals)   (rules)   (verify)                 (approve)
                └──────────────── session memory + long-term pattern store ───────────────┘
```

Use an **explicit custom orchestrator** built on the Anthropic Messages API tool-use loop (transparent and easy to explain). LangGraph is an acceptable alternative if it makes the graph cleaner, but default to the custom orchestrator.

---

## 4. Tech stack

- **Language:** Python 3.11+
- **Model layer:** `anthropic` Python SDK, Messages API with tool use.
  - Default workhorse model: `claude-sonnet-5`
  - Cheap/fast sub-steps (formatting, simple retrieval): `claude-haiku-4-5`
  - Critic (optional, for stronger verification): `claude-opus-4-8`
  - *Verify exact model strings against current Anthropic docs before running.*
- **Data:** `pandas`; dataset via `kagglehub`.
- **Schemas / validation:** `pydantic` for all agent inputs/outputs (enforce structured JSON).
- **Config:** `python-dotenv` for the API key (`ANTHROPIC_API_KEY`), never hard-coded.
- **Logging:** standard `logging` plus a structured per-case audit trail (JSON).
- **Notebook:** a Kaggle-compatible `.ipynb` that runs the whole pipeline + eval on the sample.

---

## 5. Data

**Primary dataset: PaySim** (synthetic mobile-money transactions, free on Kaggle). Chosen because it has human-readable fields (transaction `type`, `amount`, origin/destination account balances) *and* an `isFraud` ground-truth label — so agents can produce readable investigations and we get eval labels for free.

- Load via `kagglehub.dataset_download(...)` (works inside a Kaggle Notebook, free with an account).
- Columns to use: `step, type, amount, nameOrig, oldbalanceOrg, newbalanceOrig, nameDest, oldbalanceDest, newbalanceDest, isFraud`.

**Tools = functions over the dataframe** (this is the "tool use" pillar). Implement at minimum:
- `get_transaction(txn_id)` — return the alerted transaction.
- `get_customer_history(account_id, n)` — recent transactions for an account.
- `get_customer_baseline(account_id)` — typical amount/frequency/type stats.
- `get_counterparty_risk(account_id)` — activity profile of the destination account.
- `compute_velocity_signals(account_id, window)` — count/sum of recent transfers.

**Curated eval set:** sample ~50–100 transactions, balanced between `isFraud=1` and `isFraud=0`, saved to `data/eval_set.csv`. Small and inspectable on purpose.

---

## 6. The agents

Each agent takes structured input and returns a validated pydantic model. Keep prompts in a `prompts/` folder, one file per agent.

1. **Orchestrator** — receives the alert, plans the investigation, calls specialists in order, handles retries, and triggers case assembly. Owns session memory.
2. **Retriever** — uses the data tools to gather the transaction, customer history, baseline, and counterparty profile. Output: a structured evidence bundle. No judgments.
3. **Analyzer** — reasons over the evidence: computes/interprets risk signals (amount vs. the customer's own baseline, velocity, balance-draining patterns, suspicious `type` sequences like TRANSFER→CASH_OUT). Output: a risk assessment with a score and the specific signals that drove it.
4. **Policy** — checks the case against configurable fraud thresholds and simple regulatory/AML rules (e.g., structuring-like patterns). Output: policy flags and a suggested disposition.
5. **Critic** — reviews the Analyzer's and Policy's reasoning **against the actual evidence bundle**. Flags unsupported claims, hallucinated figures, or gaps, and either approves or sends it back for one revision. **This is the key quality mechanism — do not skip it.**
6. **Case Assembler + Human Gate** — compiles a case file (summary, evidence, signals, recommendation, confidence) and marks it `PENDING_HUMAN_APPROVAL`. No action executes without an explicit approve step (simulate approval in the notebook).

---

## 7. Memory

- **Session (case) memory:** the working state for the active alert — evidence, intermediate findings, critic feedback — passed between agents.
- **Long-term pattern store:** a simple JSON/dict (upgrade to a vector store only if trivial) of confirmed fraud patterns; the Analyzer consults it to sharpen future triage. Demonstrate that a newly confirmed pattern influences a later case.

---

## 8. Guardrails & safety

- **PII masking:** mask account identifiers before sending to the model; unmask only in the final local case file.
- **Input validation:** pydantic schema check on every incoming transaction; reject malformed input.
- **Output validation:** every agent returns strict JSON; every conclusion in the case file **must cite the specific signals/evidence it used** — reject and retry outputs that don't.
- **Human-in-the-loop gate:** Argus never auto-executes a freeze/block; it only recommends. Approval is a distinct, explicit step.
- **No real side effects:** all "actions" are simulated; nothing leaves the notebook.

---

## 9. Observability

Maintain a per-case **audit trail** object that logs, in order: every agent invoked, every tool call with its arguments and result, each agent's decision, critic feedback, and the final recommendation. Save it as JSON per case and print a clean, human-readable trace in the demo cell.

---

## 10. Evaluation harness (the differentiator — build this carefully)

1. Run Argus on the curated eval set; record each disposition (escalate/clear).
2. **Detection metrics:** precision, recall, F1 against the `isFraud` label.
3. **Faithfulness metric:** for each case, score whether the narrative's reasoning actually matches the evidence bundle. Implement as an **LLM-as-judge** pass using Claude (separate call), returning a 0–1 faithfulness score; also allow manual override.
4. **Baseline:** implement a **single-agent** version (one prompt: "here is a transaction, is it fraud?", no specialists, no critic) and run it on the same eval set.
5. **Report the delta** as a metrics table: single-agent vs. full Argus on precision, recall, F1, and faithfulness. This before/after comparison is the headline result.
6. Save results to `results/metrics.csv` and render the table in the notebook.

---

## 11. What the code must ultimately produce

- A public-ready **Kaggle Notebook** that runs the full pipeline + eval on the sample end-to-end.
- A **metrics table** showing Argus beating the single-agent baseline.
- A **demo cell** that traces one alert from ingestion → investigation → critic → case file → approval, printing the readable audit trail.
- A **`WRITEUP.md` stub** with the required sections: title, subtitle, track (Agents for Business), ~250-word description, impact, "how it was built," and placeholders for the notebook/video links.

---

## 12. Suggested repo structure

```
argus/
├── README.md
├── WRITEUP.md                 # Kaggle writeup draft
├── requirements.txt
├── .env.example               # ANTHROPIC_API_KEY=
├── config.py                  # thresholds, model names, paths
├── data/
│   ├── load_data.py           # kagglehub download + eval-set builder
│   └── eval_set.csv
├── tools/
│   └── data_tools.py          # the dataframe tool functions
├── agents/
│   ├── orchestrator.py
│   ├── retriever.py
│   ├── analyzer.py
│   ├── policy.py
│   ├── critic.py
│   └── case_assembler.py
├── prompts/                   # one prompt file per agent
├── memory/
│   ├── session.py
│   └── pattern_store.py
├── guardrails/
│   ├── pii.py
│   └── validation.py
├── observability/
│   └── audit.py
├── eval/
│   ├── run_eval.py
│   ├── baseline.py            # single-agent baseline
│   └── judge.py               # LLM-as-judge faithfulness
├── results/
│   └── metrics.csv
├── demo.py                    # trace one alert
└── notebook/
    └── argus_capstone.ipynb
```

---

## 13. Build plan — do these in order, checking in after each phase

- **Phase 0 — Scaffold:** repo structure, `requirements.txt`, `config.py`, `.env` handling, and `data/load_data.py` (download PaySim, build the balanced eval set). Smoke test: load data, print shape and class balance.
- **Phase 1 — Tools:** implement the dataframe tool functions in `tools/data_tools.py` with a couple of unit checks.
- **Phase 2 — Single agents:** Retriever, Analyzer, Policy — each callable in isolation on one transaction, returning validated pydantic output.
- **Phase 3 — Orchestrator + Case Assembler:** wire the specialists into one pipeline that produces a case file (no critic yet). Run one alert end-to-end.
- **Phase 4 — Critic + Human Gate:** add the verification loop and the explicit approval step.
- **Phase 5 — Guardrails + Observability:** PII masking, input/output validation, the audit trail, and the readable trace.
- **Phase 6 — Evaluation:** the single-agent baseline, the eval runner, the LLM-judge faithfulness pass, and the metrics table.
- **Phase 7 — Package:** assemble the notebook, write `demo.py`, and draft `WRITEUP.md`.
- **(Optional bonus) Phase 8 — MCP:** expose the data tools via a local MCP server and have agents call them, to showcase MCP fluency and align with the course. Keep the plain-function path working as the default.

---

## 14. Definition of done

- All six agents implemented and wired through the orchestrator.
- Notebook runs end-to-end on the eval sample with no manual steps beyond the simulated approval.
- Metrics table shows full Argus outperforming the single-agent baseline on precision/recall/F1 and faithfulness.
- Guardrails active: PII masked, outputs validated, human gate enforced, no real actions.
- Per-case audit trail produced and printed for the demo case.
- `WRITEUP.md` drafted with all required sections.

---

## 15. Constraints & notes

- Use only free, public data; keep everything runnable in a Kaggle Notebook (CPU is fine).
- Never hard-code the API key; read from environment.
- Verify current Anthropic model strings before running.
- Keep the code readable and the architecture explicit — interview-explainability is a first-class goal.
- Start with Phase 0 now and check in with me before Phase 1.
