import sqlite3
import os
import json
import redis
from typing import Optional, Dict, Any, List

DB_PATH = os.path.join(os.path.dirname(__file__), "outreach_cache.db")
REDIS_TTL_SECONDS = 86400  # 24-hour Time-To-Live for L2 Cache

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# Initialize Redis L2 Cache Client
try:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
    redis_client.ping()
    print(f"[Redis L2 Cache] Connected successfully to {REDIS_HOST}:{REDIS_PORT}")
except Exception as e:
    redis_client = None
    print(f"[Redis L2 Cache] Warning: Redis unavailable ({e}). Falling back to L3 SQLite.")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize SQLite tables for O(1) deduplication cache & outreach tracking."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Companies table (Deduplication Cache)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            region TEXT DEFAULT 'Global',
            is_cse_relevant INTEGER DEFAULT 1,
            relevance_reason TEXT,
            status TEXT DEFAULT 'DISCOVERED',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Decision Makers / Contacts table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            title TEXT NOT NULL,
            email TEXT,
            email_source TEXT,
            linkedin_url TEXT,
            twitter_handle TEXT,
            FOREIGN KEY (company_id) REFERENCES companies (id)
        )
    """)
    
    # Outreach History & Drafts table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS outreach_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            contact_id INTEGER,
            role_target TEXT NOT NULL, -- CTO, CEO, HR
            pitch_subject TEXT NOT NULL,
            pitch_body TEXT NOT NULL,
            status TEXT DEFAULT 'PENDING', -- PENDING, APPROVED, REJECTED, SENT
            sent_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_id) REFERENCES companies (id),
            FOREIGN KEY (contact_id) REFERENCES contacts (id)
        )
    """)

    # Users & Role-Based Access Control table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'admin',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Seed default admin user (sachin / sachin123) if no users exist
    cursor.execute("SELECT COUNT(*) as count FROM users")
    user_count = cursor.fetchone()["count"]
    if user_count == 0:
        import bcrypt
        default_hash = bcrypt.hashpw(b"sachin123", bcrypt.gensalt()).decode("utf-8")
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                       ("sachin", default_hash, "admin"))
        print("[Database] Seeded initial admin account: 'sachin'")

    conn.commit()
    conn.close()

def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Retrieve user record from SQLite by username."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username.strip().lower(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def is_domain_cached(domain: str) -> Optional[Dict[str, Any]]:
    """2-Tier Cache Check: L2 Redis (RAM <1ms) -> L3 SQLite (Disk) -> Full LangGraph API Execution."""
    domain_clean = domain.lower().strip().replace("https://", "").replace("http://", "").split("/")[0]
    redis_key = f"company:cache:{domain_clean}"

    # 1. Tier 2 (L2): Fast Redis In-Memory Cache Lookup
    if redis_client:
        try:
            cached_json = redis_client.get(redis_key)
            if cached_json:
                print(f"[L2 Cache Hit - Redis] {domain_clean} retrieved in sub-1ms (TTL 24h).")
                return json.loads(cached_json)
        except Exception as e:
            print(f"[L2 Cache Error] Redis read failed: {e}")

    # 2. Tier 3 (L3): SQLite Disk Database Fallback
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM companies WHERE domain = ?", (domain_clean,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        company_dict = dict(row)
        print(f"[L3 Cache Hit - SQLite] {domain_clean} found on disk DB. Warming L2 Redis cache...")
        # Populate L2 Redis Cache for future sub-1ms hits
        if redis_client:
            try:
                redis_client.setex(redis_key, REDIS_TTL_SECONDS, json.dumps(company_dict))
            except Exception as e:
                print(f"[L2 Cache Write Error]: {e}")
        return company_dict
        
    return None

