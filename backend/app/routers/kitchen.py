import asyncio
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_kitchen_config, save_kitchen_config, get_instruction
from app.database import get_db, SessionLocal
from app.middleware.auth_middleware import require_auth
from app.models.kitchen import DailyMenu

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/kitchen", tags=["kitchen"])

_CN_TZ = timezone(timedelta(hours=8))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEASON_MAP = {
    1: "冬季", 2: "冬季", 3: "春季", 4: "春季", 5: "春季",
    6: "夏季", 7: "夏季", 8: "夏季", 9: "秋季", 10: "秋季",
    11: "秋季", 12: "冬季",
}

_WEEKDAY_MAP = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

DEFAULT_MENU_PROMPT = """\
你是一位专业的家庭营养师和厨师。请为以下家庭规划 {date}（{weekday}，{season}）的一日三餐。

家庭成员：
- 1个2岁宝宝
- {adult_count}个大人

要求：
1. 当前季节为{season}（{month}月），坐标中国上海，请选用当季应季食材
2. 食材必须是清美超市能买到的（常见蔬菜、肉类、豆制品、蛋奶、水产等家常食材）
3. 宝宝餐：软烂易嚼、少盐少油、营养均衡。2岁宝宝饮食禁忌：不能吃蜂蜜、整粒坚果、大块硬质食物、生鱼片等
4. 大人餐：家常菜风格，简单快手，营养美味
5. 口味要求：清淡为主，不做重口味菜。不要辣、不要麻，少油少盐。调料以生抽、醋、料酒、姜、葱等温和调料为主，不要使用辣椒、花椒、八角、豆瓣酱等刺激性调料
6. 尽量让宝宝和大人的部分食材共用，减少浪费
7. 每餐2-3道菜即可，不需要太复杂
8. 提供完整的购物清单，标注大致用量
{history_section}
请严格按照以下 JSON 格式返回（不要输出其他内容）：
{{
  "baby_meals": [
    {{
      "meal_type": "早餐",
      "dishes": [
        {{
          "name": "菜名",
          "ingredients": ["食材1 用量", "食材2 用量"],
          "steps": ["步骤1", "步骤2"],
          "tips": "宝宝饮食注意事项（可选）"
        }}
      ]
    }},
    {{"meal_type": "午餐", "dishes": [...]}},
    {{"meal_type": "晚餐", "dishes": [...]}}
  ],
  "adult_meals": [
    {{
      "meal_type": "早餐",
      "dishes": [
        {{
          "name": "菜名",
          "ingredients": ["食材1 用量", "食材2 用量"],
          "steps": ["步骤1", "步骤2"],
          "tips": "烹饪小贴士（可选）"
        }}
      ]
    }},
    {{"meal_type": "午餐", "dishes": [...]}},
    {{"meal_type": "晚餐", "dishes": [...]}}
  ],
  "shopping_list": [
    {{"category": "蔬菜", "items": ["西兰花 200g", "胡萝卜 1根"]}},
    {{"category": "肉类/水产", "items": ["鸡胸肉 300g"]}},
    {{"category": "豆制品/蛋奶", "items": ["鸡蛋 4个", "嫩豆腐 1盒"]}},
    {{"category": "主食", "items": ["大米", "面条"]}},
    {{"category": "调料", "items": ["生抽", "醋"]}}
  ]
}}"""


def _build_history_section(db: Session, target_date: date) -> str:
    """Build the recent history section for the prompt to avoid repetition."""
    week_ago = target_date - timedelta(days=7)
    recent_menus = (
        db.query(DailyMenu)
        .filter(DailyMenu.date >= week_ago, DailyMenu.date < target_date)
        .order_by(DailyMenu.date.desc())
        .all()
    )
    if not recent_menus:
        return ""

    lines = ["\n9. 以下是最近已做过的菜，请务必避免重复相同菜名和相同主食材组合，每天要有新鲜感："]
    for menu in recent_menus:
        if not menu.menu_data:
            continue
        dish_names = []
        for section in ("baby_meals", "adult_meals"):
            for meal in menu.menu_data.get(section, []):
                for dish in meal.get("dishes", []):
                    name = dish.get("name", "") if isinstance(dish, dict) else ""
                    if name and name not in dish_names:
                        dish_names.append(name)
        if dish_names:
            lines.append(f"   - {menu.date.strftime('%m/%d')}: {'、'.join(dish_names)}")

    return "\n".join(lines) + "\n"


