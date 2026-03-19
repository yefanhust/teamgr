import asyncio
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import load_config, get_auth_password, get_gemini_config
from app.database import init_db, SessionLocal
from app.routers import auth, talents, entry, stats, chat, ideas, todos, notification, scholar, backup
from app.services.backup_service import setup_backup_scheduler

# ANSI color codes
_RESET = "\033[0m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_BLUE = "\033[34m"
_CYAN = "\033[36m"
_BOLD = "\033[1m"
_DIM = "\033[2m"

_LEVEL_COLORS = {
    "DEBUG": _DIM,
    "INFO": _GREEN,
    "WARNING": f"{_BOLD}{_YELLOW}",
    "ERROR": f"{_BOLD}{_RED}",
    "CRITICAL": f"{_BOLD}{_RED}",
}


class ColorFormatter(logging.Formatter):
    def format(self, record):
        color = _LEVEL_COLORS.get(record.levelname, "")
        record.levelname_colored = f"{color}{record.levelname}{_RESET}"
        record.name_colored = f"{_CYAN}{record.name}{_RESET}"
        record.asctime_colored = f"{_DIM}%(asctime)s{_RESET}"
        return super().format(record)


# Configure logging with colors
_handler = logging.StreamHandler()
_handler.setFormatter(ColorFormatter(
    f"{_DIM}%(asctime)s{_RESET} [%(levelname_colored)s] %(name_colored)s: %(message)s"
))
logging.root.handlers = [_handler]
logging.root.setLevel(logging.INFO)
logger = logging.getLogger(__name__)

_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    # Startup
    load_config()
    init_db()

    # Handle entries from previous runs
    from app.models.talent import EntryLog, Talent
    _db = SessionLocal()
    try:
        # Mark stuck "processing" entries as failed
        stuck = _db.query(EntryLog).filter(EntryLog.status == "processing").all()
        for entry in stuck:
            entry.status = "failed"
            logger.warning(f"Marked stuck entry {entry.id} as failed (from previous run)")
        if stuck:
            _db.commit()

        # Resume "uploaded" PDF entries that weren't processed yet
        from app.routers.entry import _process_pdf_from_file_bg, PDF_UPLOAD_DIR
        uploaded = _db.query(EntryLog).filter(EntryLog.status == "uploaded").all()
        for entry in uploaded:
            pdf_path = os.path.join(PDF_UPLOAD_DIR, f"{entry.id}.pdf")
            if os.path.exists(pdf_path):
                asyncio.create_task(_process_pdf_from_file_bg(entry.id))
                logger.info(f"Resumed uploaded PDF entry {entry.id} for background processing")
            else:
                entry.status = "failed"
                entry.llm_response = '{"error": "PDF file lost during server restart"}'
                logger.warning(f"Uploaded entry {entry.id} has no PDF file, marked as failed")
        if uploaded:
            _db.commit()

        # Clean up card_data: remove schema definitions stored as values
        all_talents = _db.query(Talent).all()
        cleaned = 0
        for t in all_talents:
            if not t.card_data:
                continue
            card = dict(t.card_data)
            changed = False
            for k, v in list(card.items()):
                if isinstance(v, dict) and "type" in v and ("properties" in v or "items" in v):
                    card[k] = [] if v.get("type") == "array" else {}
                    changed = True
            if changed:
                t.card_data = card
                cleaned += 1
        if cleaned:
            _db.commit()
            logger.info(f"Cleaned schema-as-value from {cleaned} talent card(s)")
    finally:
        _db.close()

    # Check password config
    password = get_auth_password()
    if not password:
        logger.warning(
            f"\n{_BOLD}{_YELLOW}{'=' * 60}{_RESET}\n"
            f"{_BOLD}{_RED}  NO PASSWORD CONFIGURED{_RESET}\n"
            f"{_YELLOW}  The site is running in unprotected mode.{_RESET}\n"
            f"  Fix: set {_CYAN}auth.password{_RESET} in {_CYAN}config/config.yaml{_RESET}\n"
            f"  Example:\n"
            f"    {_DIM}auth:{_RESET}\n"
            f"    {_DIM}  password: \"your-strong-password-here\"{_RESET}\n"
            f"  Then restart the web service.\n"
            f"{_BOLD}{_YELLOW}{'=' * 60}{_RESET}"
        )

    # Check Gemini config
    gemini_cfg = get_gemini_config()
    api_key = gemini_cfg.get("api_key", "")
    if not api_key or api_key == "your-gemini-api-key-here":
        logger.warning(
            f"{_BOLD}{_YELLOW}Gemini API key not configured.{_RESET} LLM features will not work.\n"
            f"  Fix: set {_CYAN}gemini.api_key{_RESET} in {_CYAN}config/config.yaml{_RESET}"
        )

    # Setup backup scheduler
    _scheduler = setup_backup_scheduler()

    # Setup scheduled jobs using config
    from app.config import get_scheduler_config
    from app.services.scheduled_query_service import run_scheduled_queries
    if _scheduler is None:
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            _scheduler = BackgroundScheduler()
            _scheduler.start()
        except ImportError:
            logger.warning("APScheduler not installed. Scheduled queries disabled.")
    if _scheduler:
        sc = get_scheduler_config()

        sq = sc.get("daily_scheduled_queries", {})
        _scheduler.add_job(
            run_scheduled_queries,
            "cron",
            hour=sq.get("cron_hour", 5),
            minute=sq.get("cron_minute", 0),
            id="daily_scheduled_queries",
        )
        logger.info(f"Scheduled query job registered: daily at {sq.get('cron_hour', 5):02d}:{sq.get('cron_minute', 0):02d}")

        from app.routers.ideas import run_daily_idea_aggregation_sync
        ia = sc.get("daily_idea_aggregation", {})
        _scheduler.add_job(
            run_daily_idea_aggregation_sync,
            "cron",
            hour=ia.get("cron_hour", 3),
            minute=ia.get("cron_minute", 0),
            id="daily_idea_aggregation",
        )
        logger.info(f"Idea aggregation job registered: daily at {ia.get('cron_hour', 3):02d}:{ia.get('cron_minute', 0):02d}")

        from app.routers.todos import run_daily_todo_analysis_sync
        ta = sc.get("daily_todo_analysis", {})
        _scheduler.add_job(
            run_daily_todo_analysis_sync,
            "cron",
            hour=ta.get("cron_hour", 3),
            minute=ta.get("cron_minute", 30),
            id="daily_todo_analysis",
        )
        logger.info(f"Todo analysis job registered: daily at {ta.get('cron_hour', 3):02d}:{ta.get('cron_minute', 30):02d}")

        from app.routers.todos import run_daily_duration_stats
        ds = sc.get("daily_duration_stats", {})
        _scheduler.add_job(
            run_daily_duration_stats,
            "cron",
            hour=ds.get("cron_hour", 3),
            minute=ds.get("cron_minute", 35),
            id="daily_duration_stats",
        )
        logger.info(f"Duration stats job registered: daily at {ds.get('cron_hour', 3):02d}:{ds.get('cron_minute', 35):02d}")

        from app.routers.todos import check_and_spawn_repeat_todos_sync
        rt = sc.get("repeat_todo_check", {})
        _scheduler.add_job(
            check_and_spawn_repeat_todos_sync,
            "interval",
            hours=rt.get("interval_hours", 1),
            id="repeat_todo_check",
        )
        logger.info(f"Repeat todo check job registered: every {rt.get('interval_hours', 1)} hour(s)")

        from app.routers.talents import run_daily_tag_organize, check_missed_tag_organize
        to = sc.get("daily_tag_organize", {})
        _scheduler.add_job(
            run_daily_tag_organize,
            "cron",
            hour=to.get("cron_hour", 22),
            minute=to.get("cron_minute", 0),
            id="daily_tag_organize",
        )
        logger.info(f"Tag organize job registered: daily at {to.get('cron_hour', 22):02d}:{to.get('cron_minute', 0):02d}")
        check_missed_tag_organize(_scheduler)

        # Scholar scheduled questions — one job per enabled question
        from app.services.scholar_scheduled_service import seed_default_scheduled_questions, refresh_scholar_jobs, check_missed_executions
        seed_default_scheduled_questions()
        refresh_scholar_jobs(_scheduler)
        check_missed_executions(_scheduler)

        # Notification delivery jobs (龙图阁 — per-bot per-function scheduling)
        from app.services.notification_scheduler import refresh_notification_jobs
        refresh_notification_jobs(_scheduler)

    logger.info("TeaMgr server started successfully")

    yield

    # Shutdown
    if _scheduler:
        _scheduler.shutdown(wait=False)
    logger.info("TeaMgr server shutting down")


app = FastAPI(
    title="TeaMgr - 人才卡管理系统",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(auth.router)
app.include_router(talents.router)
app.include_router(entry.router)
app.include_router(stats.router)
app.include_router(chat.router)
app.include_router(ideas.router)
app.include_router(todos.router)
app.include_router(notification.router)
app.include_router(scholar.router)
app.include_router(backup.router)


# Settings API for model switching
@app.get("/api/settings/model")
async def get_model_settings():
    from app.services.llm_service import get_current_model_name, get_available_models
    return {
        "current_model": get_current_model_name(),
        "available_models": get_available_models(),
    }


@app.put("/api/settings/model")
async def update_model_settings(body: dict):
    from app.config import get_config, get_local_models_config
    import yaml

    model = body.get("model", "")
    gemini_models = get_config().get("gemini", {}).get("available_models", [])
    local_names = [m["name"] for m in get_local_models_config()]
    all_valid = gemini_models + local_names

    if model not in all_valid:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"不支持的模型: {model}")

    # Update config in memory
    cfg = get_config()
    cfg.setdefault("gemini", {})["current_model"] = model

    # Also persist to config file
    config_path = os.environ.get("TEAMGR_CONFIG", "/app/config/config.yaml")
    local_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "config", "config.yaml"
    )
    actual_path = config_path if os.path.exists(config_path) else local_path

    if os.path.exists(actual_path):
        try:
            with open(actual_path, "r", encoding="utf-8") as f:
                file_cfg = yaml.safe_load(f) or {}
            file_cfg.setdefault("gemini", {})["current_model"] = model
            with open(actual_path, "w", encoding="utf-8") as f:
                yaml.dump(file_cfg, f, allow_unicode=True, default_flow_style=False)
        except OSError:
            pass  # config volume may be read-only

    # Reset model instance
    from app.services import llm_service
    llm_service._model_instance = None

    return {"current_model": model}


