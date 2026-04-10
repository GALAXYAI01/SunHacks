import os
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from analyzer import GitHubAnalyzer
from ai_reporter import generate_ceo_report

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="Predictive Engineering Intelligence Platform",
    version="2.0.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

executor = ThreadPoolExecutor(max_workers=4)
jobs: Dict[str, Dict[str, Any]] = {}


class AnalyzeRequest(BaseModel):
    repo_url: str
    github_token: str        # USER provides their own token — platform never stores one
    include_ai_report: bool = True
    slack_webhook_url: Optional[str] = None
    alert_threshold: int = 60


class MultiRepoRequest(BaseModel):
    repo_urls: List[str]
    github_token: str


class JobStatus(BaseModel):
    job_id: str
    status: str
    progress_pct: int
    message: str
    result: Optional[Dict] = None
    error: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


def _send_slack_alert(webhook_url, repo, health_score, health_label, cost):
    color = "#E24B4A" if health_label in ("CRITICAL","POOR") else "#EF9F27" if health_label=="FAIR" else "#639922"
    try:
        import requests as req
        req.post(webhook_url, json={"attachments": [{"color": color,
            "title": f"[PredictiveEng] Health Alert: {repo}",
            "fields": [{"title":"Health Score","value":f"{health_score}/100 ({health_label})","short":True},
                       {"title":"Cost of Inaction","value":f"${cost:,}","short":True}]}]}, timeout=5)
    except Exception:
        pass


def run_analysis(job_id, repo_url, github_token, include_ai, slack_webhook=None, alert_threshold=60):
    try:
        jobs[job_id].update({"status":"running","progress_pct":10,"message":"Cloning repository with your credentials..."})
        # Token is 100% from user request — no os.getenv fallback intentionally
        analyzer = GitHubAnalyzer(github_token=github_token)
        jobs[job_id].update({"progress_pct":20,"message":"Analyzing commits, complexity, burnout, cascade..."})
        raw_data = analyzer.run_full_analysis(repo_url)
        jobs[job_id].update({"progress_pct":80,"message":"Generating CEO brief via LangChain + Claude..."})
        ai_report = generate_ceo_report(raw_data) if include_ai else {}
        jobs[job_id].update({
            "status":"completed","progress_pct":100,"message":"Analysis complete.",
            "completed_at":datetime.utcnow().isoformat()+"Z",
            "result":{**raw_data,"ai_ceo_report":ai_report},
        })
        if slack_webhook:
            hs = raw_data["health_scores"]
            if hs["overall_health_score"] < alert_threshold:
                _send_slack_alert(slack_webhook, raw_data["repo_info"]["full_name"],
                                  hs["overall_health_score"], hs["health_label"],
                                  hs["total_cost_of_inaction_usd"])
    except Exception as e:
        jobs[job_id].update({"status":"failed","message":"Analysis failed.",
                              "error":str(e),"completed_at":datetime.utcnow().isoformat()+"Z"})


@app.get("/", response_class=HTMLResponse)
def root():
    html_file = BASE_DIR / "index.html"
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text(encoding="utf-8"), status_code=200)
    return HTMLResponse(content="<h1>PredictiveEng API is running. Place index.html in the project root.</h1>", status_code=200)


@app.get("/api/status")
def api_status():
    return {"service":"Predictive Engineering Intelligence Platform","version":"2.0.0","status":"operational",
            "privacy":"Your GitHub token is used only for this request and is never stored on our servers."}


