import os
import time
import redis
from fastapi import HTTPException

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

try:
    r_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
    r_client.ping()
    print("[RateLimiter] Redis connection initialized for rate limiting.")
except Exception as e:
    r_client = None
    print(f"[RateLimiter Warning] Redis unavailable: {e}. Rate limiter degraded to passthrough.")

def check_rate_limit(client_id: str = "global", limit: int = 10, window_seconds: int = 60) -> bool:
    """
    Atomic Redis Rate Limiter (Fixed Window / Sliding Window Counter).
    Prevents API quota abuse by limiting requests per time window (e.g., 10 req / 60s).
    
    Raises:
        HTTPException(429) if quota is exceeded.
    """
    if not r_client:
        return True  # Graceful fallback if Redis is unreachable
        
    current_window = int(time.time()) // window_seconds
    key = f"ratelimit:{client_id}:{current_window}"
    
    try:
        count = r_client.incr(key)
        if count == 1:
            r_client.expire(key, window_seconds)
            
        if count > limit:
            remaining_ttl = r_client.ttl(key)
            print(f"[RateLimiter Exceeded] Client '{client_id}' hit limit ({count}/{limit}). TTL: {remaining_ttl}s")
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "message": f"Quota limit ({limit} requests/{window_seconds}s) reached to protect API credits.",
                    "retry_after_seconds": max(1, remaining_ttl)
                }
            )
        return True
    except HTTPException:
        raise
    except Exception as e:
        print(f"[RateLimiter Error] Failed to evaluate rate limit: {e}")
        return True
