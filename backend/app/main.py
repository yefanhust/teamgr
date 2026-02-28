import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import load_config, get_auth_password, get_gemini_config
from app.database import init_db, SessionLocal
from app.routers import auth, talents, entry, stats, chat
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

    # Clean up stuck "processing" entries from previous runs
    from app.models.talent import EntryLog, Talent
    _db = SessionLocal()
    try:
        stuck = _db.query(EntryLog).filter(EntryLog.status == "processing").all()
        for entry in stuck:
            entry.status = "failed"
            logger.warning(f"Marked stuck entry {entry.id} as failed (from previous run)")
        if stuck:
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
    from app.config import get_config
    import yaml

    model = body.get("model", "")
    available = get_config().get("gemini", {}).get("available_models", [])

    if model not in available:
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
