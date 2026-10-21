import json
from typing import TypedDict, List, Dict, Any, Optional, Literal
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from database import is_domain_cached, save_company, save_contact, save_outreach_draft
from tools import GROQ_API_KEY, crawl_company_website, find_email_waterfall, find_person_email_waterfall

# Candidate Resume Context for High-Conversion Cold Outreach
CANDIDATE_RESUME_CONTEXT = """
Candidate Name: Sachin Mahajan
Role Target: AI/ML Engineer / Software Engineer Intern
Education: B.Tech CSE (AI/ML) at Lovely Professional University (CGPA: 7.75)
Key Highlights & Proof of Work:
1. Open Source Contributions:
   - TensorFlow (Google C++): Merged PR #116986 fixing complex sign float32 underflow with C++ std::abs/hypot; Approved PR #116947 fixing ELU/SELU numerical instability in Eigen kernels with C++ expm1(x).
   - Podman (Red Hat Go): Merged PR #29375 fixing Quadlet container storage auto-recovery logic in Go.
   - pandas (NumFOCUS): Merged PR #65413 fixing Categorical.map missing-key handling in pandas 3.1.
2. Live Shippable Projects & Systems:
   - Lead Intelligence & Executive Outreach Engine (AutoOutreach): Production cross-browser extension (Chrome & Edge) and FastAPI/LangGraph multi-agent backend executing domain scraping, Hunter.io/Groq executive email discovery, and 5-bullet high-conversion cold pitches.
   - Uncensored-Llama-1B (Weight Ablation & SFT): Fine-tuned Llama-3.2-1B with QLoRA on consumer hardware (4GB VRAM constraint) using Unsloth & Ablate Framework.
   - Phishing URL Detection: XGBoost model (58 features, 91.38% accuracy, 0.97 ROC-AUC) containerized with Docker, GitHub Actions CI/CD, and live Streamlit deployment.
3. Tech Stack: Python, C++, Golang, Data Structures & Algorithms, LangGraph, CrewAI, Groq API, ChromaDB, FastAPI, PostgreSQL, Docker, GitHub Actions CI/CD.
"""

class OutreachState(TypedDict):
    mode: str
    domain: str
    company_name: str
    person_name: str
    person_title: str
    profile_url: str
    region: str
    company_text: str
    is_cse_relevant: bool
    relevance_reason: str
    company_id: Optional[int]
    contacts: List[Dict[str, Any]]
    pitches: List[Dict[str, Any]]
    status: str

DEFAULT_PITCH_TEMPLATE = """Hi {first_name},

• B.Tech CSE student focused on AI/ML and production systems.
• Merged PRs in Google's TensorFlow, Red Hat's Podman, and pandas. Shipped production LLM applications.
• Saw your engineering work at {company_name} — think there's real overlap with what I'm building.
• Resume attached below — feel free to share with your team so they know what to test me on.
• So: don't believe the resume. Give me an assignment, see my work, then decide."""

from pydantic import BaseModel, Field

class PitchItem(BaseModel):
    role_target: str = Field(default="Decision Maker", description="Target role category or title")
    pitch_subject: str = Field(description="Impactful cold email subject line")
    pitch_body: str = Field(description="Exact 5-bullet personalized outreach pitch body")

# Initialize Groq LLM
llm = ChatGroq(
    groq_api_key=GROQ_API_KEY if GROQ_API_KEY else "dummy_key",
    model_name="llama-3.3-70b-versatile",
    temperature=0.3
)

def company_crawler_node(state: OutreachState) -> OutreachState:
    domain = state["domain"]
    print(f"[Graph] Crawling company: {domain}")
    text = crawl_company_website(domain) if domain else ""
    return {
        **state,
        "company_text": text
    }

def cse_relevance_evaluator_node(state: OutreachState) -> OutreachState:
    """All companies hiring or operating are treated as 100% valid targets for engineering outreach."""
    company_name = state.get("company_name", "Target Company")
    return {
        **state,
        "is_cse_relevant": True,
        "relevance_reason": f"{company_name} hires software, AI/ML, and engineering talent."
    }

