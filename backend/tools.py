import os
import re
import json
import requests
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from duckduckgo_search import DDGS

# Load .env file
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
load_dotenv(dotenv_path)

def get_env_var(keys: List[str]) -> str:
    """Helper to retrieve environment variable across different case variations."""
    for key in keys:
        val = os.getenv(key) or os.getenv(key.upper()) or os.getenv(key.lower())
        if val:
            return val.strip()
    return ""

GROQ_API_KEY = get_env_var(["groq_api", "GROQ_API_KEY"])
HUNTER_API_KEY = get_env_var(["hunter", "HUNTER_API_KEY"])
APOLLO_API_KEY = get_env_var(["appolo", "apollo", "APOLLO_API_KEY"])
TAVILY_API_KEY = get_env_var(["tavilly", "tavily", "TAVILY_API_KEY"])

def discover_startups_by_region() -> Dict[str, List[Dict[str, Any]]]:
    """
    Region-Partitioned Early-Stage Discovery Strategy:
    Targets early-stage / seed / Series A & YC hiring startups (where founders/CTOs directly review pitches).
    1. US & YC: Tavily API + DDG US search + Curated Early-Stage US Pool (6 results max)
    2. Europe: DuckDuckGo EU + Curated Early-Stage EU Pool (6 results max)
    3. Asia & Middle East: DuckDuckGo Asia/Dubai + Curated Early-Stage Asia/Dubai Pool (6 results max)
    """
    results = {
        "us_yc": [],
        "eu": [],
        "asia_me": []
    }
    seen_domains = set()
    ignored = [
        "ycombinator.com", "linkedin.com", "techcrunch.com", "github.com", "medium.com", "youtube.com",
        "wikipedia.org", "google.com", "glassdoor.com", "indeed.com", "builtin.com",
        "myntra.com", "nykaafashion.com", "zara.com", "only.in", "amazon.com", "flipkart.com",
        "walmart.com", "ebay.com", "etsy.com", "target.com", "nike.com", "hm.com",
        "seed.com", "minecraft.net", "gardening.com", "seedmap.org",
        "dictionary.com", "merriam-webster.com", "cambridge.org", "wiktionary.org", "thefreedictionary.com"
    ]

    TARGET_COUNT = 6

    # --- 1. US & YC Region (Early-Stage / YC / Series A) ---
    us_yc_query = "early stage Y Combinator AI startups hiring software engineers"
    if TAVILY_API_KEY:
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=TAVILY_API_KEY)
            response = client.search(query=us_yc_query, max_results=4)
            for res in response.get("results", []):
                url = res.get("url", "")
                domain = url.replace("https://", "").replace("http://", "").split("/")[0].replace("www.", "")
                if domain and domain not in seen_domains and not any(ig in domain for ig in ignored):
                    seen_domains.add(domain)
                    name = res.get("title", domain).split("-")[0].split("|")[0].strip()
                    results["us_yc"].append({
                        "name": name,
                        "domain": domain,
                        "url": url,
                        "snippet": res.get("content", "")[:180],
                        "source": "Tavily API",
                        "region": "US & YC",
                        "linkedin_url": f"https://www.linkedin.com/company/{domain.split('.')[0]}",
                        "careers_url": f"https://{domain}/careers"
                    })
        except Exception as e:
            print(f"[Tools] Tavily search error: {e}")

    # Supplemental DDG search for US (strict early-stage AI engineering terms)
    if len(results["us_yc"]) < TARGET_COUNT:
        try:
            ddgs = DDGS()
            ddg_res = list(ddgs.text("early stage AI startups San Francisco hiring software engineers", max_results=6))
            for r in ddg_res:
                url = r.get("href", "")
                domain = url.replace("https://", "").replace("http://", "").split("/")[0].replace("www.", "")
                if domain and domain not in seen_domains and not any(ig in domain for ig in ignored):
                    seen_domains.add(domain)
                    name = r.get("title", domain).split("-")[0].split("|")[0].strip()
                    results["us_yc"].append({
                        "name": name,
                        "domain": domain,
                        "url": url,
                        "snippet": r.get("body", "")[:180],
                        "source": "DuckDuckGo US",
                        "region": "US & YC",
                        "linkedin_url": f"https://www.linkedin.com/company/{domain.split('.')[0]}",
                        "careers_url": f"https://{domain}/careers"
                    })
        except Exception as e:
            print(f"[Tools] DDG US search error: {e}")

    # Curated Early-Stage US & YC Startup Pool
    us_pool = [
        {"name": "Phidata", "domain": "phidata.com", "url": "https://phidata.com", "snippet": "Open-source framework for building multi-modal AI agents with memory.", "careers_url": "https://phidata.com/careers"},
        {"name": "LlamaIndex", "domain": "llamaindex.ai", "url": "https://llamaindex.ai", "snippet": "Data framework for building LLM applications over enterprise data.", "careers_url": "https://llamaindex.ai/careers"},
        {"name": "Vapi AI", "domain": "vapi.ai", "url": "https://vapi.ai", "snippet": "Voice AI infrastructure for developers building conversational voice agents.", "careers_url": "https://vapi.ai/careers"},
        {"name": "CrewAI", "domain": "crewai.com", "url": "https://crewai.com", "snippet": "Multi-agent automation platform for engineering and operations.", "careers_url": "https://crewai.com/careers"},
        {"name": "Cursor AI", "domain": "cursor.com", "url": "https://cursor.com", "snippet": "AI-first Code Editor built for software engineers.", "careers_url": "https://cursor.com/careers"},
        {"name": "Perplexity AI", "domain": "perplexity.ai", "url": "https://perplexity.ai", "snippet": "Conversational AI search engine revolutionizing information discovery.", "careers_url": "https://perplexity.ai/careers"}
    ]
    for p in us_pool:
        if len(results["us_yc"]) >= TARGET_COUNT:
            break
        if p["domain"] not in seen_domains:
            seen_domains.add(p["domain"])
            results["us_yc"].append({
                **p,
                "source": "Curated US Early-Stage Pool",
                "region": "US & YC",
                "linkedin_url": f"https://www.linkedin.com/company/{p['domain'].split('.')[0]}"
            })

    # --- 2. Europe Region (Early-Stage / YC / Series A - 100% Free) ---
    try:
        ddgs = DDGS()
        ddg_res = list(ddgs.text("European AI tech startups hiring engineers London Berlin Paris", max_results=6))
        for r in ddg_res:
            url = r.get("href", "")
            domain = url.replace("https://", "").replace("http://", "").split("/")[0].replace("www.", "")
            if domain and domain not in seen_domains and not any(ig in domain for ig in ignored):
                seen_domains.add(domain)
                name = r.get("title", domain).split("-")[0].split("|")[0].strip()
                results["eu"].append({
                    "name": name,
                    "domain": domain,
                    "url": url,
                    "snippet": r.get("body", "")[:180],
                    "source": "DuckDuckGo EU",
                    "region": "Europe",
                    "linkedin_url": f"https://www.linkedin.com/company/{domain.split('.')[0]}",
                    "careers_url": f"https://{domain}/careers"
                })
    except Exception as e:
        print(f"[Tools] DDG EU search error: {e}")

    # Curated Early-Stage Europe Startup Pool
    eu_pool = [
        {"name": "Dust AI", "domain": "dust.tt", "url": "https://dust.tt", "snippet": "Paris-based AI platform building custom assistant tools for tech teams.", "careers_url": "https://dust.tt/careers"},
        {"name": "Poolside AI", "domain": "poolside.ai", "url": "https://poolside.ai", "snippet": "Paris-based AI lab developing frontier models specifically for software creation.", "careers_url": "https://poolside.ai/careers"},
        {"name": "Braintrust AI", "domain": "braintrust.dev", "url": "https://braintrust.dev", "snippet": "AI evaluation and observability platform for production AI software.", "careers_url": "https://braintrust.dev/careers"},
        {"name": "Lovable", "domain": "lovable.dev", "url": "https://lovable.dev", "snippet": "Stockholm-based AI web application creator shipping full-stack apps.", "careers_url": "https://lovable.dev/careers"},
        {"name": "Mistral AI", "domain": "mistral.ai", "url": "https://mistral.ai", "snippet": "Paris-based open-weights AI model research lab.", "careers_url": "https://mistral.ai/careers"},
        {"name": "Synthesia", "domain": "synthesia.io", "url": "https://synthesia.io", "snippet": "London-based AI video generation platform backed by top VCs.", "careers_url": "https://synthesia.io/careers"}
    ]
    for p in eu_pool:
        if len(results["eu"]) >= TARGET_COUNT:
            break
        if p["domain"] not in seen_domains:
            seen_domains.add(p["domain"])
            results["eu"].append({
                **p,
                "source": "Curated EU Early-Stage Pool",
                "region": "Europe",
                "linkedin_url": f"https://www.linkedin.com/company/{p['domain'].split('.')[0]}"
            })

    # --- 3. Asia & Middle East Region (Early-Stage / YC / Series A - 100% Free) ---
    try:
        ddgs = DDGS()
        ddg_res = list(ddgs.text("early stage AI tech startups Singapore Dubai hiring software engineers", max_results=6))
        for r in ddg_res:
            url = r.get("href", "")
            domain = url.replace("https://", "").replace("http://", "").split("/")[0].replace("www.", "")
            if domain and domain not in seen_domains and not any(ig in domain for ig in ignored):
                seen_domains.add(domain)
                name = r.get("title", domain).split("-")[0].split("|")[0].strip()
                results["asia_me"].append({
                    "name": name,
                    "domain": domain,
                    "url": url,
                    "snippet": r.get("body", "")[:180],
                    "source": "DuckDuckGo Asia/ME",
                    "region": "Asia & Dubai",
                    "linkedin_url": f"https://www.linkedin.com/company/{domain.split('.')[0]}",
                    "careers_url": f"https://{domain}/careers"
                })
    except Exception as e:
        print(f"[Tools] DDG Asia search error: {e}")

    # Curated Early-Stage Asia & Dubai Pool
    asia_pool = [
        {"name": "AI71", "domain": "ai71.ai", "url": "https://ai71.ai", "snippet": "Abu Dhabi & Dubai AI ecosystem commercializing Falcon foundation models.", "careers_url": "https://ai71.ai/careers"},
        {"name": "Kinetix AI", "domain": "kinetix.tech", "url": "https://kinetix.tech", "snippet": "Dubai AI startup creating generative 3D animation tools for tech platforms.", "careers_url": "https://kinetix.tech/careers"},
        {"name": "Hypotenuse AI", "domain": "hypotenuse.ai", "url": "https://hypotenuse.ai", "snippet": "Singapore generative AI writing and data intelligence platform.", "careers_url": "https://hypotenuse.ai/careers"},
        {"name": "Subconscious AI", "domain": "subconscious.ai", "url": "https://subconscious.ai", "snippet": "Singapore AI agent decision engine simulating human preference models.", "careers_url": "https://subconscious.ai/careers"},
        {"name": "Carro AI", "domain": "carro.co", "url": "https://carro.co", "snippet": "Singapore AI automotive marketplace scaleup.", "careers_url": "https://carro.co/careers"},
        {"name": "Sakana AI", "domain": "sakana.ai", "url": "https://sakana.ai", "snippet": "Tokyo AI research lab pioneering evolutionary foundation models.", "careers_url": "https://sakana.ai/careers"}
    ]
    for p in asia_pool:
        if len(results["asia_me"]) >= TARGET_COUNT:
            break
        if p["domain"] not in seen_domains:
            seen_domains.add(p["domain"])
            results["asia_me"].append({
                **p,
                "source": "Curated Asia/Dubai Early-Stage Pool",
                "region": "Asia & Dubai",
                "linkedin_url": f"https://www.linkedin.com/company/{p['domain'].split('.')[0]}"
            })

    return results

