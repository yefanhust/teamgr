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


# All scheduler job types with display labels
SCHEDULER_TYPES = {
    "daily_scheduled_queries": "每日定时查询（数据生成）",
    "daily_idea_aggregation": "灵感洞见聚合",
    "daily_todo_analysis": "任务效率分析",
    "daily_duration_stats": "任务耗时统计",
    "repeat_todo_check": "周期任务自动创建",
    "daily_backup": "数据库备份",
    "daily_tag_organize": "人才卡标签自动整理",
}

SCHEDULER_DESCRIPTIONS = {
    "daily_scheduled_queries": "执行预设的人才查询问题，生成查询结果供推送使用",
    "daily_idea_aggregation": "对近期灵感进行 AI 聚合分析，生成洞见摘要",
    "daily_todo_analysis": "分析任务完成效率，生成统计报告",
    "daily_duration_stats": "统计已完成任务的实际耗时数据",
    "repeat_todo_check": "检查设置了重复规则的已完成任务，自动创建下一周期的待办（如每日/每周/每月重复）",
    "daily_backup": "将数据库备份到腾讯云 COS",
    "daily_tag_organize": "每日自动执行人才卡标签一键整理（合并同义标签、建立层级分类）",
}

_SCHEDULER_DEFAULTS = {
    "daily_scheduled_queries": {"cron_hour": 5, "cron_minute": 0},
    "daily_idea_aggregation": {"cron_hour": 3, "cron_minute": 0},
    "daily_todo_analysis": {"cron_hour": 3, "cron_minute": 30},
    "daily_duration_stats": {"cron_hour": 3, "cron_minute": 35},
    "repeat_todo_check": {"interval_hours": 1},
    "daily_backup": {"cron_hour": 3, "cron_minute": 0},
    "daily_tag_organize": {"cron_hour": 22, "cron_minute": 0},
}


def get_scheduler_config() -> dict:
    """Get scheduler config, merging saved values with defaults."""
    cfg = get_config()
    saved = cfg.get("schedulers", {})
    result = {}
    for key, defaults in _SCHEDULER_DEFAULTS.items():
        if key == "daily_backup":
            backup = cfg.get("backup", {})
            result[key] = {
                "cron_hour": backup.get("cron_hour", 3),
                "cron_minute": backup.get("cron_minute", 0),
            }
        else:
            result[key] = {**defaults, **saved.get(key, {})}
    return result


def save_scheduler_config(schedulers: dict):
    """Save scheduler config to memory and file."""
    cfg = get_config()

    # Separate backup config
    backup_data = schedulers.pop("daily_backup", None)
    cfg["schedulers"] = schedulers

    if backup_data:
        backup = cfg.setdefault("backup", {"enabled": False})
        backup["cron_hour"] = backup_data.get("cron_hour", 3)
        backup["cron_minute"] = backup_data.get("cron_minute", 0)

    actual_path = _get_config_file_path()
    if actual_path:
        try:
            with open(actual_path, "r", encoding="utf-8") as f:
                file_cfg = yaml.safe_load(f) or {}
            file_cfg["schedulers"] = schedulers
            if backup_data:
                file_backup = file_cfg.setdefault("backup", {})
                file_backup["cron_hour"] = backup_data.get("cron_hour", 3)
                file_backup["cron_minute"] = backup_data.get("cron_minute", 0)
            with open(actual_path, "w", encoding="utf-8") as f:
                yaml.dump(file_cfg, f, allow_unicode=True, default_flow_style=False)
        except OSError:
            pass


def get_backup_config() -> dict:
    cfg = get_config()
    return cfg.get("backup", {"enabled": False, "cron_hour": 3, "cron_minute": 0})


def get_notification_config() -> dict:
    cfg = get_config()
    return cfg.get("notification", {"enabled": False})


# Default cron times for triggers (used when migrating old format)
_DEFAULT_TRIGGER_TIMES = {
    "scheduled_query": (5, 0),
    "idea_insight": (3, 30),
    "todo_analysis": (4, 0),
    "todo_deadline": (8, 0),
    "todo_daily_list": (8, 5),
    "scholar_scheduled": (6, 30),
}