@app.get("/api/settings/model-defaults")
async def get_model_defaults_api():
    from app.config import LLM_CALL_TYPES, get_model_defaults
    from app.services.llm_service import get_current_model_name, get_available_models
    return {
        "call_types": LLM_CALL_TYPES,
        "defaults": get_model_defaults(),
        "global_model": get_current_model_name(),
        "available_models": get_available_models(),
    }


@app.put("/api/settings/model-defaults")
async def update_model_defaults_api(body: dict):
    from app.config import LLM_CALL_TYPES, set_model_defaults
    defaults = body.get("defaults", {})
    # Only keep valid call types
    filtered = {k: v for k, v in defaults.items() if k in LLM_CALL_TYPES}
    set_model_defaults(filtered)
    return {"defaults": filtered}


@app.get("/api/settings/schedulers")
async def get_scheduler_settings():
    from app.config import SCHEDULER_TYPES, SCHEDULER_DESCRIPTIONS, get_scheduler_config
    return {
        "scheduler_types": SCHEDULER_TYPES,
        "scheduler_descriptions": SCHEDULER_DESCRIPTIONS,
        "schedulers": get_scheduler_config(),
    }


@app.put("/api/settings/schedulers")
async def update_scheduler_settings(body: dict):
    from app.config import SCHEDULER_TYPES, save_scheduler_config, get_scheduler_config
    schedulers = body.get("schedulers", {})
    # Only keep valid scheduler types
    filtered = {k: v for k, v in schedulers.items() if k in SCHEDULER_TYPES}
    save_scheduler_config(filtered)

    # Reschedule running jobs
    if _scheduler:
        sc = get_scheduler_config()
        for job_id, cfg in sc.items():
            try:
                if "interval_hours" in cfg:
                    _scheduler.reschedule_job(job_id, trigger="interval", hours=cfg["interval_hours"])
                elif "day_of_week" in cfg:
                    _scheduler.reschedule_job(job_id, trigger="cron", day_of_week=cfg["day_of_week"], hour=cfg["cron_hour"], minute=cfg["cron_minute"])
                elif "day_of_month" in cfg:
                    _scheduler.reschedule_job(job_id, trigger="cron", day=cfg["day_of_month"], hour=cfg["cron_hour"], minute=cfg["cron_minute"])
                else:
                    _scheduler.reschedule_job(job_id, trigger="cron", hour=cfg["cron_hour"], minute=cfg["cron_minute"])
                logger.info(f"Rescheduled job {job_id}: {cfg}")
            except Exception as e:
                logger.warning(f"Failed to reschedule {job_id}: {e}")

    return {"schedulers": get_scheduler_config()}


# Serve frontend static files
# In Docker: /app/frontend/dist; In local dev: ../../frontend/dist relative to backend/
_possible_static_dirs = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist"),
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend", "dist"),
    "/app/frontend/dist",
]
STATIC_DIR = next((d for d in _possible_static_dirs if os.path.exists(d)), _possible_static_dirs[-1])

if os.path.exists(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # Serve index.html for all non-API routes (SPA routing)
        file_path = os.path.join(STATIC_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(
            os.path.join(STATIC_DIR, "index.html"),
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