def executive_discovery_node(state: OutreachState) -> OutreachState:
    domain = state["domain"]
    company_name = state["company_name"]
    mode = state.get("mode", "company")
    person_name = state.get("person_name", "")
    person_title = state.get("person_title", "")
    profile_url = state.get("profile_url", "")
    
    if mode == "person" and person_name:
        print(f"[Graph] Finding targeted email for: {person_name} ({person_title}) at {company_name}")
        contact = find_person_email_waterfall(domain, company_name, person_name, person_title, profile_url)
        contacts = [contact]
    else:
        print(f"[Graph] Finding decision makers for: {company_name}")
        contacts = find_email_waterfall(domain, company_name)
        
    return {
        **state,
        "contacts": contacts
    }

def role_specific_pitch_generator_node(state: OutreachState) -> OutreachState:
    company_name = state["company_name"]
    company_text = state["company_text"]
    mode = state.get("mode", "company")
    person_name = state.get("person_name", "")
    person_title = state.get("person_title", "")
    contacts = state.get("contacts", [])
    role_target = person_title or ("Specific Contact" if person_name else "Founder / Tech Lead")
    target_person_str = f"Specific Person: {person_name} ({role_target})" if person_name else "Decision Maker Team"
    print(f"[Graph] Generating tailored 5-bullet pitch for {target_person_str} at {company_name}...")
    
    first_name = person_name.split()[0] if person_name else "there"
    
    prompt = f"""
    You are writing an ultra-concise, high-converting 5-bullet cold outreach email for a top-tier student software engineer (Sachin Mahajan).

    CANDIDATE PROOF OF WORK:
    - B.Tech CSE student focused on AI/ML and production systems.
    - Merged PRs in Google's TensorFlow, Red Hat's Podman, and pandas. Shipped production LLM applications.
    
    TARGET INFORMATION:
    Company Name: {company_name}
    Target Person Name: {person_name or 'Hiring Lead'}
    Target Role/Title: {role_target}
    Company Description/Tech: {company_text[:1200]}
    
    CRITICAL FORMAT RULES:
    1. Subject Line: Must use impact over jargon (e.g. "Merged code in Google's TensorFlow & Red Hat's Podman" or "Quick 15-second note: AI/ML Engineering & OSS proof").
    2. Body Format: MUST BE EXACTLY 5 BULLET POINTS preceded by a short 1-line greeting ("Hi {first_name},"):
       - Bullet 1: Identity & focus ("• B.Tech CSE student focused on AI/ML and production systems.")
       - Bullet 2: Unassailable OSS proof of work ("• Merged PRs in Google's TensorFlow, Red Hat's Podman, and pandas. Shipped production LLM applications.")
       - Bullet 3: Specific product alignment with {company_name} ("• Saw your engineering work at {company_name} — think there's real overlap with what I'm building.")
       - Bullet 4: Resume attached ("• Resume attached below — feel free to share with your team so they know what to test me on.")
       - Bullet 5: Punchy zero-risk trial ask ("• So: don't believe the resume. Give me an assignment, see my work, then decide.")
    3. Do NOT use fancy AI fluff, robotic buzzwords, or corporate filler. Keep it direct, polite, and confident.
    """
    
    try:
        structured_llm = llm.with_structured_output(PitchItem)
        res = structured_llm.invoke(prompt)
        if isinstance(res, PitchItem):
            pitch_dict = res.model_dump()
        elif isinstance(res, dict):
            pitch_dict = res
        else:
            raise ValueError(f"Unexpected response format: {type(res)}")
        pitch_dict["role_target"] = role_target
    except Exception as e:
        print(f"[Graph] Structured output generator fallback due to: {e}")
        pitch_dict = {
            "role_target": role_target,
            "pitch_subject": "Merged code in Google's TensorFlow & Red Hat's Podman",
            "pitch_body": DEFAULT_PITCH_TEMPLATE.format(first_name=first_name, company_name=company_name)
        }

    return {
        **state,
        "pitches": [pitch_dict]
    }

