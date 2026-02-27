from datetime import datetime, timedelta
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from app.config import get_jwt_secret, get_auth_password

security = HTTPBearer(auto_error=False)

TOKEN_EXPIRE_HOURS = 24


def create_token() -> str:
    expire = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {"exp": expire, "sub": "admin"}
    return jwt.encode(payload, get_jwt_secret(), algorithm="HS256")


def verify_token(token: str) -> bool:
    try:
        jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])
        return True
    except JWTError:
        return False


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Dependency that requires valid JWT authentication.
    If no password is configured, block access — admin must set a password first.
    """
    password = get_auth_password()
    if not password:
        raise HTTPException(status_code=403, detail="系统未配置密码，请联系管理员")

    if not credentials:
        raise HTTPException(status_code=401, detail="未提供认证凭据")

    if not verify_token(credentials.credentials):
        raise HTTPException(status_code=401, detail="认证已过期，请重新登录")

    return credentials.credentials
