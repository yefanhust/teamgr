import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends, Response
from pydantic import BaseModel
from app.config import get_auth_password
from app.middleware.auth_middleware import (
    create_token, verify_token, create_refresh_token,
    verify_refresh_token, require_auth, ACCESS_COOKIE_NAME,
    TOKEN_EXPIRE_HOURS,
)
from app.middleware.rate_limiter import (
    check_login_rate_limit, ban_manager, get_client_ip
)
from app.services.device_trust import (
    is_device_trusted, is_device_blacklisted, get_device_status,
    trust_device, blacklist_device, update_last_used, auto_adopt_device,
    get_active_trusted_by_ua,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

# --- HTTP-only cookie for refresh token ---
# Safari on iOS aggressively clears localStorage (ITP), which loses the
# refresh token and forces trusted devices to re-enter the password.
# Storing the refresh token in an HTTP-only cookie survives this clearing.
REFRESH_COOKIE_NAME = "teamgr_refresh"
REFRESH_COOKIE_MAX_AGE = 30 * 24 * 3600  # 30 days


def _set_refresh_cookie(response: Response, refresh_token: str):
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        samesite="lax",
        max_age=REFRESH_COOKIE_MAX_AGE,
        path="/api/auth",
    )


def _clear_refresh_cookie(response: Response):
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path="/api/auth")


# --- HTTP-only cookie for access token ---
# When Safari clears localStorage, the Bearer header token is lost.
# Storing it as a cookie lets the backend authenticate without any frontend JS changes.
ACCESS_COOKIE_MAX_AGE = TOKEN_EXPIRE_HOURS * 3600


def _set_access_cookie(response: Response, access_token: str):
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=access_token,
        httponly=True,
        samesite="lax",
        max_age=ACCESS_COOKIE_MAX_AGE,
        path="/api",
    )


def _clear_access_cookie(response: Response):
    response.delete_cookie(key=ACCESS_COOKIE_NAME, path="/api")


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
    token: Optional[str] = None


class DeviceRequest(BaseModel):
    device_id: str


class TrustDeviceResponse(BaseModel):
    message: str
    refresh_token: str


class BlacklistDeviceResponse(BaseModel):
    message: str


class RefreshRequest(BaseModel):
    refresh_token: Optional[str] = None


class RefreshResponse(BaseModel):
    token: str
    refresh_token: str


@router.get("/status", response_model=StatusResponse)
async def auth_status(request: Request, response: Response):
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

    # Fallback: check access token cookie (Safari clears localStorage but not cookies)
    if not authenticated:
        access_cookie = request.cookies.get(ACCESS_COOKIE_NAME)
        if access_cookie:
            authenticated = verify_token(access_cookie)

    # If no password required, always "authenticated"
    if not password_configured:
        authenticated = True

    # Auto-refresh from refresh cookie for trusted devices.
    # This handles when BOTH localStorage and access cookie have expired.
    if not authenticated and password_configured:
        refresh_cookie = request.cookies.get(REFRESH_COOKIE_NAME)
        if refresh_cookie:
            device_id = verify_refresh_token(refresh_cookie)
            if device_id and is_device_trusted(device_id):
                update_last_used(device_id)
                new_token = create_token()
                new_refresh = create_refresh_token(device_id)
                _set_refresh_cookie(response, new_refresh)
                _set_access_cookie(response, new_token)
                return StatusResponse(
                    password_configured=True,
                    authenticated=True,
                    token=new_token,
                )

    # Last resort: User-Agent matches a trusted device (within 30 days).
    # This handles iOS Safari where self-signed certs may prevent cookie persistence.
    # No tokens or cookies needed — just the User-Agent header.
    if not authenticated and password_configured:
        user_agent = request.headers.get("User-Agent", "")
        if user_agent:
            trusted_entry = get_active_trusted_by_ua(user_agent)
            if trusted_entry:
                device_id = trusted_entry["device_id"]
                update_last_used(device_id)
                new_token = create_token()
                new_refresh = create_refresh_token(device_id)
                _set_refresh_cookie(response, new_refresh)
                _set_access_cookie(response, new_token)
                logger.info(
                    f"Auto-login via User-Agent: "
                    f"{trusted_entry.get('device_name')}"
                )
                return StatusResponse(
                    password_configured=True,
                    authenticated=True,
                    token=new_token,
                )

    return StatusResponse(
        password_configured=password_configured,
        authenticated=authenticated,
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
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
    _set_access_cookie(response, token)

    if body.device_id:
        status = get_device_status(body.device_id)

        if status == "trusted":
            update_last_used(body.device_id)
            refresh_token = create_refresh_token(body.device_id)
            _set_refresh_cookie(response, refresh_token)
            return LoginResponse(
                token=token, message="登录成功",
                refresh_token=refresh_token, device_trusted=True,
            )

        if status == "blacklisted":
            return LoginResponse(
                token=token, message="登录成功",
                device_blacklisted=True,
            )

        # Unknown device_id — but maybe the same physical device
        # accessed via a different origin (IP change → new localStorage → new UUID).
        # If a trusted entry with the same device_name exists, auto-adopt.
        user_agent = request.headers.get("User-Agent", "")
        if auto_adopt_device(body.device_id, user_agent):
            update_last_used(body.device_id)
            refresh_token = create_refresh_token(body.device_id)
            _set_refresh_cookie(response, refresh_token)
            return LoginResponse(
                token=token, message="登录成功",
                refresh_token=refresh_token, device_trusted=True,
            )

    # Truly unknown device or no device_id — frontend decides what to show
    return LoginResponse(token=token, message="登录成功")


@router.post("/trust-device", response_model=TrustDeviceResponse)
async def trust_device_endpoint(
    body: DeviceRequest,
    request: Request,
    response: Response,
    _token: str = Depends(require_auth),
):
    """Trust the current device. Idempotent: re-trusting returns refresh_token."""
    user_agent = request.headers.get("User-Agent", "")
    success = trust_device(body.device_id, user_agent)
    if not success:
        raise HTTPException(status_code=409, detail="该设备在黑名单中，无法信任")

    refresh_token = create_refresh_token(body.device_id)
    _set_refresh_cookie(response, refresh_token)
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
async def refresh_token_endpoint(
    body: RefreshRequest, request: Request, response: Response,
):
    """Refresh access token using a refresh token. Only for trusted devices.
    Accepts refresh token from body or HTTP-only cookie (for Safari).
    """
    rt = body.refresh_token or request.cookies.get(REFRESH_COOKIE_NAME)
    if not rt:
        raise HTTPException(status_code=401, detail="Refresh token 无效或已过期")

    device_id = verify_refresh_token(rt)
    if not device_id:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="Refresh token 无效或已过期")

    if not is_device_trusted(device_id):
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="设备信任已撤销")

    update_last_used(device_id)
    new_token = create_token()
    new_refresh_token = create_refresh_token(device_id)
    _set_refresh_cookie(response, new_refresh_token)
    _set_access_cookie(response, new_token)
    return RefreshResponse(token=new_token, refresh_token=new_refresh_token)


@router.post("/logout")
async def logout(response: Response):
    """Clear all auth cookies."""
    _clear_refresh_cookie(response)
    _clear_access_cookie(response)
    return {"message": "已退出"}
