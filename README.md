# Argus — Multi-Agent Fraud Triage & Investigation Assistant

Kaggle **AI Agents: Intensive Vibe Coding** capstone — *Agents for Business* track.

Fraud ops teams drown in transaction alerts, most of them false positives, and every
one needs a human to gather context, check policy, and write up a decision. Argus
turns that flood into vetted, analyst-ready case files: an orchestrator dispatches
each alert to specialist agents, a Critic fact-checks their reasoning against the
actual evidence, and the result is a structured case file with a recommended
disposition. **No freeze/block action ever executes without human approval.**

```
Alert → Orchestrator → Retriever → Analyzer → Policy → Critic → Case File → Human Gate
              │            └────── data tools served via MCP ──────┘
              └── session memory + long-term fraud-pattern store
```

## Capstone concepts demonstrated

| Concept | Where |
|---|---|
| Multi-agent system (ADK) | Orchestrator + 5 specialist agents (`agents/`) |
| MCP server | Transaction data tools served over MCP (`tools/`) |
| Security | PII masking, I/O validation, human approval gate (`guardrails/`) |
| Deployability | Dockerfile + Cloud Run instructions |

Built with Google ADK + Gemini. Evaluated on [PaySim](https://www.kaggle.com/datasets/ealaxi/paysim1)
with a single-prompt baseline vs. full-Argus comparison (precision / recall / F1 /
LLM-judged faithfulness) — see `eval/`.

## Quickstart

```bash
uv venv --python 3.13 && uv pip install -r requirements.txt
cp .env.example .env   # add your Google AI Studio key
python -m data.load_data          # download PaySim + build eval set
python demo.py                    # trace one alert end-to-end
python -m eval.run_eval           # full eval: baseline vs Argus
```

## Deploy (Cloud Run)

Argus runs as a FastAPI service (`serve.py`, `POST /triage`) behind a Dockerfile.

```bash
# local container
docker build -t argus .
docker run -p 8080:8080 -e GOOGLE_API_KEY=$GOOGLE_API_KEY argus
curl -X POST localhost:8080/triage -H 'content-type: application/json' -d '{"txn_id": 6102387}'

# Google Cloud Run
gcloud run deploy argus --source . --region us-central1 \
  --set-env-vars GOOGLE_API_KEY=$GOOGLE_API_KEY --allow-unauthenticated
```

The service only ever *recommends* — every case comes back `PENDING_HUMAN_APPROVAL`.

## Repo map

- `agents/` — orchestrator, retriever, analyzer, policy, critic, case assembler
- `tools/` — dataframe tool functions + MCP server
- `guardrails/` — PII masking, pydantic I/O validation
- `memory/` — session state + long-term fraud-pattern store
- `observability/` — per-case JSON audit trail
- `eval/` — eval runner, single-agent baseline, LLM-as-judge faithfulness
- `notebook/` — Kaggle-ready notebook (full pipeline + eval)