async def _generate_menu_for_date(target_date: date, adult_count: int, db: Session) -> DailyMenu:
    """Generate a daily menu using LLM."""
    from app.services.llm_service import _call_model_text, _extract_json

    season = _SEASON_MAP[target_date.month]
    weekday = _WEEKDAY_MAP[target_date.weekday()]
    history_section = _build_history_section(db, target_date)

    custom_prompt = get_instruction("kitchen_daily_menu", "")
    prompt_template = custom_prompt or DEFAULT_MENU_PROMPT

    prompt = prompt_template.format(
        date=target_date.strftime("%Y年%m月%d日"),
        weekday=weekday,
        season=season,
        month=target_date.month,
        adult_count=adult_count,
        history_section=history_section,
    )

    raw_response = await _call_model_text(prompt, call_type="kitchen-menu")
    if not raw_response:
        raise HTTPException(status_code=500, detail="LLM 未返回内容，请检查 Gemini API 配置")

    try:
        menu_data = _extract_json(raw_response)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="LLM 返回的内容无法解析为 JSON")

    # Add metadata
    menu_data["date"] = target_date.isoformat()
    menu_data["season"] = season

    from app.services.llm_service import get_current_model_name
    model_name = get_current_model_name()

    # Upsert: replace existing menu for the same date
    existing = db.query(DailyMenu).filter(DailyMenu.date == target_date).first()
    if existing:
        existing.adult_count = adult_count
        existing.menu_data = menu_data
        existing.raw_response = raw_response
        existing.model_name = model_name
        existing.created_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing
    else:
        menu = DailyMenu(
            date=target_date,
            adult_count=adult_count,
            menu_data=menu_data,
            raw_response=raw_response,
            model_name=model_name,
        )
        db.add(menu)
        db.commit()
        db.refresh(menu)
        return menu


def _menu_to_dict(menu: DailyMenu) -> dict:
    return {
        "id": menu.id,
        "date": menu.date.isoformat(),
        "adult_count": menu.adult_count,
        "menu_data": menu.menu_data,
        "model_name": menu.model_name,
        "created_at": menu.created_at.isoformat() if menu.created_at else None,
    }


def _format_meal_section(meal: dict) -> str:
    """Format a single meal (e.g. breakfast) into text with readable formatting."""
    parts = []
    for d in meal.get("dishes", []):
        if not isinstance(d, dict):
            continue
        dish_lines = []
        dish_lines.append(f"🍳 {d.get('name', '')}")
        dish_lines.append("")
        ingredients = d.get("ingredients", [])
        if ingredients:
            dish_lines.append(f"食材：{'、'.join(ingredients)}")
            dish_lines.append("")
        dish_lines.append("做法：")
        for si, step in enumerate(d.get("steps", []), 1):
            dish_lines.append(f"  {si}. {step}")
        tips = d.get("tips", "")
        if tips:
            dish_lines.append("")
            dish_lines.append(f"💡 {tips}")
        parts.append("\n".join(dish_lines))
    return ("\n\n" + "─" * 20 + "\n\n").join(parts)


def _menu_to_bark_messages(menu: DailyMenu) -> list[tuple[str, str]]:
    """Convert menu to a list of (title, body) tuples for Bark push.

    Splits into multiple messages to stay under Bark's ~4KB body limit:
      1. 宝宝餐 early/lunch/dinner (one message per meal)
      2. 大人餐 early/lunch/dinner (one message per meal)
      3. 购物清单
    """
    if not menu.menu_data:
        return [("菜谱", "菜谱数据为空")]

    date_str = menu.date.strftime('%m月%d日')
    messages = []

    for section_key, emoji in [("baby_meals", "👶"), ("adult_meals", "🍽️")]:
        section_label = "宝宝餐" if section_key == "baby_meals" else "大人餐"
        for meal in menu.menu_data.get(section_key, []):
            meal_type = meal.get("meal_type", "")
            title = f"{emoji} {date_str} {section_label}·{meal_type}"
            body = _format_meal_section(meal)
            if body.strip():
                messages.append((title, body))

    shopping = menu.menu_data.get("shopping_list", [])
    if shopping:
        lines = []
        for cat in shopping:
            items = cat.get("items", [])
            if items:
                lines.append(f"▪ {cat.get('category', '')}")
                lines.append(f"  {'、'.join(items)}")
                lines.append("")
        if lines:
            messages.append((f"🛒 {date_str} 购物清单", "\n".join(lines).rstrip()))

    return messages


