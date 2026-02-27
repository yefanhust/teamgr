import os
import yaml
import logging

logger = logging.getLogger(__name__)

_config = None
_config_path = os.environ.get(
    "TEAMGR_CONFIG", "/app/config/config.yaml"
)

# Also check local development path
_local_config_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config", "config.yaml"
)


def load_config() -> dict:
    global _config
    if _config is not None:
        return _config

    config_path = _config_path
    if not os.path.exists(config_path):
        config_path = _local_config_path

    if not os.path.exists(config_path):
        logger.warning(
            f"Config file not found at {_config_path} or {_local_config_path}. "
            "Using empty config. Copy config.example.yaml to config.yaml and fill in values."
        )
        _config = {}
        return _config

    with open(config_path, "r", encoding="utf-8") as f:
        _config = yaml.safe_load(f) or {}

    return _config


def get_config() -> dict:
    if _config is None:
        return load_config()
    return _config


def reload_config() -> dict:
    global _config
    _config = None
    return load_config()


def get_auth_password() -> str:
    cfg = get_config()
    return cfg.get("auth", {}).get("password", "")


def get_jwt_secret() -> str:
    cfg = get_config()
    return cfg.get("auth", {}).get("jwt_secret", "teamgr-default-secret")


def get_gemini_config() -> dict:
    cfg = get_config()
    return cfg.get("gemini", {})


def get_cos_config() -> dict:
    cfg = get_config()
    return cfg.get("cos", {})


def get_security_config() -> dict:
    cfg = get_config()
    return cfg.get("security", {
        "rate_limit_per_minute": 5,
        "ban_thresholds": [
            {"fails": 5, "duration_minutes": 30},
            {"fails": 10, "duration_minutes": 120},
            {"fails": 20, "duration_minutes": 1440},
        ]
    })


def get_server_config() -> dict:
    cfg = get_config()
    return cfg.get("server", {"host": "0.0.0.0", "port": 8000})


def get_backup_config() -> dict:
    cfg = get_config()
    return cfg.get("backup", {"enabled": False, "cron_hour": 3, "cron_minute": 0})
