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


def get_local_models_config() -> list:
    cfg = get_config()
    return cfg.get("local_models", [])


def get_backup_config() -> dict:
    cfg = get_config()
    return cfg.get("backup", {"enabled": False, "cron_hour": 3, "cron_minute": 0})


# All LLM call types and their display labels
LLM_CALL_TYPES = {
    "text-entry": "信息录入（文本）",
    "pdf-parse": "PDF简历解析",
    "image-parse": "图片解析",
    "semantic-search": "语义搜索",
    "chat-analyze": "人才查询-维度分析",
    "chat-answer": "人才查询-回答生成",
    "organize-tags": "标签整理",
    "idea-classify": "灵感分类整理",
    "idea-insight": "灵感洞见生成",
    "todo-auto-tag": "任务自动打标",
    "todo-organize-tags": "任务标签整理",
    "todo-analysis": "任务完成效率分析",
}


def get_model_defaults() -> dict:
    """Return per-call-type model defaults. Missing keys use global current_model."""
    cfg = get_config()
    return cfg.get("model_defaults", {})


def set_model_defaults(defaults: dict):
    """Update per-call-type model defaults in memory and persist to config file."""
    cfg = get_config()
    cfg["model_defaults"] = defaults

    config_path = os.environ.get("TEAMGR_CONFIG", "/app/config/config.yaml")
    local_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "config", "config.yaml"
    )
    actual_path = config_path if os.path.exists(config_path) else local_path

    if os.path.exists(actual_path):
        try:
            import yaml
            with open(actual_path, "r", encoding="utf-8") as f:
                file_cfg = yaml.safe_load(f) or {}
            file_cfg["model_defaults"] = defaults
            with open(actual_path, "w", encoding="utf-8") as f:
                yaml.dump(file_cfg, f, allow_unicode=True, default_flow_style=False)
        except OSError:
            pass