def crawl_company_website(domain: str) -> str:
    """Crawl homepage & about page text for company intelligence synthesis."""
    clean_domain = domain.lower().replace("https://", "").replace("http://", "").split("/")[0]
    target_url = f"https://{clean_domain}"
    
    scraped_text = ""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"}
        resp = requests.get(target_url, headers=headers, timeout=5)
        if resp.status_code == 200:
            # Basic HTML text extraction
            text = re.sub(r'<script.*?>.*?</script>', '', resp.text, flags=re.DOTALL)
            text = re.sub(r'<style.*?>.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<.*?>', ' ', text)
            scraped_text = ' '.join(text.split())[:3000]
    except Exception as e:
        scraped_text = f"Company domain: {clean_domain}. Search summary unavailable."
    
    return scraped_text

def find_email_via_hunter(domain: str) -> Optional[Dict[str, str]]:
    """Waterfall Check 2: Hunter.io API Key lookup ($0 free tier)."""
    if not HUNTER_API_KEY:
        return None
    try:
        url = f"https://api.hunter.io/v2/domain-search?domain={domain}&api_key={HUNTER_API_KEY}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            emails = data.get("data", {}).get("emails", [])
            for e in emails:
                position = (e.get("position") or "").lower()
                # Exclude non-technical roles (policy, comms, legal, marketing, etc.)
                if any(reject in position for reject in ["policy", "communication", "public affair", "marketing", "legal", "hr", "recruiter", "sales", "pr"]):
                    continue
                # Strictly match technical leadership or company founders
                if any(t in position for t in ["cto", "founder", "ceo", "chief technology officer", "chief scientist", "head of engineering", "head of ai", "vp engineering", "vp of engineering"]):
                    return {
                        "name": f"{e.get('first_name', '')} {e.get('last_name', '')}".strip() or "Executive",
                        "title": e.get("position") or "Leader",
                        "email": e.get("value"),
                        "source": "Hunter.io API"
                    }
    except Exception as e:
        print(f"[Tools] Hunter API error: {e}")
    return None

