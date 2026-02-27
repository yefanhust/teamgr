import time
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)


class BanManager:
    """Manages progressive IP banning for failed login attempts."""

    def __init__(self, ban_thresholds=None):
        self.ban_thresholds = ban_thresholds or [
            {"fails": 5, "duration_minutes": 30},
            {"fails": 10, "duration_minutes": 120},
            {"fails": 20, "duration_minutes": 1440},
        ]
        # {ip: {"fail_count": int, "banned_until": datetime|None}}
        self._ip_state = defaultdict(lambda: {"fail_count": 0, "banned_until": None})

    def is_banned(self, ip: str) -> bool:
        state = self._ip_state[ip]
        if state["banned_until"] and datetime.utcnow() < state["banned_until"]:
            return True
        if state["banned_until"] and datetime.utcnow() >= state["banned_until"]:
            # Auto-unban
            state["banned_until"] = None
            state["fail_count"] = 0
        return False

    def get_ban_remaining(self, ip: str) -> int:
        """Returns remaining ban time in seconds, or 0."""
        state = self._ip_state[ip]
        if state["banned_until"] and datetime.utcnow() < state["banned_until"]:
            return int((state["banned_until"] - datetime.utcnow()).total_seconds())
        return 0

    def record_failure(self, ip: str):
        state = self._ip_state[ip]
        state["fail_count"] += 1
        count = state["fail_count"]

        # Check thresholds in reverse order (highest first)
        for threshold in sorted(self.ban_thresholds, key=lambda x: x["fails"], reverse=True):
            if count >= threshold["fails"]:
                duration = timedelta(minutes=threshold["duration_minutes"])
                state["banned_until"] = datetime.utcnow() + duration
                logger.warning(
                    f"IP {ip} banned for {threshold['duration_minutes']} minutes "
                    f"after {count} failed attempts"
                )
                break

    def record_success(self, ip: str):
        self._ip_state[ip] = {"fail_count": 0, "banned_until": None}


class RateLimiter:
    """Simple in-memory rate limiter per IP."""

    def __init__(self, max_requests: int = 5, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # {ip: [timestamp, timestamp, ...]}
        self._requests = defaultdict(list)

    def is_rate_limited(self, ip: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds
        # Clean old entries
        self._requests[ip] = [t for t in self._requests[ip] if t > window_start]
        return len(self._requests[ip]) >= self.max_requests

    def record_request(self, ip: str):
        self._requests[ip].append(time.time())


# Global instances
ban_manager = BanManager()
rate_limiter = RateLimiter()


def get_client_ip(request: Request) -> str:
    """Extract client IP, respecting X-Forwarded-For behind proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_login_rate_limit(request: Request):
    """Dependency to check rate limit and ban status for login endpoint."""
    ip = get_client_ip(request)

    if ban_manager.is_banned(ip):
        remaining = ban_manager.get_ban_remaining(ip)
        raise HTTPException(
            status_code=403,
            detail=f"IP已被临时封禁，请在{remaining // 60}分钟后重试"
        )

    if rate_limiter.is_rate_limited(ip):
        raise HTTPException(
            status_code=429,
            detail="请求过于频繁，请稍后重试"
        )

    rate_limiter.record_request(ip)