@app.post("/api/analyze", response_model=JobStatus, status_code=202)
def start_analysis(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    if "github.com" not in request.repo_url and "gitlab.com" not in request.repo_url:
        raise HTTPException(status_code=400, detail="Only GitHub/GitLab URLs supported.")
    if not request.github_token or len(request.github_token) < 10:
        raise HTTPException(status_code=400,
            detail="Provide your own GitHub Personal Access Token (repo scope). "
                   "Generate at https://github.com/settings/tokens — it is never stored.")
    job_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()+"Z"
    jobs[job_id] = {"job_id":job_id,"status":"queued","progress_pct":0,
                    "message":"Job queued.","result":None,"error":None,
                    "created_at":now,"completed_at":None}
    background_tasks.add_task(run_analysis, job_id, request.repo_url, request.github_token,
                               request.include_ai_report, request.slack_webhook_url, request.alert_threshold)
    return jobs[job_id]


@app.post("/api/analyze/portfolio", status_code=202)
def start_portfolio(request: MultiRepoRequest, background_tasks: BackgroundTasks):
    if not request.github_token or len(request.github_token) < 10:
        raise HTTPException(status_code=400, detail="Valid GitHub token required.")
    now = datetime.utcnow().isoformat()+"Z"
    job_ids = []
    for url in request.repo_urls[:10]:
        if "github.com" not in url and "gitlab.com" not in url:
            continue
        jid = str(uuid.uuid4())
        jobs[jid] = {"job_id":jid,"status":"queued","progress_pct":0,"message":"Queued.",
                     "result":None,"error":None,"created_at":now,"completed_at":None}
        background_tasks.add_task(run_analysis, jid, url, request.github_token, True)
        job_ids.append(jid)
    return {"job_ids":job_ids,"repo_count":len(job_ids),"created_at":now}


@app.get("/api/portfolio/summary")
def get_portfolio_summary(job_ids: str):
    summaries = []
    for jid in job_ids.split(","):
        if jid not in jobs: continue
        job = jobs[jid]
        if job["status"]=="completed" and job["result"]:
            r = job["result"]
            summaries.append({"job_id":jid,"repo":r["repo_info"]["full_name"],
                "overall_health_score":r["health_scores"]["overall_health_score"],
                "health_label":r["health_scores"]["health_label"],
                "security_label":r.get("security",{}).get("security_label","UNKNOWN"),
                "bus_number":r["commit_analysis"].get("bus_factor",{}).get("bus_number","N/A"),
                "test_coverage_pct":r.get("test_coverage",{}).get("test_to_source_ratio_pct",0),
                "total_cost_of_inaction_usd":r["health_scores"]["total_cost_of_inaction_usd"],
                "status":"completed"})
        else:
            summaries.append({"job_id":jid,"status":job["status"],"progress_pct":job["progress_pct"]})
    summaries.sort(key=lambda x: x.get("overall_health_score",999))
    return {"repos":summaries,"total":len(summaries),
            "completed":sum(1 for s in summaries if s.get("status")=="completed")}


@app.get("/api/jobs/{job_id}", response_model=JobStatus)
def get_job_status(job_id: str):
    if job_id not in jobs: raise HTTPException(status_code=404, detail="Job not found.")
    return jobs[job_id]


@app.get("/api/jobs/{job_id}/health")
def get_health(job_id: str):
    r = _done(job_id)["result"]
    return {"repo":r["repo_info"]["full_name"],"analyzed_at":r["analyzed_at"],
            "health_scores":r["health_scores"],
            "ai_summary":r.get("ai_ceo_report",{}).get("executive_summary"),
            "business_risk_level":r.get("ai_ceo_report",{}).get("business_risk_level"),
            "predicted_incident_probability_30d_pct":r.get("ai_ceo_report",{}).get("predicted_incident_probability_30d_pct")}


@app.get("/api/jobs/{job_id}/security")
def get_security(job_id: str):
    r = _done(job_id)["result"]
    return {"repo":r["repo_info"]["full_name"],"security":r.get("security",{}),"dependency_risk":r.get("dependency_risk",{})}


@app.get("/api/jobs/{job_id}/bus-factor")
def get_bus_factor(job_id: str):
    r = _done(job_id)["result"]
    return {"repo":r["repo_info"]["full_name"],
            "bus_factor":r["commit_analysis"].get("bus_factor",{}),
            "top_contributors":r["commit_analysis"].get("top_contributors",[])}


@app.get("/api/jobs/{job_id}/test-coverage")
def get_test_coverage(job_id: str):
    r = _done(job_id)["result"]
    return {"repo":r["repo_info"]["full_name"],"test_coverage":r.get("test_coverage",{})}


@app.get("/api/jobs/{job_id}/ceo-brief")
def get_ceo_brief(job_id: str):
    r = _done(job_id)["result"]
    return {"repo":r["repo_info"]["full_name"],"ceo_brief":r.get("ai_ceo_report",{})}


@app.get("/api/jobs/{job_id}/components")
def get_components(job_id: str):
    r = _done(job_id)["result"]
    h = r["health_scores"]
    return {"repo":r["repo_info"]["full_name"],"overall_health_score":h["overall_health_score"],
            "health_label":h["health_label"],"total_cost_of_inaction_usd":h["total_cost_of_inaction_usd"],
            "components":h["component_predictions"],"immediate_action_required":h["immediate_action_required"]}


@app.get("/api/jobs/{job_id}/burnout")
def get_burnout(job_id: str):
    r = _done(job_id)["result"]
    return {"repo":r["repo_info"]["full_name"],"burnout":r.get("burnout",{})}


@app.get("/api/jobs/{job_id}/cascade")
def get_cascade(job_id: str):
    r = _done(job_id)["result"]
    return {"repo":r["repo_info"]["full_name"],"cascade_risk":r.get("cascade_risk",{})}


@app.get("/api/jobs/{job_id}/debt")
def get_debt(job_id: str):
    r = _done(job_id)["result"]
    return {"repo":r["repo_info"]["full_name"],"technical_debt":r.get("technical_debt",{})}


@app.get("/api/jobs/{job_id}/deployment")
def get_deployment(job_id: str):
    r = _done(job_id)["result"]
    return {"repo":r["repo_info"]["full_name"],"deployment_readiness":r.get("deployment_readiness",{})}


@app.get("/api/jobs")
def list_jobs():
    return [{"job_id":j["job_id"],"status":j["status"],"progress_pct":j["progress_pct"],
             "created_at":j["created_at"],"completed_at":j.get("completed_at")} for j in jobs.values()]


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    if job_id not in jobs: raise HTTPException(status_code=404, detail="Job not found.")
    del jobs[job_id]
    return {"deleted":job_id}


def _done(job_id: str) -> dict:
    if job_id not in jobs: raise HTTPException(status_code=404, detail="Job not found.")
    job = jobs[job_id]
    if job["status"] != "completed":
        raise HTTPException(status_code=425, detail=f"Job is {job['status']}. Wait until completed.")
    return job


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