def find_github_commit_email(company_name: str, person_name: str) -> Optional[Dict[str, str]]:
    """Waterfall Check 1: GitHub API Commit Lookup (100% Free & Unlimited for Tech Leaders)."""
    try:
        query = f"{person_name} {company_name}"
        url = f"https://api.github.com/search/users?q={query}"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            if items:
                username = items[0].get("login")
                events_url = f"https://api.github.com/users/{username}/events/public"
                events_resp = requests.get(events_url, headers=headers, timeout=5)
                if events_resp.status_code == 200:
                    events = events_resp.json()
                    for ev in events:
                        if ev.get("type") == "PushEvent":
                            commits = ev.get("payload", {}).get("commits", [])
                            for c in commits:
                                author_email = c.get("author", {}).get("email")
                                if author_email and not author_email.endswith("noreply.github.com"):
                                    return {
                                        "name": person_name,
                                        "title": "CTO / Technical Leader",
                                        "email": author_email,
                                        "source": f"GitHub Commits (@{username})"
                                    }
    except Exception as e:
        print(f"[Tools] GitHub lookup error: {e}")
    return None

def find_email_waterfall(domain: str, company_name: str) -> List[Dict[str, str]]:
    """
    Waterfall Email Lookup Pipeline:
    1. Try Hunter.io API
    2. Try GitHub Commit API for tech leads
    3. Try Web Regex Scraping
    4. Fallback to Social / Email Prediction
    """
    contacts = []

    # 1. Hunter API Lookup
    hunter_res = find_email_via_hunter(domain)
    if hunter_res:
        contacts.append(hunter_res)

    # 2. LLM + DDG Search to resolve true CEO/CTO/Founder
    try:
        snippets = ""
        try:
            ddgs = DDGS()
            res = list(ddgs.text(f"{company_name} CEO OR CTO OR Founder", max_results=4))
            snippets = "\n".join([r.get("body", "") for r in res])
        except Exception as e:
            print(f"[Tools] DDG snippet fetch error: {e}")
        
        prompt = f"""Target Company: {company_name} ({domain})
Search Snippets (if available):
{snippets}

Identify the primary CEO, CTO, or Founder of {company_name}.
Return ONLY a JSON object with no markdown formatting:
{{
  "name": "Full Name",
  "title": "Exact Title (e.g. CEO & Co-Founder or CTO)",
  "email_prefix": "firstname.lastname or firstname"
}}
"""
        if GROQ_API_KEY:
            from groq import Groq
            client = Groq(api_key=GROQ_API_KEY)
            response = client.chat.completions.create(
                model="qwen/qwen3.8-27b",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            raw = response.choices[0].message.content.strip()
            # Clean json fences if present
            raw_clean = re.sub(r"```json|```", "", raw).strip()
            exec_data = json.loads(raw_clean)
            
            p_name = (exec_data.get("name") or "").strip()
            p_title = (exec_data.get("title") or "Co-Founder / Decision Maker").strip()
            p_prefix = (exec_data.get("email_prefix") or "").strip().lower()
            
            invalid_terms = ["unknown", "n/a", "none", "not available", "null", "undefined"]
            is_invalid = not p_name or any(inv == p_name.lower() or inv in p_prefix for inv in invalid_terms)
            
            clean_domain = domain.lower().replace("https://", "").replace("http://", "").split("/")[0].replace("www.", "")
            
            if is_invalid:
                p_name = f"Founders & Tech Leadership of {company_name}"
                p_email = f"founders@{clean_domain}"
                p_source = "Domain Standard Founder Pattern"
            else:
                if not p_prefix:
                    p_prefix = p_name.lower().split()[0]
                p_email = f"{p_prefix}@{clean_domain}"
                p_source = "AI Executive Resolver (Groq + Web)"

            exec_contact = {
                "name": p_name,
                "title": p_title,
                "email": p_email,
                "source": p_source,
                "linkedin_url": f"https://www.linkedin.com/company/{clean_domain.split('.')[0]}"
            }
            # Prioritize true CEO / CTO / Founder over Hunter API generic contacts
            if any(k in p_title.lower() for k in ["ceo", "cto", "founder", "chief"]):
                contacts.insert(0, exec_contact)
            else:
                contacts.append(exec_contact)
    except Exception as e:
        print(f"[Tools] LLM executive resolution error: {e}")

    # 3. Fallback default if nothing found
    if not contacts:
        contacts.append({
            "name": f"Founders of {company_name}",
            "title": "CEO / Engineering Leadership",
            "email": f"founders@{domain}",
            "source": "Domain Standard Pattern"
        })

    return contacts

def find_person_email_waterfall(domain: str, company_name: str, person_name: str, person_title: str = "", profile_url: str = "") -> Dict[str, str]:
    """Find or predict email specifically for a targeted person profile."""
    if not person_name:
        return find_email_waterfall(domain, company_name)[0]

    # 1. Try GitHub commit lookup for person_name
    gh_res = find_github_commit_email(company_name, person_name)
    if gh_res and gh_res.get("email"):
        return {
            "name": person_name,
            "title": person_title or "Executive / Engineering Leader",
            "email": gh_res["email"],
            "source": gh_res["source"],
            "linkedin_url": profile_url
        }
        
    # 2. Try Hunter if API key present AND email matches target person
    hunter_res = find_email_via_hunter(domain)
    if hunter_res and hunter_res.get("email"):
        h_name = hunter_res.get("name", "").lower()
        p_first = person_name.lower().split()[0]
        if p_first in h_name:
            return {
                "name": person_name,
                "title": person_title or hunter_res.get("title", "Leader"),
                "email": hunter_res["email"],
                "source": hunter_res["source"],
                "linkedin_url": profile_url
            }
        
    # 3. Derive standard corporate email format for person: first.last@domain
    name_parts = person_name.lower().strip().replace(".", "").replace(",", "").split()
    first = name_parts[0] if name_parts else "contact"
    last = name_parts[-1] if len(name_parts) > 1 else ""
    
    clean_domain = domain.lower().replace("https://", "").replace("http://", "").split("/")[0].replace("www.", "")
    predicted_email = f"{first}.{last}@{clean_domain}" if (last and clean_domain) else f"{first}@{clean_domain if clean_domain else 'company.com'}"
    
    return {
        "name": person_name,
        "title": person_title or "Co-founder / Decision Maker",
        "email": predicted_email,
        "source": "Smart Direct Email Prediction (first.last@domain)",
        "linkedin_url": profile_url
    }


