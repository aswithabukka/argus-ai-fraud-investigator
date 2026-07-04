# Argus — Multi-Agent Fraud Triage & Investigation Assistant

**Subtitle:** Turning a flood of transaction alerts into vetted, audit-ready case files — with a Critic that fact-checks every claim and a human who approves every action.

**Track:** Agents for Business

**Links:** _(fill in before submitting)_
- Notebook: `<public Kaggle notebook URL>`
- GitHub repo: https://github.com/aswithabukka/argus-ai-fraud-investigator
- Demo video (≤5 min): `<public YouTube URL>`

**Media gallery:** cover image · architecture diagram (`docs/screenshots/architecture.png`) · workbench screenshots (overview, case file, live triage)

---

## The problem (why this matters)

Fraud operations teams are buried in transaction alerts, and the large majority are false positives. Every alert still costs a human analyst the same slow ritual: pull the transaction, gather the customer's history, check it against policy, and write a defensible decision. It's expensive, inconsistent, and it doesn't scale. And the obvious shortcut — "just ask an LLM if it's fraud" — fails exactly where it matters: a single prompt has no real evidence, can't be audited, and will confidently hallucinate a reason. In fraud, a made-up justification that triggers a real account freeze is worse than no answer at all.

## What Argus does

Argus ingests a fraud alert and runs the investigation a human analyst would, as a team of specialized agents coordinated by an orchestrator:

- **Retriever** gathers evidence by calling data tools over an **MCP server** — the customer's baseline behavior, recent history, the counterparty's risk profile, and velocity signals.
- **Analyzer** reasons over that evidence to produce a risk score and a set of signals, each of which **must cite the specific evidence that supports it**.
- **Policy** is a deterministic, auditable rules engine (thresholds + AML-style checks) — not an LLM — because a regulator wants to see the exact rule that fired.
- **Critic** — the key quality mechanism — fact-checks the Analyzer's and Policy's reasoning **against the actual evidence bundle**, flags any hallucinated figure or unsupported claim, and sends the case back for one revision if it doesn't hold up.
- **Case Assembler** fuses the LLM risk score with the policy result (a score-fusion step) into an analyst-ready case file marked `PENDING_HUMAN_APPROVAL`.

**No freeze or block is ever executed automatically.** Argus only recommends; a human approves. Every step — each agent, each tool call, each decision, the critic's verdict — is written to a per-case JSON audit trail.

## How it was built

- **Google ADK + Gemini.** Each agent is an ADK `LlmAgent`; the orchestration is explicit, readable Python (not a hidden framework graph) so every decision is inspectable. Gemini 2.5 Flash runs the pipeline — the Critic is a separate adversarial role with its own prompt and context, so it verifies rather than rubber-stamps (on a paid tier it's one env var to move the Critic to a distinct model).
- **Cost-aware model routing.** A router keeps routine cases entirely on Flash and elevates only the cases where extra judgment can change the outcome — ambiguous risk scores, model-vs-policy disagreements, and $1M+ high-stakes calls — to Gemini 2.5 Pro. High risk is not high uncertainty: a textbook drain-to-mule stays on the cheap tier. The routing decision (and its reason) is logged to the audit trail like every other step.
- **MCP server.** The five transaction data tools are served over the Model Context Protocol; the Retriever consumes them as MCP tools. The evidence bundle is then assembled deterministically from exact tool outputs, so downstream reasoning never works from LLM-paraphrased numbers.
- **Guardrails & security.** PII masking of account identifiers before any model call (reversed only in the final local case file); pydantic schema validation on every agent's input and output; an evidence-citation guardrail that rejects any conclusion with no supporting evidence; and the human-in-the-loop approval gate.
- **Memory.** Session memory carries the working case state between agents; a long-term pattern store lets confirmed fraud shapes sharpen future triage.
- **Data.** [PaySim](https://www.kaggle.com/datasets/ealaxi/paysim1) (synthetic, free), which ships with an `isFraud` label — used only for scoring, never exposed to the agents.
- **Deployability.** Packaged behind a FastAPI service with a Dockerfile for one-command Cloud Run deployment.

## The analyst workbench (the demo)

Argus ships with a dark security-console **analyst workbench** (FastAPI + a dependency-free frontend, served at `/`). It is where the human-in-the-loop actually lives:

- **Case files** — every investigated alert as a full case report: the alert, the evidence gathered over MCP (with an "amount vs this account's own history" baseline chart), a money-flow diagram of where the funds went, the policy rules that fired, the Critic's pass/reject loop, and how model + rules were fused.
- **Live triage** — pick a queued alert and watch the real pipeline run through all six agent stages, then decide.
- **The gate** — nothing is escalated or cleared without an explicit confirm plus a **required written rationale**; both are appended to the case's audit trail (with undo). The queue status flips only after the human commits.
- **Ask Argus** — grounded Q&A over one case's record; if the answer isn't in the record, it says so instead of guessing.

## Results — the before/after

The headline is an honest comparison against a **single-agent baseline** (one prompt, no tools, no critic) on the same balanced eval set, scored against ground truth, plus an LLM-as-judge **faithfulness** score measuring how well each case's reasoning is actually supported by its evidence.

| System | Precision | Recall | F1 | Faithfulness |
|---|---|---|---|---|
| Single-agent baseline | .481 | .925 | .632 | n/a |
| **Argus (full)** | **.506** | **.975** | **.667** | **0.86** |

On 80 balanced PaySim alerts (40 fraud / 40 legitimate), Argus caught **39 of 40 frauds** and won **5 of the 6 head-to-head disagreements** with the baseline — recovering 3 frauds the baseline missed and correctly clearing 2 false alarms the baseline escalated. Precision is modest for both systems by design: the legitimate alerts in the eval set are large transfers ($550K–$1.5M) chosen to *look* like fraud, so size alone can't separate them.

_(Regenerate with `python -m eval.run_eval`; the table is written to `results/metrics.csv`.)_

Beyond the headline numbers: the long-term **pattern memory** matched a known fraud shape on 31 of 80 cases, and the Critic's revision loop is what drives the 0.86 faithfulness — unsupported claims get rejected before a human ever sees them.

## Capstone concepts demonstrated

Multi-agent orchestration (ADK) · MCP server · Tool use · Memory · Evaluation (baseline + LLM-judge) · Guardrails/security (PII, validation, human gate) · Observability (audit trail) · Deployability (Docker + Cloud Run) · Cost-aware model routing.

## Impact & honest limitations

For a fraud ops team, Argus converts unstructured alert triage into consistent, evidence-cited case files with a built-in hallucination check and a full audit trail — the difference between "the model said so" and "here is the evidence, the rule, and who approved it." Limitations: PaySim is synthetic and its fraud shapes are simpler than production traffic; the thresholds are illustrative and would be tuned per portfolio; and the pattern store is intentionally a simple JSON, upgradeable to a vector store. The architecture — evidence-grounded specialists, a fact-checking critic, deterministic policy, and a human gate — is the part that transfers directly to a real deployment.
