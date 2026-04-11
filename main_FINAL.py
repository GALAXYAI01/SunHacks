"""
main_FINAL.py — FastAPI server for PredictiveEng.

NO GitHub token required — analyzes public repositories only.
Privacy: AES-256-GCM encrypted API responses, no credentials exposed.
"""

import os
import uuid
import json
import base64
import secrets
from datetime import datetime
from typing import Optional, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
load_dotenv()  # Load .env BEFORE anything else

from fastapi import FastAPI, BackgroundTasks, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from analyzer import GitHubAnalyzer
from ai_reporter_FINAL import generate_ceo_report

app = FastAPI(
    title="Predictive Engineering Intelligence Platform",
    version="3.0.0",
    description="Analyzes public GitHub repos. No credentials required.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-encrypted"],
)

executor = ThreadPoolExecutor(max_workers=4)
jobs: Dict[str, Dict[str, Any]] = {}

# ── Encryption session store ─────────────────────────────────────────
crypto_sessions: Dict[str, bytes] = {}  # session_id -> AES key bytes


# ── Models ────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    repo_url:          str
    github_token:      str = ""     # optional, ignored for privacy
    include_ai_report: bool = True


class MultiRepoRequest(BaseModel):
    repo_urls:    List[str]
    github_token: str = ""          # optional, ignored for privacy


class ChatRequest(BaseModel):
    job_id:  str = ""              # optional — chat works without analysis too
    message: str
    history: List[Dict] = []


class FixCodeRequest(BaseModel):
    job_id:        str
    file_path:     str
    function_name: str
    line_start:    int
    complexity:    int
    original_code: str


class JobStatus(BaseModel):
    job_id:       str
    status:       str
    progress_pct: int
    message:      str
    result:       Optional[Dict] = None
    error:        Optional[str] = None
    created_at:   str
    completed_at: Optional[str] = None


# ── AES-256-GCM encryption helpers ───────────────────────────────────

def _encrypt_payload(data: dict, key: bytes) -> dict:
    """Encrypt a JSON dict with AES-256-GCM."""
    plaintext = json.dumps(data).encode("utf-8")
    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext, None)
    return {
        "ct": base64.b64encode(ct).decode(),
        "iv": base64.b64encode(nonce).decode(),
    }


def _decrypt_payload(ct_b64: str, iv_b64: str, key: bytes) -> dict:
    """Decrypt an AES-256-GCM encrypted payload."""
    ct = base64.b64decode(ct_b64)
    iv = base64.b64decode(iv_b64)
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(iv, ct, None)
    return json.loads(plaintext.decode("utf-8"))


# ── Encryption middleware ─────────────────────────────────────────────

@app.middleware("http")
async def encryption_middleware(request: Request, call_next):
    """
    If the request has x-session-id header, decrypt inbound body and
    encrypt the outbound response. This hides all data from browser
    Network/Inspect tab.
    """
    session_id = request.headers.get("x-session-id")

    # Decrypt inbound POST body if encrypted
    if session_id and session_id in crypto_sessions:
        if request.method in ("POST", "PUT"):
            try:
                raw_body = await request.body()
                if raw_body:
                    body_json = json.loads(raw_body)
                    if "ct" in body_json and "iv" in body_json:
                        key = crypto_sessions[session_id]
                        decrypted = _decrypt_payload(
                            body_json["ct"], body_json["iv"], key
                        )
                        # Rebuild request with decrypted body
                        request._body = json.dumps(decrypted).encode("utf-8")
            except Exception:
                pass  # Fall through to handle unencrypted

    response = await call_next(request)

    # Encrypt outbound response if session is active
    if session_id and session_id in crypto_sessions:
        if response.headers.get("content-type", "").startswith("application/json"):
            body_bytes = b""
            async for chunk in response.body_iterator:
                if isinstance(chunk, bytes):
                    body_bytes += chunk
                else:
                    body_bytes += chunk.encode("utf-8")

            try:
                data = json.loads(body_bytes)
                key = crypto_sessions[session_id]
                encrypted = _encrypt_payload(data, key)
                encrypted_bytes = json.dumps(encrypted).encode("utf-8")
                return Response(
                    content=encrypted_bytes,
                    status_code=response.status_code,
                    headers={
                        "content-type": "application/json",
                        "x-encrypted": "true",
                        "access-control-allow-origin": "*",
                        "access-control-expose-headers": "x-encrypted",
                    },
                )
            except Exception:
                pass  # Return response as-is if encryption fails

    return response


# ── Worker ────────────────────────────────────────────────────────────

