"""
Auth Middleware — JWT token creation, verification, and RBAC enforcement.

Roles:
  admin  — full access (query, audit logs, ingest, stats)
  agent  — can query + stats
  viewer — read-only (stats only)
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from config import settings

bearer_scheme = HTTPBearer(auto_error=False)

# ── Role hierarchy ─────────────────────────────────────────────────────────────
ROLE_PERMISSIONS = {
    "admin":  ["query", "audit", "ingest", "stats", "admin"],
    "agent":  ["query", "stats"],
    "viewer": ["stats"],
}

# ── Demo users — plain text passwords for demo/competition use ────────────────
# In production: replace with DB lookup + proper hashing
DEMO_USERS = {
    "admin": {
        "username": "admin",
        "password": "admin123",
        "role":     "admin",
    },
    "agent001": {
        "username": "agent001",
        "password": "agent123",
        "role":     "agent",
    },
    "viewer": {
        "username": "viewer",
        "password": "viewer123",
        "role":     "viewer",
    },
}


# ── Pydantic models ────────────────────────────────────────────────────────────
class TokenData(BaseModel):
    username: str
    role:     str


class Token(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    role:         str
    expires_in:   int


class LoginRequest(BaseModel):
    username: str
    password: str


# ── Auth utilities ─────────────────────────────────────────────────────────────
def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Verify username + password. Returns user dict or None."""
    user = DEMO_USERS.get(username)
    if not user:
        return None
    if user["password"] != password:
        return None
    return user


def create_access_token(username: str, role: str) -> Token:
    """Create a signed JWT token."""
    expire = datetime.utcnow() + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub":  username,
        "role": role,
        "exp":  expire,
        "iat":  datetime.utcnow(),
    }
    token = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return Token(
        access_token=token,
        role=role,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def verify_token(token: str) -> TokenData:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        username: str = payload.get("sub")
        role:     str = payload.get("role", "viewer")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return TokenData(username=username, role=role)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token validation failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── FastAPI dependencies ───────────────────────────────────────────────────────
def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
) -> TokenData:
    """Extract and validate Bearer token from request."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verify_token(credentials.credentials)


def require_permission(permission: str):
    """
    RBAC dependency factory.
    Usage: Depends(require_permission("audit"))
    """
    def _check(current_user: TokenData = Depends(get_current_user)) -> TokenData:
        allowed = ROLE_PERMISSIONS.get(current_user.role, [])
        if permission not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' does not have '{permission}' permission",
            )
        return current_user
    return _check