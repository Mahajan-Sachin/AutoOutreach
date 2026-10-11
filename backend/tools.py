import os
import re
import json
import asyncio
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

async def discover_startups_by_region() -> Dict[str, List[Dict[str, Any]]]:
    """
    Region-Partitioned Early-Stage Discovery Strategy:
    100% Live Discovery powered by AsyncTavilyClient + AsyncGroq AI Startup Scout.
    Concurrent non-blocking fetch across US/YC, Europe, and Asia/Dubai hubs via asyncio.gather.
    """
    regions_config = {
        "us_yc": {
            "name": "US & YC Startups",
            "region_label": "US & YC",
            "query": "top early stage YC AI tech startups hiring software engineers San Francisco New York 2024"
        },
        "eu": {
            "name": "Europe Tech Scaleups",
            "region_label": "Europe",
            "query": "top European AI tech startups hiring software engineers London Berlin Paris Munich"
        },
        "asia_me": {
            "name": "Asia & Dubai Hubs",
            "region_label": "Asia & Dubai",
            "query": "top early stage AI tech startups hiring software engineers Singapore Dubai Bengaluru Tokyo"
        }
    }

    results = {
        "us_yc": [],
        "eu": [],
        "asia_me": []
    }
    seen_domains = set()

    async def fetch_region(reg_key: str, reg_info: dict) -> tuple:
        search_context = ""
        items = []

        if TAVILY_API_KEY:
            try:
                from tavily import AsyncTavilyClient
                t_client = AsyncTavilyClient(api_key=TAVILY_API_KEY)
                t_res = await t_client.search(query=reg_info["query"], max_results=8)
                snippets = [f"- {r.get('title')}: {r.get('url')} | {r.get('content', '')[:160]}" for r in t_res.get("results", [])]
                search_context = "\n".join(snippets)
            except Exception as e:
                print(f"[Tools] Async Tavily search error for {reg_key}: {e}")

        if GROQ_API_KEY:
            try:
                from groq import AsyncGroq
                g_client = AsyncGroq(api_key=GROQ_API_KEY)
                prompt = f"""You are a Silicon Valley startup scout.
Current live web search context for {reg_info['name']}:
{search_context}

Identify or extract exactly 6 real, active early-stage / Series A-B AI & software tech startups based in {reg_info['name']} that hire software engineers.
CRITICAL RULES:
1. NEVER output job boards (Simplify, Indeed, Wellfound, LinkedIn), news/directory sites (TechCrunch, CB Insights, OpenVC, Forbes, Reddit, Baidu), or Big Tech (Google, Meta, Apple, Amazon, Microsoft).
2. ONLY output real tech companies with their own primary domain (e.g. cursor.com, phidata.com, mistral.ai, elevenlabs.io, postman.com).
3. Return EXACTLY 6 startups in a strict JSON array.

Format your response as a strict JSON array of 6 objects with these keys:
- "name": Company Name
- "domain": primary domain only (e.g. "cursor.com")
- "url": "https://company.com"
- "snippet": Short 1-sentence technical description
- "careers_url": "https://company.com/careers"

Output ONLY the JSON array, no markdown fences, no explanation."""

                res = await g_client.chat.completions.create(
                    model="qwen/qwen3.8-27b",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2
                )
                raw = res.choices[0].message.content.strip()
                raw_clean = re.sub(r"^```json|^```|```$", "", raw).strip()
                parsed = json.loads(raw_clean)

                for item in parsed:
                    domain = item.get("domain", "").lower().replace("https://", "").replace("http://", "").split("/")[0].replace("www.", "").strip()
                    if domain:
                        items.append({
                            "name": item.get("name", domain),
                            "domain": domain,
                            "url": item.get("url", f"https://{domain}"),
                            "snippet": item.get("snippet", ""),
                            "source": "Live AI Scout",
                            "region": reg_info["region_label"],
                            "linkedin_url": f"https://www.linkedin.com/company/{domain.split('.')[0]}",
                            "careers_url": item.get("careers_url", f"https://{domain}/careers")
                        })
            except Exception as e:
                print(f"[Tools] Async AI Scout error for {reg_key}: {e}")

        return reg_key, items

    # Concurrent non-blocking fetch across all 3 regions using standard asyncio.gather
    completed = await asyncio.gather(*(fetch_region(k, v) for k, v in regions_config.items()))
    for reg_key, items in completed:
        for item in items:
            if item["domain"] not in seen_domains:
                seen_domains.add(item["domain"])
                results[reg_key].append(item)

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