# All available trigger types with display labels
TRIGGER_TYPES = {
    "scheduled_query": "每日定时查询",
    "idea_insight": "灵感洞见推送",
    "todo_analysis": "任务效率分析",
    "todo_deadline": "任务截止提醒",
    "todo_daily_list": "每日任务清单",
    "scholar_scheduled": "龙图阁定时报告",
}


def get_notification_bots() -> list:
    """Get notification bots list, with backward compatibility for old format."""
    cfg = get_notification_config()
    if not cfg.get("enabled"):
        return []

    # New format: bots list
    if "bots" in cfg:
        return cfg.get("bots", [])

    # Old format: channels + triggers → convert to bots
    channels = cfg.get("channels", {})
    triggers = cfg.get("triggers", {})
    wecom = channels.get("wecom_webhook", {})
    if wecom.get("enabled") and wecom.get("webhook_url"):
        functions = []
        for trigger_name, enabled in triggers.items():
            if enabled:
                h, m = _DEFAULT_TRIGGER_TIMES.get(trigger_name, (0, 0))
                functions.append({
                    "trigger": trigger_name,
                    "cron_hour": h,
                    "cron_minute": m,
                })
        return [{
            "id": "default",
            "name": "工作通知",
            "channel": "wecom",
            "webhook_url": wecom["webhook_url"],
            "enabled": True,
            "functions": functions,
        }]

    return []


def _get_config_file_path() -> str | None:
    """Return the actual config file path, or None if not found."""
    config_path = os.environ.get("TEAMGR_CONFIG", "/app/config/config.yaml")
    local_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "config", "config.yaml"
    )
    if os.path.exists(config_path):
        return config_path
    if os.path.exists(local_path):
        return local_path
    return None


# ========== Instructions (prompts) — stored in instructions.yaml ==========

_instructions = None


def _get_instructions_path() -> str:
    """Return instructions.yaml path, next to config.yaml."""
    cfg_path = _get_config_file_path()
    if cfg_path:
        return os.path.join(os.path.dirname(cfg_path), "instructions.yaml")
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "config", "instructions.yaml"
    )


def load_instructions() -> dict:
    global _instructions
    path = _get_instructions_path()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            _instructions = yaml.safe_load(f) or {}
    else:
        _instructions = {}
    return _instructions


def get_instructions() -> dict:
    if _instructions is None:
        return load_instructions()
    return _instructions


def get_instruction(key: str, default: str = "") -> str:
    return get_instructions().get(key, "") or default


def save_instruction(key: str, value: str):
    instructions = get_instructions()
    instructions[key] = value
    path = _get_instructions_path()

    class _BlockDumper(yaml.Dumper):
        pass

    _BlockDumper.add_representer(str, lambda d, s: d.represent_scalar(
        'tag:yaml.org,2002:str', s, style='|' if '\n' in s else None
    ))
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(instructions, f, Dumper=_BlockDumper, allow_unicode=True, default_flow_style=False)


def save_notification_bots(bots: list):
    """Save notification bots to config (in memory + persist to file)."""
    cfg = get_config()
    notif = cfg.setdefault("notification", {"enabled": True})
    notif["bots"] = bots
    # Remove old format keys if present
    notif.pop("channels", None)
    notif.pop("triggers", None)
    notif["enabled"] = True

    actual_path = _get_config_file_path()
    if actual_path:
        try:
            with open(actual_path, "r", encoding="utf-8") as f:
                file_cfg = yaml.safe_load(f) or {}
            file_notif = file_cfg.setdefault("notification", {})
            file_notif["enabled"] = True
            file_notif["bots"] = bots
            file_notif.pop("channels", None)
            file_notif.pop("triggers", None)
            with open(actual_path, "w", encoding="utf-8") as f:
                yaml.dump(file_cfg, f, allow_unicode=True, default_flow_style=False)
        except OSError:
            pass


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
    "scholar-categorize": "大学士-历史对话分类",
    "project-summary": "项目概览生成",
    "project-update-parse": "项目进展解析",
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