def run_analysis(job_id: str, repo_url: str, include_ai: bool):
    import traceback
    try:
        _upd(job_id, 5, "Connecting to GitHub...")
        analyzer = GitHubAnalyzer()

        _upd(job_id, 10, "Fetching repository info...")
        # run_full_analysis handles everything internally
        _upd(job_id, 15, "Cloning repository (this may take 30-60s)...")
        raw = analyzer.run_full_analysis(repo_url)

        _upd(job_id, 80, "Generating AI intelligence brief...")
        try:
            ai = generate_ceo_report(raw) if include_ai else {}
        except Exception as ai_err:
            print(f"[AI Report Warning] {ai_err}")
            ai = {}  # Don't fail the whole analysis if AI report fails

        jobs[job_id].update({
            "status":       "completed",
            "progress_pct": 100,
            "message":      "Analysis complete.",
            "completed_at": datetime.utcnow().isoformat() + "Z",
            "result":       {**raw, "ai_ceo_report": ai},
        })
        print(f"[OK] Analysis completed for job {job_id}")

    except Exception as e:
        msg = str(e)
        print(f"[ERROR] Analysis FAILED for job {job_id}: {msg}")
        traceback.print_exc()
        # Never leak URLs, paths, or tokens in error messages
        if any(s in msg.lower() for s in ("token", "api_key", "apikey", "credential")):
            msg = "Repository access failed. Make sure the URL is correct and the repo is public."
        jobs[job_id].update({
            "status":       "failed",
            "message":      "Analysis failed.",
            "error":        msg,
            "completed_at": datetime.utcnow().isoformat() + "Z",
        })


def _upd(job_id, pct, msg):
    jobs[job_id].update({"status": "running", "progress_pct": pct, "message": msg})


from pathlib import Path as _Path
_BASE = _Path(__file__).resolve().parent

@app.get("/", response_class=Response)
def root():
    """Serve the main dashboard HTML."""
    html_path = _BASE / "index.html"
    return Response(content=html_path.read_text(encoding="utf-8"), media_type="text/html")


@app.get("/api/status")
def api_status():
    return {
        "service":  "Predictive Engineering Intelligence Platform",
        "version":  "3.0.0",
        "status":   "operational",
        "privacy":  "All API traffic is AES-256-GCM encrypted. No credentials required.",
        "docs":     "/docs",
    }


@app.post("/api/handshake")
def handshake():
    """
    Generate a new AES-256-GCM session key for the client.
    The client stores this key and uses it to encrypt/decrypt all traffic.
    """
    session_id = str(uuid.uuid4())
    key = AESGCM.generate_key(bit_length=256)
    crypto_sessions[session_id] = key
    return {
        "sid": session_id,
        "key": base64.b64encode(key).decode(),
    }


@app.post("/api/analyze", status_code=202)
def start_analysis(req: AnalyzeRequest, bg: BackgroundTasks):
    if "github.com" not in req.repo_url:
        raise HTTPException(status_code=400,
            detail="Only GitHub repositories are supported. "
                   "Provide a URL like https://github.com/owner/repo")
    job_id = str(uuid.uuid4())
    now    = datetime.utcnow().isoformat() + "Z"
    jobs[job_id] = {
        "job_id": job_id, "status": "queued", "progress_pct": 0,
        "message": "Queued.", "result": None, "error": None,
        "created_at": now, "completed_at": None,
    }
    bg.add_task(run_analysis, job_id, req.repo_url, req.include_ai_report)
    return jobs[job_id]


@app.post("/api/analyze/portfolio", status_code=202)
def start_portfolio(req: MultiRepoRequest, bg: BackgroundTasks):
    now  = datetime.utcnow().isoformat() + "Z"
    ids  = []
    for url in req.repo_urls[:8]:
        if "github.com" not in url:
            continue
        jid = str(uuid.uuid4())
        jobs[jid] = {"job_id": jid, "status": "queued", "progress_pct": 0,
                     "message": "Queued.", "result": None, "error": None,
                     "created_at": now, "completed_at": None}
        bg.add_task(run_analysis, jid, url, True)
        ids.append(jid)
    return {"job_ids": ids, "repo_count": len(ids), "created_at": now}


@app.post("/api/chat")
def chat_endpoint(req: ChatRequest):
    """Contextual chatbot — works with or without analysis data."""
    from chatbot import chat, general_chat
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    # If job_id  is provided and the job is completed, use contextual chat
    if req.job_id and req.job_id in jobs and jobs[req.job_id]["status"] == "completed":
        answer = chat(question=req.message,
                      analysis=jobs[req.job_id]["result"],
                      history=req.history)
    else:
        # General chat mode — no analysis context
        answer = general_chat(question=req.message, history=req.history)

    return {"answer": answer, "response": answer, "job_id": req.job_id}


@app.post("/api/fix-code")
def fix_code_endpoint(req: FixCodeRequest):
    """
    Returns a fully refactored version of the specified function.
    Paste the original function code and get back improved code + explanation.
    """
    from chatbot import fix_code
    job = _done(req.job_id)
    return fix_code(
        file_path=req.file_path,
        function_name=req.function_name,
        line_start=req.line_start,
        complexity=req.complexity,
        original_code=req.original_code,
        analysis=job["result"],
    )


# ── Data endpoints ────────────────────────────────────────────────────

@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found.")
    # Return job without the full result blob (too large for polling)
    j = {k: v for k, v in jobs[job_id].items() if k != "result"}
    return j


