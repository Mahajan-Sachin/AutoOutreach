import os
import json
import urllib.parse
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Depends
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
from tools import discover_startups_by_region
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
    title="Autonomous Startup Discovery & Cold Outreach Platform",
    version="1.0.0"
)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

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
def discover_startups():
    """Discover region-partitioned US/YC, European, and Asian/Middle-East tech startups."""
    raw_regions = discover_startups_by_region()
    
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
    if not clean_domain and req.company_name:
        clean_domain = req.company_name.lower().replace(" ", "") + ".com"
        
    company_name = req.company_name or clean_domain.split(".")[0].capitalize()
    
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
        r_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
