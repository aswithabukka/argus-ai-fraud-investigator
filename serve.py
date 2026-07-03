"""FastAPI service wrapper — the deployability concept.

Exposes Argus as an HTTP endpoint so it can run on Cloud Run (or any container
host). POST a txn_id, get back the analyst-ready case file (still
PENDING_HUMAN_APPROVAL — the service recommends, it never acts).

    uvicorn serve:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import config
import workbench_export as wb
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


# ======================= analyst workbench (frontend) ========================
# Pixel-faithful port of docs/design_handoff_argus_workbench, wired to real data.

@app.get("/")
def workbench() -> FileResponse:
    return FileResponse(config.ROOT / "workbench" / "index.html")


@app.get("/api/cases")
def api_cases() -> list[dict]:
    cases = wb.build_all()
    for c in cases:  # merge live human decisions (change at runtime)
        c["humanLog"] = wb.human_log(int(c["id"]))
    return cases


@app.get("/api/stats")
def api_stats() -> dict:
    return wb.stats()


class DecisionRequest(BaseModel):
    caseId: str
    action: str  # approved | dismissed
    rationale: str


@app.post("/api/decision")
def api_decision(req: DecisionRequest) -> dict:
    if len(req.rationale.strip()) < 8:
        raise HTTPException(status_code=400, detail="rationale must be ≥8 chars")
    f = config.AUDIT_DIR / f"case_{req.caseId}.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="unknown case")
    audit = json.loads(f.read_text())
    audit["steps"].append({
        "seq": len(audit["steps"]) + 1, "agent": "human_gate",
        "action": "ESCALATION_APPROVED" if req.action == "approved"
                  else "DISMISSED_AS_FALSE_ALARM",
        "detail": {"actor": "A. Reyes", "rationale": req.rationale.strip(),
                   "ts": datetime.now().strftime("%H:%M:%S")},
        "tool_calls": [],
    })
    f.write_text(json.dumps(audit, indent=2, default=str))
    return {"ok": True}


@app.delete("/api/decision/{case_id}")
def api_undo_decision(case_id: str) -> dict:
    f = config.AUDIT_DIR / f"case_{case_id}.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="unknown case")
    audit = json.loads(f.read_text())
    if audit["steps"] and audit["steps"][-1].get("agent") == "human_gate":
        audit["steps"].pop()
        f.write_text(json.dumps(audit, indent=2, default=str))
    return {"ok": True}


class AskRequest(BaseModel):
    caseId: str
    question: str


_genai_client = None


def _client():
    global _genai_client
    if _genai_client is None:
        from google import genai
        _genai_client = genai.Client()
    return _genai_client


@app.post("/api/ask")
def api_ask(req: AskRequest) -> dict:
    f = config.AUDIT_DIR / f"case_{req.caseId}.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="unknown case")
    audit = json.loads(f.read_text())
    case_f = config.CASES_DIR / f"case_{req.caseId}.json"
    case = json.loads(case_f.read_text()) if case_f.exists() else {}
    payload = {"audit_trail": audit, "case_file": case}
    prompt = (
        "You are Argus, a fraud-investigation assistant talking to a bank analyst. "
        "Answer the question using ONLY the case record below. Be concise and "
        "plain-English; cite the specific evidence or step that supports each point. "
        "If the record doesn't contain the answer, say so instead of guessing.\n\n"
        f"CASE RECORD:\n{json.dumps(payload, default=str)[:60000]}\n\n"
        f"QUESTION: {req.question}"
    )
    r = _client().models.generate_content(model=config.WORKHORSE_MODEL,
                                          contents=prompt)
    return {"answer": r.text or "(no answer)"}


class LiveTriageRequest(BaseModel):
    txn_id: int


@app.post("/api/live-triage")
async def api_live_triage(req: LiveTriageRequest) -> dict:
    """Run the real pipeline, then refresh that case in the workbench cache."""
    try:
        await orchestrator.triage_alert(req.txn_id)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    cases = wb.refresh_case(req.txn_id)
    for c in cases:
        c["humanLog"] = wb.human_log(int(c["id"]))
    return {"cases": cases}