def hitl_save_node(state: OutreachState) -> OutreachState:
    domain = state["domain"]
    company_name = state["company_name"]
    region = state.get("region", "Global")
    is_cse = 1 if state.get("is_cse_relevant", True) else 0
    reason = state.get("relevance_reason", "")
    
    # 1. Save Company to DB (Cache)
    company_id = save_company(domain, company_name, region, is_cse, reason)
    
    # If not CSE relevant, skip contact/pitch creation
    if not is_cse:
        return {
            **state,
            "company_id": company_id,
            "status": "REJECTED_NON_CSE"
        }
        
    contacts = state.get("contacts", [])
    pitches = state.get("pitches", [])
    
    # 2. Save Contacts
    saved_contacts = []
    for c in contacts:
        cid = save_contact(
            company_id=company_id,
            name=c.get("name", "Executive"),
            title=c.get("title", "Leader"),
            email=c.get("email", ""),
            email_source=c.get("source", ""),
            linkedin_url=c.get("linkedin_url", ""),
            twitter_handle=c.get("twitter_handle", "")
        )
        saved_contacts.append({
            "contact_id": cid,
            "email": (c.get("email") or "").strip().lower(),
            "name": c.get("name", ""),
            "title": c.get("title", "")
        })
        
    primary_contact_id = saved_contacts[0]["contact_id"] if saved_contacts else None
    
    # 3. Deduplicate Pending Pitch Drafts (Human in the Loop Queue) by recipient email
    saved_emails = set()
    filtered_pitches = []
    
    for p in pitches:
        role = p.get("role_target", "CTO")
        target_contact_id = primary_contact_id
        target_email = saved_contacts[0]["email"] if saved_contacts else f"founders@{domain}"
        
        # Check if a specific contact matches this role
        for sc in saved_contacts:
            title_l = sc["title"].lower()
            if (role == "CTO" and any(k in title_l for k in ["cto", "tech", "vp", "architect"])) or \
               (role == "CEO" and any(k in title_l for k in ["ceo", "founder", "president"])) or \
               (role == "HR" and any(k in title_l for k in ["hr", "recruiter", "talent", "people"])):
                target_contact_id = sc["contact_id"]
                target_email = sc["email"]
                break

        if target_email not in saved_emails:
            saved_emails.add(target_email)
            filtered_pitches.append((p, target_contact_id))
            
    for p, cid in filtered_pitches:
        save_outreach_draft(
            company_id=company_id,
            contact_id=cid,
            role_target=p.get("role_target", "CTO"),
            pitch_subject=p.get("pitch_subject", ""),
            pitch_body=p.get("pitch_body", "")
        )
        
    return {
        **state,
        "company_id": company_id,
        "status": "HITL_PENDING_REVIEW"
    }

# Build LangGraph Workflow
workflow = StateGraph(OutreachState)

workflow.add_node("crawl", company_crawler_node)
workflow.add_node("relevance", cse_relevance_evaluator_node)
workflow.add_node("exec_discovery", executive_discovery_node)
workflow.add_node("pitch_generator", role_specific_pitch_generator_node)
workflow.add_node("hitl_save", hitl_save_node)

workflow.set_entry_point("crawl")
workflow.add_edge("crawl", "relevance")

# Conditional edge based on CSE Relevance
def relevance_router(state: OutreachState):
    if state.get("is_cse_relevant", True):
        return "exec_discovery"
    return "hitl_save"

workflow.add_conditional_edges("relevance", relevance_router, {
    "exec_discovery": "exec_discovery",
    "hitl_save": "hitl_save"
})

workflow.add_edge("exec_discovery", "pitch_generator")
workflow.add_edge("pitch_generator", "hitl_save")
workflow.add_edge("hitl_save", END)

outreach_graph = workflow.compile()
