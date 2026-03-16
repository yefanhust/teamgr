"""
Multi-device trust service with whitelist and blacklist.

Data stored in config/trusted_devices.json:
{
  "trusted": [ {device_id, device_name, trusted_at, last_used_at}, ... ],
  "blacklisted": [ {device_id, device_name, blacklisted_at}, ... ]
}

- Trusted devices get 30-day refresh tokens.
- Blacklisted devices always require password, never prompted again.
- Unknown devices are prompted with: trust / skip / blacklist.
- Management: edit or delete config/trusted_devices.json on the server.
"""
import json
import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_container_path = "/app/config/trusted_devices.json"
_local_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config", "trusted_devices.json"
)


def _get_file_path() -> str:
    config_env = os.environ.get("TEAMGR_CONFIG", "")
    if config_env:
        return os.path.join(os.path.dirname(config_env), "trusted_devices.json")
    if os.path.exists(os.path.dirname(_container_path)):
        return _container_path
    return _local_path


def _read() -> dict:
    path = _get_file_path()
    if not os.path.exists(path):
        return {"trusted": [], "blacklisted": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "trusted" in data:
            return data
        # Migrate from old single-device format
        if isinstance(data, dict) and "device_id" in data:
            return {"trusted": [data], "blacklisted": []}
    except (json.JSONDecodeError, OSError):
        pass
    return {"trusted": [], "blacklisted": []}


def _write(data: dict):
    path = _get_file_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_device_status(device_id: str) -> str:
    """Return 'trusted', 'blacklisted', or 'unknown'."""
    data = _read()
    for d in data.get("trusted", []):
        if d.get("device_id") == device_id:
            return "trusted"
    for d in data.get("blacklisted", []):
        if d.get("device_id") == device_id:
            return "blacklisted"
    return "unknown"


def is_device_trusted(device_id: str) -> bool:
    return get_device_status(device_id) == "trusted"


def is_device_blacklisted(device_id: str) -> bool:
    return get_device_status(device_id) == "blacklisted"


def trust_device(device_id: str, user_agent: str) -> bool:
    """Add device to trusted list. Returns False if already trusted or blacklisted."""
    data = _read()
    status = get_device_status(device_id)
    if status != "unknown":
        return False
    now = datetime.now(timezone.utc).isoformat()
    device_name = _parse_device_name(user_agent)
    data["trusted"].append({
        "device_id": device_id,
        "device_name": device_name,
        "trusted_at": now,
        "last_used_at": now,
    })
    _write(data)
    logger.info(f"Device trusted: {device_name} ({device_id[:8]}...)")
    return True


def blacklist_device(device_id: str, user_agent: str) -> bool:
    """Add device to blacklist. Returns False if already known."""
    data = _read()
    status = get_device_status(device_id)
    if status != "unknown":
        return False
    now = datetime.now(timezone.utc).isoformat()
    device_name = _parse_device_name(user_agent)
    data["blacklisted"].append({
        "device_id": device_id,
        "device_name": device_name,
        "blacklisted_at": now,
    })
    _write(data)
    logger.info(f"Device blacklisted: {device_name} ({device_id[:8]}...)")
    return True


def update_last_used(device_id: str):
    data = _read()
    for d in data.get("trusted", []):
        if d.get("device_id") == device_id:
            d["last_used_at"] = datetime.now(timezone.utc).isoformat()
            _write(data)
            return


def _parse_device_name(user_agent: str) -> str:
    ua = user_agent.lower()
    if "iphone" in ua:
        return "iPhone"
    if "ipad" in ua:
        return "iPad"
    if "android" in ua:
        return "Android"
    if "macintosh" in ua or "mac os" in ua:
        return "Mac"
    if "windows" in ua:
        return "Windows PC"
    if "linux" in ua:
        return "Linux"
    return "Unknown Device"
