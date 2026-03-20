from datetime import datetime, timedelta, timezone
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from app.config import get_jwt_secret, get_auth_password

security = HTTPBearer(auto_error=False)

TOKEN_EXPIRE_HOURS = 24
REFRESH_TOKEN_EXPIRE_DAYS = 30

# Access token cookie — allows the backend to authenticate requests even when
# Safari has cleared localStorage (losing the Bearer header token).
ACCESS_COOKIE_NAME = "teamgr_access"


def create_token() -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {"exp": expire, "sub": "admin", "type": "access"}
    return jwt.encode(payload, get_jwt_secret(), algorithm="HS256")


def create_refresh_token(device_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"exp": expire, "sub": "admin", "type": "refresh", "device_id": device_id}
    return jwt.encode(payload, get_jwt_secret(), algorithm="HS256")


def verify_token(token: str) -> bool:
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])
        # Accept both old tokens (no type) and access tokens
        token_type = payload.get("type", "access")
        return token_type == "access"
    except JWTError:
        return False


def verify_refresh_token(token: str) -> str | None:
    """Verify a refresh token. Returns device_id if valid, None otherwise."""
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])
        if payload.get("type") != "refresh":
            return None
        return payload.get("device_id")
    except JWTError:
        return None


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Dependency that requires valid JWT authentication.
    If no password is configured, block access — admin must set a password first.
    Checks Authorization header first, then falls back to access token cookie
    (for Safari where localStorage is cleared by ITP).
    """
    password = get_auth_password()
    if not password:
        raise HTTPException(status_code=403, detail="系统未配置密码，请联系管理员")

    # 1. Check Authorization header (standard path)
    if credentials and verify_token(credentials.credentials):
        return credentials.credentials

    # 2. Fallback: access token cookie (survives Safari localStorage clearing)
    access_cookie = request.cookies.get(ACCESS_COOKIE_NAME)
    if access_cookie and verify_token(access_cookie):
        return access_cookie

    # 3. Last resort: User-Agent matches a trusted device (within 30 days).
    #    Handles iOS Safari where self-signed certs may prevent cookie persistence.
    from app.services.device_trust import get_active_trusted_by_ua
    user_agent = request.headers.get("User-Agent", "")
    if user_agent:
        trusted_entry = get_active_trusted_by_ua(user_agent)
        if trusted_entry:
            return trusted_entry["device_id"]

    raise HTTPException(status_code=401, detail="认证已过期，请重新登录")
