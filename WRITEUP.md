# Argus — Multi-Agent Fraud Triage & Investigation Assistant

**Subtitle:** Turning a flood of transaction alerts into vetted, audit-ready case files — with a Critic that fact-checks every claim and a human who approves every action.

**Track:** Agents for Business

**Links:** _(fill in before submitting)_
- Notebook: `<public Kaggle notebook URL>`
- GitHub repo: `<public repo URL>`
- Demo video (≤5 min): `<public YouTube URL>`

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

- **Google ADK + Gemini.** Each agent is an ADK `LlmAgent`; the orchestration is explicit, readable Python (not a hidden framework graph) so every decision is inspectable. Gemini Flash runs the specialists; Gemini Pro runs the Critic, since catching another agent's mistake is the harder job.
- **MCP server.** The five transaction data tools are served over the Model Context Protocol; the Retriever consumes them as MCP tools. The evidence bundle is then assembled deterministically from exact tool outputs, so downstream reasoning never works from LLM-paraphrased numbers.
- **Guardrails & security.** PII masking of account identifiers before any model call (reversed only in the final local case file); pydantic schema validation on every agent's input and output; an evidence-citation guardrail that rejects any conclusion with no supporting evidence; and the human-in-the-loop approval gate.
- **Memory.** Session memory carries the working case state between agents; a long-term pattern store lets confirmed fraud shapes sharpen future triage.
- **Data.** [PaySim](https://www.kaggle.com/datasets/ealaxi/paysim1) (synthetic, free), which ships with an `isFraud` label — used only for scoring, never exposed to the agents.
- **Deployability.** Packaged behind a FastAPI service with a Dockerfile for one-command Cloud Run deployment.

## Results — the before/after

The headline is an honest comparison against a **single-agent baseline** (one prompt, no tools, no critic) on the same balanced eval set, scored against ground truth, plus an LLM-as-judge **faithfulness** score measuring how well each case's reasoning is actually supported by its evidence.

| System | Precision | Recall | F1 | Faithfulness |
|---|---|---|---|---|
| Single-agent baseline | _run to fill_ | _run_ | _run_ | n/a |
| **Argus (full)** | _run_ | _run_ | _run_ | _run_ |

_(Regenerate with `python -m eval.run_eval`; the table is written to `results/metrics.csv`.)_

## Capstone concepts demonstrated

Multi-agent orchestration (ADK) · MCP server · Tool use · Memory · Evaluation (baseline + LLM-judge) · Guardrails/security (PII, validation, human gate) · Observability (audit trail) · Deployability (Docker + Cloud Run).

## Impact & honest limitations

For a fraud ops team, Argus converts unstructured alert triage into consistent, evidence-cited case files with a built-in hallucination check and a full audit trail — the difference between "the model said so" and "here is the evidence, the rule, and who approved it." Limitations: PaySim is synthetic and its fraud shapes are simpler than production traffic; the thresholds are illustrative and would be tuned per portfolio; and the pattern store is intentionally a simple JSON, upgradeable to a vector store. The architecture — evidence-grounded specialists, a fact-checking critic, deterministic policy, and a human gate — is the part that transfers directly to a real deployment.
