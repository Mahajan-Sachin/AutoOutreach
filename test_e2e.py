import json
import urllib.request
import urllib.error
import sys

BASE_URL = "http://4.145.88.53:8000"

def log_test(name, passed, detail=""):
    status = " PASS " if passed else " FAIL "
    print(f"[{status}] {name}")
    if detail:
        print(f"       -> {detail}")
    if not passed:
        sys.exit(1)

def run_e2e_suite():
    print("=" * 60)
    print("  RUNNING SYSTEM END-TO-END VERIFICATION SUITE")
    print(f"  Target: {BASE_URL}")
    print("=" * 60)

    # 1. Health Check
    try:
        req = urllib.request.Request(f"{BASE_URL}/api/health")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            log_test("GET /api/health", data.get("status") == "online", f"Response: {data}")
    except Exception as e:
        log_test("GET /api/health", False, str(e))

    # 2. Auth Protection (Unauthenticated Request should fail)
    try:
        req = urllib.request.Request(f"{BASE_URL}/api/pending")
        urllib.request.urlopen(req, timeout=10)
        log_test("Auth Guard (Expected 401)", False, "Endpoint unexpectedly allowed anonymous access")
    except urllib.error.HTTPError as e:
        log_test("Auth Guard (Expected 401)", e.code == 401, f"Received expected HTTP {e.code}")

    # 3. Invalid Login Credentials
    try:
        payload = json.dumps({"username": "sachin", "password": "wrongpassword"}).encode()
        req = urllib.request.Request(f"{BASE_URL}/api/auth/login", data=payload, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        log_test("Invalid Login Guard (Expected 401)", False, "Allowed bad password")
    except urllib.error.HTTPError as e:
        log_test("Invalid Login Guard (Expected 401)", e.code == 401, f"Received expected HTTP {e.code}")

    # 4. Valid Admin Login & JWT Issuance
    token = None
    try:
        payload = json.dumps({"username": "sachin", "password": "sachin123"}).encode()
        req = urllib.request.Request(f"{BASE_URL}/api/auth/login", data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            token = data.get("access_token")
            log_test("POST /api/auth/login (JWT Generation)", bool(token), f"Role: {data.get('role')}")
    except Exception as e:
        log_test("POST /api/auth/login (JWT Generation)", False, str(e))

    auth_headers = {"Authorization": f"Bearer {token}"}

    # 5. Token Verification
    try:
        req = urllib.request.Request(f"{BASE_URL}/api/auth/verify", headers=auth_headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            log_test("GET /api/auth/verify (Token Validation)", data.get("status") == "AUTHENTICATED", f"User: {data.get('user')}")
    except Exception as e:
        log_test("GET /api/auth/verify (Token Validation)", False, str(e))

    # 6. Live Startup Discovery
    try:
        req = urllib.request.Request(f"{BASE_URL}/api/discover", headers=auth_headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            total = data.get("total", 0)
            regions = data.get("regions", {})
            log_test("GET /api/discover (Live Discovery Search)", total > 0, f"Found {total} live startups across {list(regions.keys())}")
    except Exception as e:
        log_test("GET /api/discover (Live Discovery Search)", False, str(e))

    # 7. HITL Pending Drafts Endpoint
    try:
        req = urllib.request.Request(f"{BASE_URL}/api/pending", headers=auth_headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            drafts = data.get("pending_drafts", [])
            log_test("GET /api/pending (HITL Queue Access)", isinstance(drafts, list), f"Drafts count: {len(drafts)}")
    except Exception as e:
        log_test("GET /api/pending (HITL Queue Access)", False, str(e))

    # 8. History Endpoint & Data Persistence
    try:
        req = urllib.request.Request(f"{BASE_URL}/api/history", headers=auth_headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            history = data.get("history", [])
            log_test("GET /api/history (Approved Records)", len(history) > 0, f"History items count: {len(history)} (Last: {history[0].get('domain') if history else 'None'})")
    except Exception as e:
        log_test("GET /api/history (Approved Records)", False, str(e))

    print("=" * 60)
    print("  ALL 8 END-TO-END VERIFICATION CHECKS PASSED PERFECTLY!")
    print("=" * 60)

if __name__ == "__main__":
    run_e2e_suite()