def _menu_to_bark_text(menu: DailyMenu) -> str:
    """Convert menu to single text string (for notification_service trigger)."""
    msgs = _menu_to_bark_messages(menu)
    return "\n\n".join(f"{t}\n{b}" for t, b in msgs)


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@router.get("/daily-menu")
async def get_daily_menu(
    date_str: Optional[str] = Query(None, alias="date"),
    db: Session = Depends(get_db),
    _: bool = Depends(require_auth),
):
    """Get menu for a specific date. Defaults to today (CN timezone)."""
    if date_str:
        try:
            target = date.fromisoformat(date_str)
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式错误，请使用 YYYY-MM-DD")
    else:
        target = datetime.now(_CN_TZ).date()

    menu = db.query(DailyMenu).filter(DailyMenu.date == target).first()
    if not menu:
        return {"menu": None}
    return {"menu": _menu_to_dict(menu)}


@router.get("/daily-menu/recent")
async def get_recent_menus(
    days: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db),
    _: bool = Depends(require_auth),
):
    """Get menus for the last N days."""
    today = datetime.now(_CN_TZ).date()
    start = today - timedelta(days=days - 1)
    menus = (
        db.query(DailyMenu)
        .filter(DailyMenu.date >= start)
        .order_by(DailyMenu.date.desc())
        .all()
    )
    return {"menus": [_menu_to_dict(m) for m in menus]}


class GenerateRequest(BaseModel):
    date: Optional[str] = None
    adult_count: Optional[int] = None


@router.post("/daily-menu/generate")
async def generate_menu(
    body: GenerateRequest,
    db: Session = Depends(get_db),
    _: bool = Depends(require_auth),
):
    """Generate a menu for the given date (defaults to tomorrow)."""
    if body.date:
        try:
            target = date.fromisoformat(body.date)
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式错误")
    else:
        target = datetime.now(_CN_TZ).date() + timedelta(days=1)

    kitchen_cfg = get_kitchen_config()
    adult_count = body.adult_count or kitchen_cfg.get("adult_count", 1)

    menu = await _generate_menu_for_date(target, adult_count, db)
    return {"menu": _menu_to_dict(menu)}


@router.post("/daily-menu/{menu_id}/regenerate")
async def regenerate_menu(
    menu_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_auth),
):
    """Regenerate an existing menu."""
    existing = db.query(DailyMenu).filter(DailyMenu.id == menu_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="菜谱不存在")

    kitchen_cfg = get_kitchen_config()
    adult_count = existing.adult_count or kitchen_cfg.get("adult_count", 1)
    menu = await _generate_menu_for_date(existing.date, adult_count, db)
    return {"menu": _menu_to_dict(menu)}


def _get_bark_devices(bark_cfg: dict) -> list[dict]:
    """Extract device list from bark config, with backward compat for old single-key format.

    Returns list of {"name": str, "key": str}.
    """
    devices = bark_cfg.get("devices", [])
    if devices:
        return [d for d in devices if d.get("key")]
    # Backward compat: old format had a single device_key string
    old_key = bark_cfg.get("device_key", "")
    if old_key:
        return [{"name": "默认设备", "key": old_key}]
    return []


async def _push_bark_to_all(bark_cfg: dict, title: str, body: str):
    """Push a single message to all configured Bark devices."""
    from app.services.notification_service import send_bark_push
    server_url = bark_cfg.get("server_url", "https://api.day.app")
    devices = _get_bark_devices(bark_cfg)
    for device in devices:
        await send_bark_push(server_url, device["key"], title, body, group="每日食谱")


async def _push_bark_menu_to_all(bark_cfg: dict, menu: DailyMenu):
    """Push a full menu as multiple smaller messages to all Bark devices."""
    from app.services.notification_service import send_bark_push
    import asyncio

    server_url = bark_cfg.get("server_url", "https://api.day.app")
    devices = _get_bark_devices(bark_cfg)
    messages = _menu_to_bark_messages(menu)

    for device in devices:
        for title, body in messages:
            await send_bark_push(server_url, device["key"], title, body, group="每日食谱")
            await asyncio.sleep(0.3)  # small delay to preserve ordering


@router.post("/daily-menu/{menu_id}/push")
async def push_menu(
    menu_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(require_auth),
):
    """Push a menu to all Bark devices (split into multiple messages per meal)."""
    menu = db.query(DailyMenu).filter(DailyMenu.id == menu_id).first()
    if not menu:
        raise HTTPException(status_code=404, detail="菜谱不存在")

    kitchen_cfg = get_kitchen_config()
    bark_cfg = kitchen_cfg.get("bark", {})
    devices = _get_bark_devices(bark_cfg)
    if not bark_cfg.get("enabled") or not devices:
        raise HTTPException(status_code=400, detail="Bark 推送未配置，请先在设置中添加设备")

    await _push_bark_menu_to_all(bark_cfg, menu)
    messages = _menu_to_bark_messages(menu)
    return {"success": True, "device_count": len(devices), "message_count": len(messages)}


