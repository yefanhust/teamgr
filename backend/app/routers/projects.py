import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth_middleware import require_auth
from app.models.project import Project, ProjectUpdate, ProjectMember, ProjectAnalysis
from app.models.talent import Talent
from app.services.pinyin_service import get_pinyin_data, match_pinyin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/projects", tags=["projects"])


# ---- Pydantic schemas ----

class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    parent_id: Optional[int] = None


class ProjectUpdateSchema(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    parent_id: Optional[int] = -1  # -1 means not provided; None means clear parent


class UpdateCreate(BaseModel):
    project_id: int
    talent_id: int
    content: str
    model: Optional[str] = None


# ---- Helpers ----

def _project_to_dict(p: Project, include_children: bool = False) -> dict:
    d = {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "status": p.status,
        "parent_id": p.parent_id,
        "parent_name": p.parent.name if p.parent else None,
        "started_at": p.started_at.isoformat() if p.started_at else None,
        "last_update_at": p.last_update_at.isoformat() if p.last_update_at else None,
        "member_count": len(p.members),
        "update_count": len(p.updates),
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }
    if include_children:
        d["children"] = [_project_to_dict(c) for c in (p.children or [])]
    return d


def _update_to_dict(u: ProjectUpdate) -> dict:
    return {
        "id": u.id,
        "project_id": u.project_id,
        "project_name": u.project.name if u.project else "",
        "talent_id": u.talent_id,
        "talent_name": u.talent.name if u.talent else "",
        "raw_input": u.raw_input,
        "parsed_data": u.parsed_data or {},
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def _member_to_dict(m: ProjectMember) -> dict:
    return {
        "id": m.id,
        "project_id": m.project_id,
        "talent_id": m.talent_id,
        "talent_name": m.talent.name if m.talent else "",
        "role": m.role,
        "joined_at": m.joined_at.isoformat() if m.joined_at else None,
    }


# ---- Project CRUD ----

@router.get("")
async def list_projects(
    status: Optional[str] = None,
    top_only: bool = False,
    q: str = "",
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    query = db.query(Project)
    if status:
        query = query.filter(Project.status == status)
    if top_only:
        query = query.filter(Project.parent_id.is_(None))
    projects = query.order_by(Project.last_update_at.desc().nullslast(), Project.created_at.desc()).all()

    if q.strip():
        projects = [
            p for p in projects
            if match_pinyin(q, p.name, p.name_pinyin or "", p.name_pinyin_initials or "")
        ]

    return [_project_to_dict(p, include_children=True) for p in projects]


@router.post("")
async def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    if body.parent_id:
        parent = db.query(Project).filter(Project.id == body.parent_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="父项目不存在")

    full_pinyin, initials = get_pinyin_data(body.name)
    project = Project(
        name=body.name,
        name_pinyin=full_pinyin,
        name_pinyin_initials=initials,
        description=body.description,
        parent_id=body.parent_id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return _project_to_dict(project, include_children=True)


@router.get("/search")
async def search_projects(
    q: str = Query("", min_length=0),
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    if not q.strip():
        projects = db.query(Project).filter(Project.status == "active").order_by(Project.name).limit(50).all()
        return [_project_to_dict(p, include_children=True) for p in projects]

    all_projects = db.query(Project).filter(Project.status != "archived").all()
    matched = [
        p for p in all_projects
        if match_pinyin(q, p.name, p.name_pinyin or "", p.name_pinyin_initials or "")
    ]
    return [_project_to_dict(p, include_children=True) for p in matched]


@router.get("/updates/recent")
async def get_recent_updates(
    days: int = 30,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    since = datetime.utcnow() - timedelta(days=days)
    updates = (
        db.query(ProjectUpdate)
        .filter(ProjectUpdate.created_at >= since)
        .order_by(ProjectUpdate.created_at.desc())
        .all()
    )
    return [_update_to_dict(u) for u in updates]


@router.get("/board/timeline")
async def board_timeline(
    range: str = "month",  # week / month / all
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    now = datetime.utcnow()
    if range == "week":
        since = now - timedelta(days=7)
    elif range == "month":
        since = now - timedelta(days=30)
    else:
        since = datetime(2000, 1, 1)

    updates = (
        db.query(ProjectUpdate)
        .filter(ProjectUpdate.created_at >= since)
        .order_by(ProjectUpdate.created_at.desc())
        .all()
    )

    # Group by date
    groups = {}
    for u in updates:
        date_key = u.created_at.strftime("%Y-%m-%d") if u.created_at else "unknown"
        if date_key not in groups:
            groups[date_key] = []
        groups[date_key].append(_update_to_dict(u))

    return {"groups": groups, "total": len(updates)}


@router.get("/board/members")
async def board_members(
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    members = db.query(ProjectMember).all()

    # Group by talent
    talent_map = {}
    for m in members:
        tid = m.talent_id
        if tid not in talent_map:
            talent_map[tid] = {
                "talent_id": tid,
                "talent_name": m.talent.name if m.talent else "",
                "projects": [],
            }
        # Get latest update for this member in this project
        latest = (
            db.query(ProjectUpdate)
            .filter(
                ProjectUpdate.project_id == m.project_id,
                ProjectUpdate.talent_id == m.talent_id,
            )
            .order_by(ProjectUpdate.created_at.desc())
            .first()
        )
        talent_map[tid]["projects"].append({
            "project_id": m.project_id,
            "project_name": m.project.name if m.project else "",
            "project_status": m.project.status if m.project else "",
            "role": m.role,
            "latest_update": _update_to_dict(latest) if latest else None,
        })

    return list(talent_map.values())


@router.get("/{project_id}")
async def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    result = _project_to_dict(project, include_children=True)
    result["members"] = [_member_to_dict(m) for m in project.members]
    result["recent_updates"] = [
        _update_to_dict(u) for u in
        sorted(project.updates, key=lambda x: x.created_at or datetime.min, reverse=True)[:20]
    ]
    result["llm_summary"] = project.llm_summary or ""
    return result


@router.put("/{project_id}")
async def update_project(
    project_id: int,
    body: ProjectUpdateSchema,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    if body.name is not None:
        project.name = body.name
        full_pinyin, initials = get_pinyin_data(body.name)
        project.name_pinyin = full_pinyin
        project.name_pinyin_initials = initials
    if body.description is not None:
        project.description = body.description
    if body.status is not None and body.status in ("active", "completed", "archived"):
        project.status = body.status
    if body.parent_id != -1:  # -1 means field not provided
        if body.parent_id is not None and body.parent_id != project.id:
            parent = db.query(Project).filter(Project.id == body.parent_id).first()
            if parent:
                project.parent_id = body.parent_id
        elif body.parent_id is None:
            project.parent_id = None

    db.commit()
    db.refresh(project)
    return _project_to_dict(project, include_children=True)


@router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    db.delete(project)
    db.commit()
    return {"ok": True}


# ---- Updates (progress records) ----

@router.post("/updates")
async def submit_update(
    body: UpdateCreate,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    import asyncio

    project = db.query(Project).filter(Project.id == body.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    talent = db.query(Talent).filter(Talent.id == body.talent_id).first()
    if not talent:
        raise HTTPException(status_code=404, detail="人才不存在")

    # Save update immediately with raw content, LLM parsing happens in background
    update = ProjectUpdate(
        project_id=body.project_id,
        talent_id=body.talent_id,
        raw_input=body.content,
        parsed_data={},
    )
    db.add(update)

    # Update project timestamps
    now = datetime.utcnow()
    project.last_update_at = now
    if not project.started_at:
        project.started_at = now

    # Auto-maintain project member
    existing_member = (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == body.project_id, ProjectMember.talent_id == body.talent_id)
        .first()
    )
    if not existing_member:
        member = ProjectMember(
            project_id=body.project_id,
            talent_id=body.talent_id,
        )
        db.add(member)

    db.commit()
    db.refresh(update)

    # Launch LLM parsing in background
    update_id = update.id
    talent_name = talent.name
    project_name = project.name
    model = body.model
    asyncio.create_task(_parse_update_bg(update_id, body.content, talent_name, project_name, model))

    return _update_to_dict(update)


@router.get("/{project_id}/updates")
async def get_project_updates(
    project_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    updates = (
        db.query(ProjectUpdate)
        .filter(ProjectUpdate.project_id == project_id)
        .order_by(ProjectUpdate.created_at.desc())
        .all()
    )
    return [_update_to_dict(u) for u in updates]


# ---- Active project info (LLM summary) ----

@router.get("/{project_id}/info")
async def get_project_info(
    project_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    # Check if summary needs refresh (no summary or new updates since last generation)
    needs_refresh = (
        not project.llm_summary
        or not project.llm_summary_updated_at
        or (project.last_update_at and project.llm_summary_updated_at < project.last_update_at)
    )

    if needs_refresh:
        summary = await _generate_project_summary(project, db)
        project.llm_summary = summary
        project.llm_summary_updated_at = datetime.utcnow()
        db.commit()

    # Compute days active
    days_active = 0
    if project.started_at:
        days_active = (datetime.utcnow() - project.started_at).days

    return {
        "id": project.id,
        "name": project.name,
        "description": project.description or "",
        "status": project.status,
        "parent_id": project.parent_id,
        "parent_name": project.parent.name if project.parent else None,
        "started_at": project.started_at.isoformat() if project.started_at else None,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "days_active": days_active,
        "member_count": len(project.members),
        "update_count": len(project.updates),
        "members": [_member_to_dict(m) for m in project.members],
        "llm_summary": project.llm_summary or "",
        "recent_updates": [
            _update_to_dict(u) for u in
            sorted(project.updates, key=lambda x: x.created_at or datetime.min, reverse=True)[:20]
        ],
    }


@router.post("/{project_id}/refresh-info")
async def refresh_project_info(
    project_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    summary = await _generate_project_summary(project, db)
    project.llm_summary = summary
    project.llm_summary_updated_at = datetime.utcnow()
    db.commit()

    return {"llm_summary": summary}


# ---- Background LLM processing ----

async def _parse_update_bg(update_id: int, content: str, talent_name: str, project_name: str, model: str = None):
    """Background task: parse update content with LLM and save results."""
    from app.database import SessionLocal
    try:
        parsed_data = await _parse_update_with_llm(content, talent_name, project_name, model_override=model)
        db = SessionLocal()
        try:
            upd = db.query(ProjectUpdate).filter(ProjectUpdate.id == update_id).first()
            if upd:
                upd.parsed_data = parsed_data
                # Update member role if detected
                if parsed_data.get("role_hint"):
                    member = (
                        db.query(ProjectMember)
                        .filter(ProjectMember.project_id == upd.project_id, ProjectMember.talent_id == upd.talent_id)
                        .first()
                    )
                    if member and not member.role:
                        member.role = parsed_data["role_hint"]
                db.commit()
                logger.info(f"Background LLM parse done for update {update_id}")
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Background LLM parse failed for update {update_id}: {e}")


# ---- LLM helpers ----

async def _parse_update_with_llm(content: str, talent_name: str, project_name: str, model_override: str = None) -> dict:
    """Use LLM to parse free-text update into structured fields."""
    from app.services.llm_service import _call_model_text, _extract_json, _strip_think_tags

    prompt = f"""你是项目管理助手。用户输入了一段关于「{talent_name}」在项目「{project_name}」上的工作进展。
请将其结构化为以下JSON格式（直接输出JSON，不要其他内容）：

{{
  "progress": "当前进展描述（简要概括）",
  "blockers": "遇到的阻碍（如无则为空字符串）",
  "next_steps": "下一步计划（如无则为空字符串）",
  "completion_pct": null,
  "role_hint": "从内容推断此人在项目中的角色/分工（如：前端开发、测试、产品设计等，如无法判断则为空字符串）"
}}

completion_pct 为预估完成百分比（0-100的整数），如无法判断则为 null。

用户输入：
{content}"""

    try:
        raw = await _call_model_text(prompt, call_type="project-update-parse", model_override=model_override)
        if not raw:
            return {"progress": content, "blockers": "", "next_steps": "", "completion_pct": None, "role_hint": ""}
        cleaned = _strip_think_tags(raw)
        return _extract_json(cleaned)
    except Exception as e:
        logger.warning(f"LLM parse update failed: {e}")
        return {"progress": content, "blockers": "", "next_steps": "", "completion_pct": None, "role_hint": ""}


async def _generate_project_summary(project: Project, db: Session) -> str:
    """Use LLM to generate a project summary from all updates and members."""
    from app.services.llm_service import _call_model_text, _strip_think_tags

    # Gather data
    members_info = []
    for m in project.members:
        name = m.talent.name if m.talent else "未知"
        members_info.append(f"- {name}（角色：{m.role or '未指定'}）")

    updates_info = []
    sorted_updates = sorted(project.updates, key=lambda x: x.created_at or datetime.min)
    for u in sorted_updates[-30:]:  # Last 30 updates
        talent_name = u.talent.name if u.talent else "未知"
        date_str = u.created_at.strftime("%Y-%m-%d") if u.created_at else "未知"
        parsed = u.parsed_data or {}
        progress = parsed.get("progress", u.raw_input)
        updates_info.append(f"- [{date_str}] {talent_name}: {progress}")

    days_active = 0
    if project.started_at:
        days_active = (datetime.utcnow() - project.started_at).days

    prompt = f"""根据以下项目信息，生成一份简洁的项目概览（使用Markdown格式）。

项目名称：{project.name}
项目描述：{project.description or '无'}
开始日期：{project.started_at.strftime('%Y-%m-%d') if project.started_at else '未开始'}
已进行：{days_active} 天
状态：{project.status}
参与人数：{len(project.members)} 人

参与成员：
{chr(10).join(members_info) if members_info else '暂无成员'}

进展记录（按时间排序）：
{chr(10).join(updates_info) if updates_info else '暂无进展记录'}

请生成包含以下内容的项目概览：
1. 项目概况（一句话总结当前状态）
2. 团队分工
3. 当前整体进展
4. 关键里程碑（从进展记录中提取）
5. 潜在风险或待解决问题（如有）

直接输出Markdown内容，不要包裹在代码块中。"""

    try:
        raw = await _call_model_text(prompt, call_type="project-summary")
        if not raw:
            return "暂无法生成项目摘要。"
        return _strip_think_tags(raw)
    except Exception as e:
        logger.warning(f"LLM generate project summary failed: {e}")
        return "项目摘要生成失败，请稍后重试。"


# ---- Project Efficiency Analysis ----

def _build_project_analysis_prompt(db: Session):
    """Build analysis prompt from all active projects. Returns (prompt, count) or (None, 0)."""
    from zoneinfo import ZoneInfo
    tz_shanghai = ZoneInfo("Asia/Shanghai")

    active_projects = (
        db.query(Project)
        .filter(Project.status == "active")
        .order_by(Project.last_update_at.desc().nullslast(), Project.created_at.desc())
        .all()
    )
    if not active_projects:
        return None, 0

    project_sections = []
    for p in active_projects:
        days_active = (datetime.utcnow() - p.started_at).days if p.started_at else 0

        # Members
        members_lines = []
        for m in p.members:
            name = m.talent.name if m.talent else "未知"
            role = m.role or "未指定"
            members_lines.append(f"  - {name}（{role}）")

        # Recent updates (last 20)
        sorted_updates = sorted(p.updates, key=lambda x: x.created_at or datetime.min, reverse=True)[:20]
        update_lines = []
        for u in sorted_updates:
            talent_name = u.talent.name if u.talent else "未知"
            date_str = u.created_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz_shanghai).strftime("%Y-%m-%d %H:%M") if u.created_at else "未知"
            parsed = u.parsed_data or {}
            progress = parsed.get("progress", u.raw_input)
            blockers = parsed.get("blockers", "")
            next_steps = parsed.get("next_steps", "")
            completion_pct = parsed.get("completion_pct")
            line = f"  - [{date_str}] {talent_name}: {progress}"
            if blockers:
                line += f"\n    阻碍：{blockers}"
            if next_steps:
                line += f"\n    下一步：{next_steps}"
            if completion_pct is not None:
                line += f" (完成度: {completion_pct}%)"
            update_lines.append(line)

        # Update frequency
        total_updates = len(p.updates)
        if days_active > 0 and total_updates > 0:
            freq = f"{total_updates}条/{days_active}天 (平均{total_updates/days_active:.1f}条/天)"
        else:
            freq = f"{total_updates}条"

        # Last update time
        last_update_str = "无"
        if p.last_update_at:
            last_local = p.last_update_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz_shanghai)
            days_since = (datetime.utcnow() - p.last_update_at).days
            last_update_str = f"{last_local.strftime('%Y-%m-%d')} ({days_since}天前)"

        section = f"""### 项目：{p.name}
- 描述：{p.description or '无'}
- 状态：{p.status}
- 已进行：{days_active}天
- 参与人数：{len(p.members)}人
- 最近更新：{last_update_str}
- 更新频率：{freq}

成员：
{chr(10).join(members_lines) if members_lines else '  暂无成员'}

最近进展记录：
{chr(10).join(update_lines) if update_lines else '  暂无进展记录'}"""
        project_sections.append(section)

    projects_text = "\n\n".join(project_sections)
    prompt = f"""你是一个项目管理效率顾问。以下是当前所有活跃项目的详细信息，包括项目描述、成员、进展记录、更新频率等。

{projects_text}

请对这些项目进行全面分析，给出以下方面的评估和建议：
1. **项目健康度**：各项目的整体状态评估，是否有停滞或进展缓慢的项目
2. **进展频率与节奏**：更新是否规律，是否有长期无更新的项目需要关注
3. **资源分配**：成员在各项目间的分布是否合理，是否有项目缺少人手
4. **阻碍与风险**：从进展记录中提取的关键阻碍和潜在风险汇总
5. **具体建议**：3-5条可操作的项目管理优化建议

请用简洁的中文回答，使用 Markdown 格式，方便阅读。"""
    return prompt, len(active_projects)


@router.get("/analysis")
def get_project_analyses(db: Session = Depends(get_db)):
    """Get the latest project analysis."""
    analyses = (
        db.query(ProjectAnalysis)
        .order_by(ProjectAnalysis.created_at.desc())
        .limit(1)
        .all()
    )
    return [
        {
            "id": a.id,
            "content": a.content,
            "generated_date": a.generated_date,
            "model_name": a.model_name,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in analyses
    ]


# --- Background project analysis task state ---
_project_analysis_bg = {
    "status": "idle",       # idle | running | done | error
    "subscribers": [],      # list[asyncio.Queue]
    "full_text": "",
    "thinking_text": "",
    "task": None,
    "error": None,
}


def _broadcast_project(event):
    """Send event to all subscriber queues."""
    dead = []
    for q in _project_analysis_bg["subscribers"]:
        try:
            q.put_nowait(event)
        except Exception:
            dead.append(q)
    for q in dead:
        try:
            _project_analysis_bg["subscribers"].remove(q)
        except ValueError:
            pass


async def _run_project_analysis_bg(prompt):
    """Background coroutine: runs LLM, broadcasts events, saves to DB."""
    import asyncio
    import time
    import threading
    from app.services.llm_service import _record_llm_usage, _get_local_model_config, get_current_model_name
    from app.config import get_gemini_config, get_model_defaults

    state = _project_analysis_bg
    my_task = asyncio.current_task()
    full_text = ""
    usage = None
    t0 = time.monotonic()

    model_name = get_model_defaults().get("project-analysis") or get_current_model_name()
    local_cfg = _get_local_model_config(model_name)

    try:
        if local_cfg:
            import httpx
            api_base = local_cfg["api_base"].rstrip("/")
            api_key = local_cfg.get("api_key", "")
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            payload = {
                "messages": [
                    {"role": "system", "content": "请直接回答，不要输出思考过程。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.7,
                "max_tokens": 4096,
                "stream": True,
            }
            if local_cfg.get("model_id"):
                payload["model"] = local_cfg["model_id"]

            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream("POST", f"{api_base}/chat/completions", json=payload, headers=headers) as resp:
                    resp.raise_for_status()
                    isl, osl = 0, 0
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            text = delta.get("content", "")
                            if text:
                                full_text += text
                                state["full_text"] = full_text
                                _broadcast_project({"type": "chunk", "content": text})
                            u = chunk.get("usage")
                            if u:
                                isl = u.get("prompt_tokens", isl)
                                osl = u.get("completion_tokens", osl)
                        except (json.JSONDecodeError, IndexError, KeyError):
                            pass
            duration_ms = int((time.monotonic() - t0) * 1000)
            _record_llm_usage(model_name, "project-analysis", duration_ms, isl, osl)
        else:
            from google import genai
            from google.genai import types as genai_types

            cfg = get_gemini_config()
            api_key = cfg.get("api_key", "")
            if not api_key or api_key == "your-gemini-api-key-here":
                _broadcast_project({"type": "error", "content": "LLM模型不可用"})
                state["status"] = "error"
                state["error"] = "LLM模型不可用"
                return

            client = genai.Client(api_key=api_key)
            queue = asyncio.Queue()
            loop = asyncio.get_event_loop()
            stream_error = [None]

            def produce():
                try:
                    response = client.models.generate_content_stream(
                        model=model_name,
                        contents=prompt,
                        config=genai_types.GenerateContentConfig(
                            thinking_config=genai_types.ThinkingConfig(
                                include_thoughts=True,
                            ),
                        ),
                    )
                    last_usage = None
                    for chunk in response:
                        parts = []
                        try:
                            for part in chunk.candidates[0].content.parts:
                                is_thought = getattr(part, 'thought', False)
                                text = getattr(part, 'text', '') or ''
                                if text:
                                    parts.append(('thought' if is_thought else 'text', text))
                        except (IndexError, AttributeError):
                            pass
                        if parts:
                            loop.call_soon_threadsafe(queue.put_nowait, ('_parts', parts))
                        last_usage = getattr(chunk, 'usage_metadata', None) or last_usage
                    loop.call_soon_threadsafe(queue.put_nowait, ('_meta', last_usage))
                except Exception as e:
                    stream_error[0] = e
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, None)

            threading.Thread(target=produce, daemon=True).start()

            in_thinking = False
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    elapsed = int(time.monotonic() - t0)
                    _broadcast_project({"type": "thinking", "elapsed": elapsed})
                    continue
                if item is None:
                    break
                if isinstance(item, tuple) and item[0] == '_meta':
                    usage = item[1]
                    continue
                if isinstance(item, tuple) and item[0] == '_parts':
                    for kind, text in item[1]:
                        if kind == 'thought':
                            if not in_thinking:
                                in_thinking = True
                            state["thinking_text"] += text
                            _broadcast_project({"type": "thinking_chunk", "content": text})
                        else:
                            if in_thinking:
                                in_thinking = False
                                elapsed = int(time.monotonic() - t0)
                                _broadcast_project({"type": "thinking_done", "elapsed": elapsed})
                            full_text += text
                            state["full_text"] = full_text
                            _broadcast_project({"type": "chunk", "content": text})

            if stream_error[0]:
                raise stream_error[0]

            duration_ms = int((time.monotonic() - t0) * 1000)
            isl = getattr(usage, 'prompt_token_count', 0) or getattr(usage, 'input_tokens', 0) if usage else 0
            osl = getattr(usage, 'candidates_token_count', 0) or getattr(usage, 'output_tokens', 0) if usage else 0
            _record_llm_usage(model_name, "project-analysis", duration_ms, isl, osl)

        # Save to DB
        if full_text.strip():
            from app.database import SessionLocal
            save_db = SessionLocal()
            try:
                today = datetime.utcnow().strftime("%Y-%m-%d")
                old = save_db.query(ProjectAnalysis).order_by(ProjectAnalysis.created_at.desc()).offset(6).all()
                for o in old:
                    save_db.delete(o)
                save_db.add(ProjectAnalysis(content=full_text.strip(), generated_date=today, model_name=model_name))
                save_db.commit()
            finally:
                save_db.close()

        state["status"] = "done"
        logger.info(f"Project analysis completed, text length={len(full_text)}, subscribers={len(state['subscribers'])}")
        _broadcast_project({"type": "done", "content": full_text.strip()})

    except Exception as e:
        logger.error(f"Project analysis background task error: {e}")
        state["status"] = "error"
        state["error"] = str(e)
        _broadcast_project({"type": "error", "content": str(e)})

    finally:
        await asyncio.sleep(5)
        # Only clean up if no new task has replaced us
        if state["task"] is my_task:
            state["status"] = "idle"
            state["subscribers"].clear()
            state["full_text"] = ""
            state["thinking_text"] = ""
            state["error"] = None
            state["task"] = None


@router.get("/analysis/status")
async def get_project_analysis_status():
    """Check if a project analysis background task is running."""
    return {"status": _project_analysis_bg["status"]}


@router.post("/analysis/trigger")
async def trigger_project_analysis_stream(db: Session = Depends(get_db)):
    """Stream project analysis via SSE. Idempotent: if already running, subscribes to existing task."""
    import asyncio

    state = _project_analysis_bg

    if state["status"] != "running":
        prompt, count = _build_project_analysis_prompt(db)
        if not prompt:
            async def error_stream():
                yield f"data: {json.dumps({'type': 'error', 'content': '没有活跃的项目'}, ensure_ascii=False)}\n\n"
            return StreamingResponse(error_stream(), media_type="text/event-stream",
                                     headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

        state["status"] = "running"
        state["subscribers"] = []
        state["full_text"] = ""
        state["thinking_text"] = ""
        state["error"] = None
        state["task"] = asyncio.create_task(_run_project_analysis_bg(prompt))

    # Subscribe to the running task
    sub_queue = asyncio.Queue()
    state["subscribers"].append(sub_queue)

    async def event_stream():
        try:
            # Replay accumulated content for late joiners
            if state["thinking_text"]:
                yield f"data: {json.dumps({'type': 'thinking_chunk', 'content': state['thinking_text']}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'thinking_done', 'elapsed': 0}, ensure_ascii=False)}\n\n"
            if state["full_text"]:
                yield f"data: {json.dumps({'type': 'chunk', 'content': state['full_text']}, ensure_ascii=False)}\n\n"

            if state["status"] == "done":
                yield f"data: {json.dumps({'type': 'done', 'content': state['full_text']}, ensure_ascii=False)}\n\n"
                return
            elif state["status"] == "error":
                yield f"data: {json.dumps({'type': 'error', 'content': state.get('error', 'Unknown error')}, ensure_ascii=False)}\n\n"
                return

            while True:
                try:
                    event = await asyncio.wait_for(sub_queue.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'thinking', 'elapsed': 0}, ensure_ascii=False)}\n\n"
                    continue
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") in ("done", "error"):
                    break
        finally:
            try:
                state["subscribers"].remove(sub_queue)
            except ValueError:
                pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def run_daily_project_analysis():
    """Run by scheduler at 3:40 AM. Analyzes active projects with LLM."""
    from app.database import SessionLocal
    from app.services.llm_service import _call_model_text, get_current_model_name
    from app.config import get_model_defaults

    db = SessionLocal()
    try:
        prompt, count = _build_project_analysis_prompt(db)
        if not prompt:
            logger.info("No active projects to analyze")
            return

        result = await _call_model_text(prompt, call_type="project-analysis")
        if not result:
            logger.warning("Project analysis LLM call returned empty result")
            return

        effective_model = get_model_defaults().get("project-analysis") or get_current_model_name()
        today = datetime.utcnow().strftime("%Y-%m-%d")
        old = db.query(ProjectAnalysis).order_by(ProjectAnalysis.created_at.desc()).offset(6).all()
        for o in old:
            db.delete(o)
        db.add(ProjectAnalysis(content=result, generated_date=today, model_name=effective_model))
        db.commit()
        logger.info(f"Project analysis generated for {today} ({count} projects)")

    except Exception as e:
        logger.error(f"Project analysis failed: {e}")
    finally:
        db.close()


def run_daily_project_analysis_sync():
    """Synchronous wrapper for APScheduler."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(run_daily_project_analysis())
        else:
            loop.run_until_complete(run_daily_project_analysis())
    except RuntimeError:
        asyncio.run(run_daily_project_analysis())
