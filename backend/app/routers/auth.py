import logging
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from app.config import get_auth_password
from app.middleware.auth_middleware import create_token, verify_token
from app.middleware.rate_limiter import (
    check_login_rate_limit, ban_manager, get_client_ip
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str
    message: str


class StatusResponse(BaseModel):
    password_configured: bool
    authenticated: bool


@router.get("/status", response_model=StatusResponse)
async def auth_status(request: Request):
    """Check if password is configured and if user is authenticated."""
    password = get_auth_password()
    password_configured = bool(password)

    if not password_configured:
        logger.warning(
            "⚠️  No password configured! "
            "Please set auth.password in config/config.yaml. "
            "The site is currently in unprotected mode."
        )

    # Check if bearer token is present and valid
    authenticated = False
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        authenticated = verify_token(token)

    # If no password required, always "authenticated"
    if not password_configured:
        authenticated = True

    return StatusResponse(
        password_configured=password_configured,
        authenticated=authenticated,
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    _: None = Depends(check_login_rate_limit),
):
    """Login with password. Subject to rate limiting and progressive banning."""
    ip = get_client_ip(request)
    configured_password = get_auth_password()

    if not configured_password:
        raise HTTPException(status_code=400, detail="未配置密码")

    if body.password != configured_password:
        ban_manager.record_failure(ip)
        raise HTTPException(status_code=401, detail="密码错误")

    ban_manager.record_success(ip)
    token = create_token()
    return LoginResponse(token=token, message="登录成功")
