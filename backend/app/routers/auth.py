import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from app.config import get_auth_password
from app.middleware.auth_middleware import (
    create_token, verify_token, create_refresh_token,
    verify_refresh_token, require_auth,
)
from app.middleware.rate_limiter import (
    check_login_rate_limit, ban_manager, get_client_ip
)
from app.services.device_trust import (
    is_device_trusted, is_device_blacklisted, get_device_status,
    trust_device, blacklist_device, update_last_used,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str
    device_id: Optional[str] = None


class LoginResponse(BaseModel):
    token: str
    message: str
    refresh_token: Optional[str] = None
    device_trusted: Optional[bool] = None
    device_blacklisted: Optional[bool] = None


class StatusResponse(BaseModel):
    password_configured: bool
    authenticated: bool


class DeviceRequest(BaseModel):
    device_id: str


class TrustDeviceResponse(BaseModel):
    message: str
    refresh_token: str


class BlacklistDeviceResponse(BaseModel):
    message: str


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    token: str
    refresh_token: str


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

    if body.device_id:
        status = get_device_status(body.device_id)

        if status == "trusted":
            update_last_used(body.device_id)
            refresh_token = create_refresh_token(body.device_id)
            return LoginResponse(
                token=token, message="登录成功",
                refresh_token=refresh_token, device_trusted=True,
            )

        if status == "blacklisted":
            return LoginResponse(
                token=token, message="登录成功",
                device_blacklisted=True,
            )

    # Unknown device or no device_id — frontend decides what to show
    return LoginResponse(token=token, message="登录成功")


@router.post("/trust-device", response_model=TrustDeviceResponse)
async def trust_device_endpoint(
    body: DeviceRequest,
    request: Request,
    _token: str = Depends(require_auth),
):
    """Trust the current device. Allows multiple trusted devices."""
    user_agent = request.headers.get("User-Agent", "")
    success = trust_device(body.device_id, user_agent)
    if not success:
        raise HTTPException(status_code=409, detail="该设备已在信任或黑名单中")

    refresh_token = create_refresh_token(body.device_id)
    return TrustDeviceResponse(message="设备已信任", refresh_token=refresh_token)


@router.post("/blacklist-device", response_model=BlacklistDeviceResponse)
async def blacklist_device_endpoint(
    body: DeviceRequest,
    request: Request,
    _token: str = Depends(require_auth),
):
    """Blacklist the current device. It will never get refresh tokens or trust prompts."""
    user_agent = request.headers.get("User-Agent", "")
    success = blacklist_device(body.device_id, user_agent)
    if not success:
        raise HTTPException(status_code=409, detail="该设备已在信任或黑名单中")

    return BlacklistDeviceResponse(message="设备已加入黑名单")


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token_endpoint(body: RefreshRequest):
    """Refresh access token using a refresh token. Only for trusted devices."""
    device_id = verify_refresh_token(body.refresh_token)
    if not device_id:
        raise HTTPException(status_code=401, detail="Refresh token 无效或已过期")

    if not is_device_trusted(device_id):
        raise HTTPException(status_code=401, detail="设备信任已撤销")

    update_last_used(device_id)
    new_token = create_token()
    new_refresh_token = create_refresh_token(device_id)
    return RefreshResponse(token=new_token, refresh_token=new_refresh_token)