def save_company(domain: str, name: str, region: str = "Global", is_cse_relevant: int = 1, relevance_reason: str = "") -> int:
    domain_clean = domain.lower().strip().replace("https://", "").replace("http://", "").split("/")[0]
    redis_key = f"company:cache:{domain_clean}"
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO companies (domain, name, region, is_cse_relevant, relevance_reason)
            VALUES (?, ?, ?, ?, ?)
        """, (domain_clean, name, region, is_cse_relevant, relevance_reason))
        company_id = cursor.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        cursor.execute("SELECT id FROM companies WHERE domain = ?", (domain_clean,))
        company_id = cursor.fetchone()['id']
    conn.close()

    # Build company payload & populate L2 Redis RAM cache
    company_dict = {
        "id": company_id,
        "domain": domain_clean,
        "name": name,
        "region": region,
        "is_cse_relevant": is_cse_relevant,
        "relevance_reason": relevance_reason
    }
    if redis_client:
        try:
            redis_client.setex(redis_key, REDIS_TTL_SECONDS, json.dumps(company_dict))
            print(f"[L2 Cache Saved] {domain_clean} written to Redis RAM with {REDIS_TTL_SECONDS}s TTL.")
        except Exception as e:
            print(f"[L2 Cache Write Error]: {e}")

    return company_id

def save_contact(company_id: int, name: str, title: str, email: str = "", email_source: str = "", linkedin_url: str = "", twitter_handle: str = "") -> int:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO contacts (company_id, name, title, email, email_source, linkedin_url, twitter_handle)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (company_id, name, title, email, email_source, linkedin_url, twitter_handle))
    contact_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return contact_id

def save_outreach_draft(company_id: int, contact_id: Optional[int], role_target: str, pitch_subject: str, pitch_body: str) -> int:
    """
    Saves outreach draft with composite key Idempotency Guard (company_id:contact_id:role_target).
    Prevents duplicate pitch drafts in Redis & SQLite database.
    """
    cid_str = str(contact_id or 0)
    idempotency_key = f"idempotency:draft:{company_id}:{cid_str}:{role_target}"
    
    # 1. Check Redis for atomic idempotency key (<1ms)
    if redis_client:
        try:
            existing_draft_id = redis_client.get(idempotency_key)
            if existing_draft_id:
                print(f"[Idempotency Hit - Redis] Draft already exists for key '{idempotency_key}' (Draft ID: {existing_draft_id}). Skipping duplicate insert.")
                return int(existing_draft_id)
        except Exception as e:
            print(f"[Idempotency Read Error]: {e}")

    # 2. Check SQLite DB if draft with same company, contact, and role target is already pending
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM outreach_logs 
        WHERE company_id = ? AND (contact_id = ? OR (contact_id IS NULL AND ? = 0)) AND role_target = ? AND status = 'PENDING'
    """, (company_id, contact_id, contact_id or 0, role_target))
    row = cursor.fetchone()
    if row:
        existing_id = row['id']
        conn.close()
        if redis_client:
            try:
                redis_client.setex(idempotency_key, REDIS_TTL_SECONDS, str(existing_id))
            except Exception:
                pass
        print(f"[Idempotency Hit - SQLite] Draft ID {existing_id} already exists for '{idempotency_key}'. Skipping duplicate.")
        return existing_id

    # 3. Insert unique draft
    cursor.execute("""
        INSERT INTO outreach_logs (company_id, contact_id, role_target, pitch_subject, pitch_body, status)
        VALUES (?, ?, ?, ?, ?, 'PENDING')
    """, (company_id, contact_id, role_target, pitch_subject, pitch_body))
    draft_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # 4. Record idempotency key in Redis RAM (24h TTL)
    if redis_client:
        try:
            redis_client.setex(idempotency_key, REDIS_TTL_SECONDS, str(draft_id))
            print(f"[Idempotency Saved] Key '{idempotency_key}' mapped to Draft ID {draft_id}.")
        except Exception as e:
            print(f"[Idempotency Write Error]: {e}")

    return draft_id

def update_outreach_status(draft_id: int, status: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE outreach_logs 
        SET status = ?, sent_at = CURRENT_TIMESTAMP 
        WHERE id = ?
    """, (status, draft_id))
    conn.commit()
    conn.close()

def delete_outreach_draft(draft_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM outreach_logs WHERE id = ?", (draft_id,))
    conn.commit()
    conn.close()

def get_pending_outreach():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            o.id as draft_id,
            o.role_target,
            o.pitch_subject,
            o.pitch_body,
            o.status,
            o.created_at,
            c.name as company_name,
            c.domain as company_domain,
            c.relevance_reason,
            ct.name as contact_name,
            ct.title as contact_title,
            ct.email as contact_email,
            ct.email_source as contact_email_source,
            ct.linkedin_url as contact_linkedin,
            ct.twitter_handle as contact_twitter
        FROM outreach_logs o
        JOIN companies c ON o.company_id = c.id
        LEFT JOIN contacts ct ON o.contact_id = ct.id
        WHERE o.status = 'PENDING'
        ORDER BY o.created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    
    seen_pairs = set()
    unique_drafts = []
    for r in rows:
        d = dict(r)
        key = (d.get("company_domain"), (d.get("contact_email") or "").strip().lower())
        if key not in seen_pairs:
            seen_pairs.add(key)
            unique_drafts.append(d)
    return unique_drafts

def get_all_history():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            o.id as draft_id,
            o.role_target,
            o.pitch_subject,
            o.pitch_body,
            o.status,
            o.sent_at,
            c.name as company_name,
            c.domain as company_domain,
            ct.name as contact_name,
            ct.email as contact_email
        FROM outreach_logs o
        JOIN companies c ON o.company_id = c.id
        LEFT JOIN contacts ct ON o.contact_id = ct.id
        ORDER BY o.created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# Init on module import
init_db()
