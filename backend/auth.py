import os
import time
import bcrypt
import jwt
from typing import Optional, Dict, Any
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Secret key and algorithm configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "jobfit_production_jwt_secret_key_2026_azure_secure")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 30 * 24 * 3600  # 30-day token lifetime for seamless Chrome extension usage

security = HTTPBearer(auto_error=False)

def hash_password(plain_password: str) -> str:
    """Hash password securely using bcrypt with auto-generated salt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def create_access_token(data: Dict[str, Any], expires_delta_seconds: Optional[int] = None) -> str:
    """Create signed HMAC-SHA256 JWT access token with role and subject claims."""
    to_encode = data.copy()
    expire_timestamp = int(time.time()) + (expires_delta_seconds or ACCESS_TOKEN_EXPIRE_SECONDS)
    to_encode.update({"exp": expire_timestamp, "iat": int(time.time())})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and cryptographically verify JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session token expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token signature.",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_current_admin(auth: Optional[HTTPAuthorizationCredentials] = Security(security)) -> Dict[str, Any]:
    """
    FastAPI Route Guard:
    Validates Bearer token from 'Authorization: Bearer <token>' header.
    Ensures requester is authenticated and has admin privileges.
    """
    if not auth or not auth.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    payload = decode_access_token(auth.credentials)
    username = payload.get("sub")
    role = payload.get("role")
    
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload is missing subject identity.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    return {"username": username, "role": role}