@router.post("/daily-menu/push-test")
async def push_test(
    _: bool = Depends(require_auth),
):
    """Send a test Bark push notification to all devices."""
    kitchen_cfg = get_kitchen_config()
    bark_cfg = kitchen_cfg.get("bark", {})
    devices = _get_bark_devices(bark_cfg)
    if not devices:
        raise HTTPException(status_code=400, detail="请先添加 Bark 设备")

    await _push_bark_to_all(bark_cfg, "御膳房测试推送", "如果你收到这条消息，说明 Bark 推送配置成功！")
    return {"success": True, "device_count": len(devices)}


@router.get("/settings")
async def get_settings(_: bool = Depends(require_auth)):
    """Get kitchen settings (includes scheduler time and model)."""
    from app.config import get_scheduler_config, get_model_defaults
    from app.services.llm_service import get_available_models

    kitchen_cfg = get_kitchen_config()
    sc = get_scheduler_config().get("daily_menu_generation", {})
    model_defaults = get_model_defaults()

    return {
        "settings": kitchen_cfg,
        "scheduler": {
            "cron_hour": sc.get("cron_hour", 20),
            "cron_minute": sc.get("cron_minute", 0),
        },
        "model": model_defaults.get("kitchen-menu", ""),
        "available_models": get_available_models(),
    }


class SettingsUpdate(BaseModel):
    adult_count: Optional[int] = None
    bark: Optional[dict] = None
    scheduler: Optional[dict] = None
    model: Optional[str] = None


@router.put("/settings")
async def update_settings(
    body: SettingsUpdate,
    _: bool = Depends(require_auth),
):
    """Update kitchen settings (includes scheduler time and model)."""
    cfg = get_kitchen_config()
    if body.adult_count is not None:
        cfg["adult_count"] = body.adult_count
    if body.bark is not None:
        cfg["bark"] = body.bark
    save_kitchen_config(cfg)

    # Update scheduler config (synced with system settings)
    if body.scheduler is not None:
        from app.config import get_scheduler_config, save_scheduler_config
        sc = get_scheduler_config()
        sc["daily_menu_generation"] = {
            "cron_hour": body.scheduler.get("cron_hour", 20),
            "cron_minute": body.scheduler.get("cron_minute", 0),
        }
        save_scheduler_config(sc)

    # Update model default (synced with system settings)
    if body.model is not None:
        from app.config import get_model_defaults, set_model_defaults
        defaults = get_model_defaults()
        if body.model:
            defaults["kitchen-menu"] = body.model
        else:
            defaults.pop("kitchen-menu", None)
        set_model_defaults(defaults)

    return {"settings": cfg}


# ---------------------------------------------------------------------------
# Scheduled job
# ---------------------------------------------------------------------------

def _generate_daily_menu_and_push():
    """Sync wrapper called by APScheduler: generate tomorrow's menu and push via Bark."""
    async def _inner():
        db = SessionLocal()
        try:
            tomorrow = datetime.now(_CN_TZ).date() + timedelta(days=1)
            kitchen_cfg = get_kitchen_config()
            adult_count = kitchen_cfg.get("adult_count", 1)

            logger.info(f"Generating daily menu for {tomorrow}")
            menu = await _generate_menu_for_date(tomorrow, adult_count, db)
            logger.info(f"Daily menu generated for {tomorrow}: {menu.id}")

            # Push via Bark if configured
            bark_cfg = kitchen_cfg.get("bark", {})
            devices = _get_bark_devices(bark_cfg)
            if bark_cfg.get("enabled") and devices:
                await _push_bark_menu_to_all(bark_cfg, menu)
                logger.info(f"Daily menu pushed via Bark to {len(devices)} device(s)")

            # Also push via notification system (for bots subscribed to daily_menu trigger)
            from app.services.notification_service import send_notification_for_trigger
            trigger_content = _generate_daily_menu_trigger_content(menu)
            if trigger_content:
                await send_notification_for_trigger("daily_menu", trigger_content[0], trigger_content[1])

        except Exception as e:
            logger.error(f"Failed to generate/push daily menu: {e}", exc_info=True)
        finally:
            db.close()

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_inner())
        else:
            loop.run_until_complete(_inner())
    except RuntimeError:
        asyncio.run(_inner())


def _generate_daily_menu_trigger_content(menu: DailyMenu) -> tuple[str, str] | None:
    """Generate notification content for the daily_menu trigger."""
    if not menu or not menu.menu_data:
        return None
    title = f"明日食谱 - {menu.date.strftime('%m月%d日')}"
    body = _menu_to_bark_text(menu)
    return title, body


def run_daily_menu_generation_sync():
    """Entry point for APScheduler."""
    _generate_daily_menu_and_push()
