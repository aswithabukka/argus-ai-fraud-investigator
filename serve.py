"""FastAPI service wrapper — the deployability concept.

Exposes Argus as an HTTP endpoint so it can run on Cloud Run (or any container
host). POST a txn_id, get back the analyst-ready case file (still
PENDING_HUMAN_APPROVAL — the service recommends, it never acts).

    uvicorn serve:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agents import orchestrator
from guardrails.validation import ValidationError
from schemas import CaseFile

app = FastAPI(title="Argus — Fraud Triage", version="1.0")


class TriageRequest(BaseModel):
    txn_id: int


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/triage", response_model=CaseFile)
async def triage(req: TriageRequest) -> CaseFile:
    try:
        case, _ = await orchestrator.triage_alert(req.txn_id)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return case
