import os
import redis
from fastapi import HTTPException

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

try:
    r_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
    r_client.ping()
except Exception:
    r_client = None

def check_rate_limit(client_id: str = "global", limit: int = 10, window_seconds: int = 60) -> bool:
    """Atomic Redis Rate Limiter: INCR key, EXPIRE on 1st request, raise 429 if count > limit."""
    if not r_client:
        return True
        
    key = f"rate_limit:{client_id}"
    count = r_client.incr(key)
    
    if count == 1:
        r_client.expire(key, window_seconds)
        
    if count > limit:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: maximum {limit} requests per {window_seconds}s allowed."
        )
        
    return True
