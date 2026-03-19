import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth_middleware import require_auth
from app.models.project import Project, ProjectUpdate, ProjectMember
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
    project = db.query(Project).filter(Project.id == body.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    talent = db.query(Talent).filter(Talent.id == body.talent_id).first()
    if not talent:
        raise HTTPException(status_code=404, detail="人才不存在")

    # Parse with LLM
    parsed_data = await _parse_update_with_llm(body.content, talent.name, project.name, model_override=body.model)

    update = ProjectUpdate(
        project_id=body.project_id,
        talent_id=body.talent_id,
        raw_input=body.content,
        parsed_data=parsed_data,
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
            role=parsed_data.get("role_hint", ""),
        )
        db.add(member)
    elif parsed_data.get("role_hint") and not existing_member.role:
        existing_member.role = parsed_data["role_hint"]

    db.commit()
    db.refresh(update)
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
        "status": project.status,
        "started_at": project.started_at.isoformat() if project.started_at else None,
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
