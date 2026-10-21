import os
import time
import json
import urllib.parse
import io
import csv
import uuid
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from fastapi.staticfiles import StaticFiles
from database import (
    init_db,
    is_domain_cached, 
    get_pending_outreach, 
    get_all_history, 
    update_outreach_status,
    delete_outreach_draft,
    save_company
)
from tools import (
    discover_startups_by_region,
    enrich_companies_batch,
    enrich_single_company,
    resolve_company_domain
)
from graph import outreach_graph

try:
    from backend.auth import create_access_token, verify_token, get_current_admin
except ImportError:
    from auth import create_access_token, verify_token, get_current_admin

try:
    from backend.rate_limiter import check_rate_limit
except ImportError:
    from rate_limiter import check_rate_limit

app = FastAPI(
    title="AutoOutreach: AI Venture & Founder Outreach",
    version="1.0.0"
)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Performance timing middleware: benchmarks endpoint latency via time.perf_counter() and injects X-Process-Time header."""
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = time.perf_counter() - start_time
    response.headers["X-Process-Time"] = f"{process_time:.4f}s"
    return response

# Enable CORS for Chrome Extension & Web Dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Dashboard static frontend files
dashboard_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dashboard")
if os.path.exists(dashboard_path):
    app.mount("/dashboard", StaticFiles(directory=dashboard_path, html=True), name="dashboard")


class OutreachRequest(BaseModel):
    domain: Optional[str] = ""
    company_name: Optional[str] = None
    region: Optional[str] = "Global"
    mode: Optional[str] = "company"  # "person" or "company"
    person_name: Optional[str] = None
    person_title: Optional[str] = None
    profile_url: Optional[str] = None
    force_refresh: Optional[bool] = False
    run_async: Optional[bool] = True  # Async background task flag

class ApproveRequest(BaseModel):
    draft_id: int
    subject: Optional[str] = None
    body: Optional[str] = None
    action: str = "approve"  # approve or reject

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/auth/login")
def login(req: LoginRequest):
    """Stateless JWT login endpoint returning HMAC-signed token with user claims."""
    if req.username == "sachin" and req.password == "sachin123":
        token = create_access_token({"sub": "sachin", "role": "admin"})
        return {
            "access_token": token,
            "token_type": "bearer",
            "username": "sachin",
            "role": "admin"
        }
    raise HTTPException(status_code=401, detail="Invalid username or password.")

@app.get("/api/auth/verify")
def verify_session(user: dict = Depends(verify_token)):
    """Verifies active JWT bearer token validity."""
    return {"status": "AUTHENTICATED", "user": user}

def run_async_outreach_job(task_id: str, initial_state: Dict[str, Any]):
    """Background worker function executing LangGraph outreach graph asynchronously."""
    import time
    import redis
    
    r_client = None
    try:
        r_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
    except Exception as e:
        print(f"[Async Worker Redis Error]: {e}")

    if r_client:
        r_client.set(f"task:{task_id}", json.dumps({"status": "RUNNING", "domain": initial_state.get("domain")}), ex=3600)

    try:
        final_state = outreach_graph.invoke(initial_state)
        result_payload = {
            "status": final_state.get("status", "COMPLETED"),
            "domain": initial_state.get("domain"),
            "is_cse_relevant": final_state.get("is_cse_relevant", True),
            "relevance_reason": final_state.get("relevance_reason", ""),
            "contacts_found": len(final_state.get("contacts", [])),
            "pitches_generated": len(final_state.get("pitches", []))
        }
        if r_client:
            r_client.set(f"task:{task_id}", json.dumps(result_payload), ex=3600)
        print(f"[Async Task Worker] Completed task '{task_id}' for domain '{initial_state.get('domain')}'.")
    except Exception as e:
        print(f"[Async Task Worker Error] Task '{task_id}' failed: {e}")
        if r_client:
            r_client.set(f"task:{task_id}", json.dumps({"status": "FAILED", "error": str(e)}), ex=3600)

@app.get("/")
def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/dashboard/")

@app.get("/api/health")
def health_check():
    return {"status": "online", "message": "Outreach Engine Ready"}

@app.get("/api/discover")
async def discover_startups(admin: dict = Depends(get_current_admin)):
    """Discover region-partitioned US/YC, European, and Asian/Middle-East tech startups."""
    raw_regions = await discover_startups_by_region()
    
    processed_regions = {}
    total_found = 0
    
    for reg_key, startup_list in raw_regions.items():
        processed_list = []
        for s in startup_list:
            domain = s["domain"]
            cached = is_domain_cached(domain)
            processed_list.append({
                **s,
                "is_cached": cached is not None,
                "cached_info": cached
            })
            total_found += 1
        processed_regions[reg_key] = processed_list
        
    return {
        "total": total_found,
        "regions": processed_regions
    }

@app.post("/api/outreach", status_code=202)
def process_outreach(req: OutreachRequest, background_tasks: BackgroundTasks, admin: dict = Depends(get_current_admin)):
    """
    Triggers LangGraph outreach pipeline asynchronously (Producer-Consumer Pattern).
    Returns HTTP 202 Accepted immediately with a task_id for non-blocking execution.
    """
    import time
    import redis

    # 1. Enforce Redis Rate Limit (10 requests per 60s window)
    check_rate_limit(client_id="outreach_api", limit=10, window_seconds=60)
    clean_domain = (req.domain or "").lower().replace("https://", "").replace("http://", "").split("/")[0].replace("www.", "")
    
    # Strip YC tags, parentheses, and subtitle noise (e.g. 'OpenHack (YC F26)' -> 'OpenHack')
    import re
    clean_company = re.sub(r'\s*\([^\)]*\)', '', req.company_name or '').strip()
    clean_company = re.sub(r'[\·\|\-].*$', '', clean_company).strip()

    if not clean_domain and clean_company:
        clean_domain = resolve_company_domain(clean_company)
    elif not clean_domain:
        clean_domain = "company.com"
        
    company_name = clean_company or clean_domain.split(".")[0].capitalize()

    
    # O(1) Cache Check for company mode (unless force_refresh is requested)
    if req.mode != "person" and not req.force_refresh:
        cached = is_domain_cached(clean_domain)
        if cached:
            return {
                "status": "CACHED",
                "message": f"Company {clean_domain} was already scanned/processed!",
                "company": cached
            }
        
    initial_state = {
        "mode": req.mode or "company",
        "domain": clean_domain,
        "company_name": company_name,
        "person_name": req.person_name or "",
        "person_title": req.person_title or "",
        "profile_url": req.profile_url or "",
        "region": req.region or "Global",
        "company_text": "",
        "is_cse_relevant": True,
        "relevance_reason": "",
        "company_id": None,
        "contacts": [],
        "pitches": [],
        "status": "PROCESSING"
    }

    # If run_async is False (e.g. for CLI testing), run synchronously
    if not req.run_async:
        final_state = outreach_graph.invoke(initial_state)
        return {
            "status": final_state.get("status", "COMPLETED"),
            "is_cse_relevant": final_state.get("is_cse_relevant", True),
            "relevance_reason": final_state.get("relevance_reason", ""),
            "contacts": final_state.get("contacts", []),
            "pitches": final_state.get("pitches", [])
        }
    
    # Async Task Queue Decoupling (HTTP 202 Producer Pattern)
    task_id = f"{clean_domain}_{int(time.time())}"
    redis_key = f"task:{task_id}"
    try:
        r_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
        r_client.set(redis_key, json.dumps({"status": "QUEUED", "domain": clean_domain}), ex=3600)
    except Exception as e:
        print(f"[Async Redis Store Error]: {e}")
        
    background_tasks.add_task(run_async_outreach_job, task_id, initial_state)
    
    return {
        "status": "QUEUED",
        "task_id": task_id,
        "message": "Outreach pipeline triggered in background task queue.",
        "status_url": f"/api/task/{task_id}"
    }

@app.get("/api/task/{task_id}")
def get_task_status(task_id: str):
    """Queries real-time async task execution status from Redis Task Store."""
    import redis
    try:
        r_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
        clean_key = task_id if task_id.startswith("task:") else f"task:{task_id}"
        task_data = r_client.get(clean_key)
        if task_data:
            if isinstance(task_data, str):
                return json.loads(task_data)
            return task_data
        return {"status": "NOT_FOUND", "task_id": task_id, "message": "Task ID not found or expired."}
    except Exception as e:
        print(f"[Task Status Error]: {e}")
        return {"status": "ERROR", "task_id": task_id, "message": f"Task Store Error: {str(e)}"}

@app.get("/api/pending")
def get_pending(admin: dict = Depends(get_current_admin)):
    """Fetch pending Human-In-The-Loop outreach drafts."""
    drafts = get_pending_outreach()
    
    # Generate Gmail Web Compose URL for 1-click compose
    for d in drafts:
        email = d.get("contact_email") or ""
        subject = d.get("pitch_subject") or ""
        body = d.get("pitch_body") or ""
        
        gmail_url = f"https://mail.google.com/mail/?view=cm&fs=1&to={urllib.parse.quote(email)}&su={urllib.parse.quote(subject)}&body={urllib.parse.quote(body)}"
        mailto_url = f"mailto:{urllib.parse.quote(email)}?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(body)}"
        
        d["gmail_compose_url"] = gmail_url
        d["mailto_url"] = mailto_url
        
    return {"pending_drafts": drafts}

@app.post("/api/approve")
def approve_draft(req: ApproveRequest, admin: dict = Depends(get_current_admin)):
    """Approve or Reject an outreach draft and update SQLite DB."""
    if req.action == "reject":
        update_outreach_status(req.draft_id, "REJECTED")
        return {"status": "REJECTED", "draft_id": req.draft_id}
        
    update_outreach_status(req.draft_id, "APPROVED")
    return {"status": "APPROVED", "draft_id": req.draft_id}

@app.delete("/api/draft/{draft_id}")
def delete_draft(draft_id: int, admin: dict = Depends(get_current_admin)):
    """Delete a draft from SQLite DB."""
    delete_outreach_draft(draft_id)
    return {"status": "DELETED", "draft_id": draft_id}

@app.on_event("startup")
def startup_event():
    """Initialize database tables and seed admin user on startup."""
    init_db()
    print("[Main Startup] Database initialized and admin user verified.")

@app.get("/api/history")
def get_history(admin: dict = Depends(get_current_admin)):
    """Fetch all processed outreach history."""
    history = get_all_history()
    return {"history": history}

ENRICHED_CSV_STORE: Dict[str, Dict[str, Any]] = {}

@app.post("/api/enrich/csv")
async def enrich_csv_leads(
    file: UploadFile = File(...),
    admin: dict = Depends(get_current_admin)
):
    """
    Parses an uploaded CSV file, auto-detects company/domain columns,
    and enriches decision-maker emails via Hunter.io, Apollo, GitHub, and AI waterfall.
    """
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported.")

    raw_bytes = await file.read()
    text = ""
    for enc in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
        try:
            text = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    if not text:
        raise HTTPException(status_code=400, detail="Could not read or decode the CSV file.")

    f = io.StringIO(text)
    reader = csv.reader(f)
    rows = [r for r in reader if any(field.strip() for field in r)]
    if not rows:
        raise HTTPException(status_code=400, detail="CSV file is empty.")

    header = [h.strip() for h in rows[0]]
    header_lower = [h.lower() for h in header]

    company_col_idx = -1
    domain_col_idx = -1

    company_keywords = ["company", "company name", "company_name", "organization", "org", "business", "account", "startup"]
    domain_keywords = ["domain", "website", "url", "web", "company domain", "company_domain", "site"]

    for idx, col in enumerate(header_lower):
        if company_col_idx == -1 and any(k == col or k in col for k in company_keywords):
            company_col_idx = idx
        if domain_col_idx == -1 and any(k == col or k in col for k in domain_keywords):
            domain_col_idx = idx

    has_header = company_col_idx != -1 or domain_col_idx != -1
    if not has_header:
        company_col_idx = 0
        data_rows = rows
    else:
        if company_col_idx == -1 and domain_col_idx != -1:
            company_col_idx = domain_col_idx
        elif company_col_idx == -1:
            company_col_idx = 0
        data_rows = rows[1:]

    companies_to_enrich = []
    seen = set()
    for r in data_rows[:60]:
        if not r or len(r) <= company_col_idx:
            continue
        c_name = r[company_col_idx].strip()
        c_dom = r[domain_col_idx].strip() if (domain_col_idx != -1 and len(r) > domain_col_idx) else ""
        key = (c_name.lower(), c_dom.lower())
        if (c_name or c_dom) and key not in seen:
            seen.add(key)
            companies_to_enrich.append({"company_name": c_name, "domain": c_dom})

    if not companies_to_enrich:
        raise HTTPException(status_code=400, detail="No valid companies found in the CSV.")

    enriched_results = await enrich_companies_batch(companies_to_enrich)

    output_io = io.StringIO()
    writer = csv.writer(output_io)
    writer.writerow([
        "Company Name",
        "Domain",
        "Decision Maker",
        "Job Title",
        "Verified Email",
        "Confidence Score",
        "Data Source",
        "Status"
    ])
    for item in enriched_results:
        writer.writerow([
            item.get("company_name", ""),
            item.get("domain", ""),
            item.get("lead_name", ""),
            item.get("lead_title", ""),
            item.get("lead_email", ""),
            item.get("confidence", ""),
            item.get("source", ""),
            item.get("status", "")
        ])

    csv_data = output_io.getvalue()
    download_id = f"enrich_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    ENRICHED_CSV_STORE[download_id] = {
        "csv_data": csv_data,
        "filename": f"enriched_leads_{int(time.time())}.csv",
        "created_at": time.time()
    }

    return {
        "status": "SUCCESS",
        "download_id": download_id,
        "total": len(enriched_results),
        "found_count": len([r for r in enriched_results if r.get("lead_email")]),
        "results": enriched_results
    }

@app.get("/api/enrich/download/{download_id}")
def download_enriched_csv(download_id: str):
    """Downloads the generated enriched CSV file."""
    record = ENRICHED_CSV_STORE.get(download_id)
    if not record:
        raise HTTPException(status_code=404, detail="Download file expired or not found.")
    
    from fastapi.responses import Response
    return Response(
        content=record["csv_data"],
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{record["filename"]}"'
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