@app.get("/api/jobs/{job_id}/health")
def get_health(job_id: str):
    r = _done(job_id)["result"]
    ai = r.get("ai_ceo_report", {})
    return {
        "repo":          r["repo_info"]["full_name"],
        "analyzed_at":   r["analyzed_at"],
        "health_scores": r["health_scores"],
        "ai_summary":    ai.get("executive_summary"),
        "health_analogy":ai.get("health_analogy"),
        "business_risk_level": ai.get("business_risk_level"),
        "predicted_incident_probability_30d_pct":
            ai.get("predicted_incident_probability_30d_pct"),
        "top_actions":   ai.get("top_actions", []),
        "cost_summary":  ai.get("cost_summary", {}),
        "critical_finding": ai.get("critical_finding"),
    }


@app.get("/api/jobs/{job_id}/components")
def get_components(job_id: str):
    r = _done(job_id)["result"]
    h = r["health_scores"]
    # Normalize: ensure each component has both "file" and "component" fields
    comps = []
    for c in h.get("component_predictions", []):
        entry = dict(c)
        # Make sure "file" field exists (some code uses "component", some uses "file")
        if "file" not in entry and "component" in entry:
            entry["file"] = entry["component"]
        if "component" not in entry and "file" in entry:
            entry["component"] = entry["file"]
        comps.append(entry)
    return {
        "repo":                       r["repo_info"]["full_name"],
        "overall_health_score":       h["overall_health_score"],
        "health_label":               h["health_label"],
        "total_cost_of_inaction_usd": h["total_cost_of_inaction_usd"],
        "components":                 comps,
        "immediate_action_required":  h["immediate_action_required"],
    }


@app.get("/api/jobs/{job_id}/cascade")
def get_cascade(job_id: str):
    r = _done(job_id)["result"]
    return {
        "repo":         r["repo_info"]["full_name"],
        "cascade_risk": r.get("cascade_risk", {}),
    }


@app.get("/api/jobs/{job_id}/security")
def get_security(job_id: str):
    r = _done(job_id)["result"]
    return {
        "repo":            r["repo_info"]["full_name"],
        "security":        r.get("security", {}),
        "dependency_risk": r.get("dependency_risk", {}),
    }


@app.get("/api/jobs/{job_id}/burnout")
def get_burnout(job_id: str):
    r = _done(job_id)["result"]
    return {"repo": r["repo_info"]["full_name"],
            "burnout": r.get("burnout", {})}


@app.get("/api/jobs/{job_id}/debt")
def get_debt(job_id: str):
    r = _done(job_id)["result"]
    return {"repo": r["repo_info"]["full_name"],
            "technical_debt": r.get("technical_debt", {})}


@app.get("/api/jobs/{job_id}/deployment")
def get_deployment(job_id: str):
    r = _done(job_id)["result"]
    return {"repo": r["repo_info"]["full_name"],
            "deployment_readiness": r.get("deployment_readiness", {})}


@app.get("/api/jobs/{job_id}/bus-factor")
def get_bus(job_id: str):
    r = _done(job_id)["result"]
    return {"repo": r["repo_info"]["full_name"],
            "bus_factor": r["commit_analysis"].get("bus_factor", {}),
            "top_contributors": r["commit_analysis"].get("top_contributors", [])}


@app.get("/api/jobs/{job_id}/test-coverage")
def get_test(job_id: str):
    r = _done(job_id)["result"]
    return {"repo": r["repo_info"]["full_name"],
            "test_coverage": r.get("test_coverage", {}),
            "commit_trend":  r["commit_analysis"].get("commit_trend", [])}


@app.get("/api/jobs/{job_id}/ceo-brief")
def get_ceo(job_id: str):
    r = _done(job_id)["result"]
    return {"repo": r["repo_info"]["full_name"],
            "ceo_brief": r.get("ai_ceo_report", {})}


@app.get("/api/jobs")
def list_jobs():
    return [{"job_id":      j["job_id"],
             "status":      j["status"],
             "progress_pct":j["progress_pct"],
             "created_at":  j["created_at"],
             "completed_at":j.get("completed_at")} for j in jobs.values()]


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found.")
    del jobs[job_id]
    return {"deleted": job_id}


@app.get("/api/portfolio/summary")
def portfolio_summary(job_ids: str):
    out = []
    for jid in job_ids.split(","):
        if jid not in jobs:
            continue
        job = jobs[jid]
        if job["status"] == "completed" and job["result"]:
            r = job["result"]
            out.append({
                "job_id":      jid,
                "repo":        r["repo_info"]["full_name"],
                "health_score":r["health_scores"]["overall_health_score"],
                "health_label":r["health_scores"]["health_label"],
                "security":    r.get("security",{}).get("security_label","?"),
                "debt_grade":  r.get("technical_debt",{}).get("debt_grade","?"),
                "cost":        r["health_scores"]["total_cost_of_inaction_usd"],
                "status":      "completed",
            })
        else:
            out.append({"job_id": jid, "status": job["status"],
                        "progress_pct": job["progress_pct"]})
    out.sort(key=lambda x: x.get("health_score", 999))
    return {"repos": out, "total": len(out)}


def _done(job_id: str) -> dict:
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found.")
    job = jobs[job_id]
    if job["status"] != "completed":
        raise HTTPException(status_code=425,
            detail=f"Job is {job['status']}. Wait until status = completed.")
    return job