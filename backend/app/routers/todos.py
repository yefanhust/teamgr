import json
import logging
import os
import re
import subprocess
from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.todo import TodoItem, TodoTag, TodoItemTag, TodoAnalysis

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/todos", tags=["todos"])


class TodoCreate(BaseModel):
    title: str
    high_priority: bool = False
    deadline: Optional[str] = None  # "YYYY-MM-DD" or null


class TodoUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    high_priority: Optional[bool] = None
    deadline: Optional[str] = None  # "YYYY-MM-DD", "" to clear, or null to skip
    repeat_rule: Optional[str] = None  # "daily"/"weekly"/"monthly"/"yearly", "" to clear
    repeat_interval: Optional[int] = None
    repeat_include_weekends: Optional[bool] = None


class VibeStatusUpdate(BaseModel):
    status: Optional[str] = None  # "planning", "implementing", "verifying", "committing", "committed", or null/""
    summary: Optional[str] = None  # summary of changes when moving to verifying
    plan: Optional[str] = None  # implementation plan


class TagCreate(BaseModel):
    name: str
    color: str = "#3B82F6"


def _write_queue_file(filename: str, data: dict):
    data_dir = os.environ.get("TEAMGR_DATA_DIR", "/app/data")
    queue_dir = os.path.join(data_dir, "vibe-queue")
    os.makedirs(queue_dir, exist_ok=True)
    with open(os.path.join(queue_dir, filename), "w") as f:
        json.dump(data, f, ensure_ascii=False)


def _serialize(item: TodoItem) -> dict:
    return {
        "id": item.id,
        "title": item.title,
        "description": item.description or "",
        "high_priority": item.high_priority,
        "deadline": item.deadline.isoformat() if item.deadline else None,
        "deadline_urgent": _is_deadline_urgent(item.deadline),
        "completed": item.completed,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "repeat_rule": item.repeat_rule,
        "repeat_interval": item.repeat_interval or 1,
        "repeat_next_at": item.repeat_next_at.isoformat() if item.repeat_next_at else None,
        "repeat_include_weekends": bool(item.repeat_include_weekends),
        "repeat_source_id": item.repeat_source_id,
        "vibe_status": item.vibe_status,
        "vibe_plan": item.vibe_plan or "",
        "vibe_summary": item.vibe_summary or "",
        "vibe_commit_id": item.vibe_commit_id or "",
        "vibe_session_id": item.vibe_session_id or "",
        "tags": [{"id": t.id, "name": t.name, "color": t.color} for t in item.tags],
    }


def _is_deadline_urgent(deadline) -> bool:
    """Return True if deadline is within 3 days from now."""
    if not deadline:
        return False
    today = date.today()
    return deadline <= today + timedelta(days=3)


def _parse_deadline(value: Optional[str]):
    """Parse deadline string to date or None."""
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _calc_next_repeat(from_date: date, rule: str, interval: int, include_weekends: bool = True) -> date:
    """Calculate the next repeat date. If include_weekends is False, skip to Monday."""
    import calendar
    if rule == "daily":
        result = from_date + timedelta(days=interval)
    elif rule == "weekly":
        result = from_date + timedelta(weeks=interval)
    elif rule == "monthly":
        m = from_date.month - 1 + interval
        y = from_date.year + m // 12
        m = m % 12 + 1
        d = min(from_date.day, calendar.monthrange(y, m)[1])
        result = date(y, m, d)
    elif rule == "yearly":
        y = from_date.year + interval
        d = min(from_date.day, calendar.monthrange(y, from_date.month)[1])
        result = date(y, from_date.month, d)
    else:
        result = from_date + timedelta(days=interval)
    # Skip weekends: push to next Monday
    if not include_weekends and result.weekday() >= 5:
        result += timedelta(days=(7 - result.weekday()))
    return result


def _spawn_repeat_todo(db: Session, source: TodoItem):
    """Create a new pending todo from a completed repeating todo, copying tags."""
    new_item = TodoItem(
        title=source.title,
        description=source.description,
        high_priority=source.high_priority,
        deadline=None,
        repeat_rule=source.repeat_rule,
        repeat_interval=source.repeat_interval,
        repeat_include_weekends=source.repeat_include_weekends,
        repeat_next_at=_calc_next_repeat(date.today(), source.repeat_rule, source.repeat_interval or 1, bool(source.repeat_include_weekends)),
        repeat_source_id=source.id,
    )
    db.add(new_item)
    db.flush()
    # Copy tags from source
    for tag in source.tags:
        db.add(TodoItemTag(todo_id=new_item.id, tag_id=tag.id))
    db.commit()
    db.refresh(new_item)
    return new_item


def check_and_spawn_repeat_todos_sync():
    """Scheduler-callable: check for due repeat todos and spawn new ones."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        _check_and_spawn_repeat_todos(db)
    finally:
        db.close()


def _check_and_spawn_repeat_todos(db: Session):
    """Check completed repeating todos whose repeat_next_at <= today, spawn new pending todos."""
    today = date.today()
    due_items = (
        db.query(TodoItem)
        .filter(
            TodoItem.completed == True,
            TodoItem.repeat_rule.isnot(None),
            TodoItem.repeat_next_at <= today,
        )
        .all()
    )
    for item in due_items:
        # Check if a pending child already exists for this source
        existing = (
            db.query(TodoItem)
            .filter(
                TodoItem.repeat_source_id == item.id,
                TodoItem.completed == False,
            )
            .first()
        )
        if existing:
            continue
        _spawn_repeat_todo(db, item)
        # Clear repeat_next_at on the completed source so it doesn't re-trigger
        item.repeat_next_at = None
        db.commit()
    return len(due_items)


@router.get("")
def list_todos(db: Session = Depends(get_db)):
    # Check for due repeat todos on each list request
    try:
        _check_and_spawn_repeat_todos(db)
    except Exception as e:
        logger.warning(f"Repeat todo check failed: {e}")

    pending = (
        db.query(TodoItem)
        .filter(TodoItem.completed == False)
        .order_by(TodoItem.high_priority.desc(), TodoItem.created_at.desc())
        .all()
    )
    # Auto-promote: deadline within 3 days -> high_priority
    promoted = False
    for item in pending:
        if not item.high_priority and _is_deadline_urgent(item.deadline):
            item.high_priority = True
            promoted = True
    if promoted:
        db.commit()
        pending.sort(key=lambda t: (-t.high_priority, t.created_at), reverse=False)
        pending.sort(key=lambda t: (-t.high_priority,))

    completed = (
        db.query(TodoItem)
        .filter(TodoItem.completed == True)
        .order_by(TodoItem.completed_at.desc())
        .all()
    )
    return {
        "pending": [_serialize(t) for t in pending],
        "completed": [_serialize(t) for t in completed],
    }


@router.post("")
async def create_todo(body: TodoCreate, db: Session = Depends(get_db)):
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    dl = _parse_deadline(body.deadline)
    high = body.high_priority or (dl is not None and _is_deadline_urgent(dl))
    item = TodoItem(title=body.title.strip(), high_priority=high, deadline=dl)
    db.add(item)
    db.commit()
    db.refresh(item)

    # Auto-tag using LLM
    try:
        tag_names = await _auto_tag(item.title)
        if tag_names:
            _assign_tags(db, item, tag_names)
            db.refresh(item)
    except Exception as e:
        logger.warning(f"Auto-tag failed for todo {item.id}: {e}")

    # Auto-claim if this is a new vibe task
    if item.title.lower().startswith("vibe"):
        try:
            _write_queue_file("claim.json", {
                "action": "claim",
                "id": item.id,
                "title": item.title,
                "description": item.description or "",
            })
        except Exception:
            pass

    return _serialize(item)


@router.put("/{todo_id}")
def update_todo(todo_id: int, body: TodoUpdate, db: Session = Depends(get_db)):
    item = db.query(TodoItem).filter(TodoItem.id == todo_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Todo not found")
    if body.title is not None:
        item.title = body.title.strip()
    if body.description is not None:
        item.description = body.description
    if body.deadline is not None:
        if body.deadline == "":
            item.deadline = None
        else:
            item.deadline = _parse_deadline(body.deadline)
    if body.high_priority is not None:
        item.high_priority = body.high_priority
    # Repeat config
    if body.repeat_include_weekends is not None:
        item.repeat_include_weekends = body.repeat_include_weekends
    if body.repeat_rule is not None:
        if body.repeat_rule == "":
            item.repeat_rule = None
            item.repeat_interval = 1
            item.repeat_next_at = None
            item.repeat_include_weekends = False
        elif body.repeat_rule in ("daily", "weekly", "monthly", "yearly"):
            item.repeat_rule = body.repeat_rule
            if body.repeat_interval is not None and body.repeat_interval >= 1:
                item.repeat_interval = body.repeat_interval
            # Compute next repeat date from today
            item.repeat_next_at = _calc_next_repeat(date.today(), item.repeat_rule, item.repeat_interval or 1, bool(item.repeat_include_weekends))
    elif body.repeat_interval is not None and item.repeat_rule:
        item.repeat_interval = max(1, body.repeat_interval)
        item.repeat_next_at = _calc_next_repeat(date.today(), item.repeat_rule, item.repeat_interval, bool(item.repeat_include_weekends))
    elif body.repeat_include_weekends is not None and item.repeat_rule:
        # Recalculate next date when weekends toggle changes
        item.repeat_next_at = _calc_next_repeat(date.today(), item.repeat_rule, item.repeat_interval or 1, bool(item.repeat_include_weekends))
    # Auto-promote if deadline is urgent
    if not item.high_priority and _is_deadline_urgent(item.deadline):
        item.high_priority = True
    db.commit()
    db.refresh(item)

    # Auto-claim if title was changed to vibe prefix and task has no vibe status yet
    if body.title is not None and item.title.lower().startswith("vibe") and not item.vibe_status:
        try:
            _write_queue_file("claim.json", {
                "action": "claim",
                "id": item.id,
                "title": item.title,
                "description": item.description or "",
            })
        except Exception:
            pass

    return _serialize(item)


@router.post("/{todo_id}/complete")
def complete_todo(todo_id: int, db: Session = Depends(get_db)):
    item = db.query(TodoItem).filter(TodoItem.id == todo_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Todo not found")
    item.completed = True
    item.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    result = _serialize(item)
    # If this is a repeating todo, spawn a new one
    if item.repeat_rule:
        new_item = _spawn_repeat_todo(db, item)
        result["spawned"] = _serialize(new_item)
    return result


@router.post("/{todo_id}/restart")
def restart_todo(todo_id: int, db: Session = Depends(get_db)):
    item = db.query(TodoItem).filter(TodoItem.id == todo_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Todo not found")
    # Keep the completed item as a historical record; create a new pending clone
    new_item = TodoItem(
        title=item.title,
        description=item.description,
        high_priority=item.high_priority,
        deadline=item.deadline,
        repeat_rule=item.repeat_rule,
        repeat_interval=item.repeat_interval,
        repeat_include_weekends=item.repeat_include_weekends,
    )
    db.add(new_item)
    db.flush()
    # Copy tags
    for tag in item.tags:
        db.add(TodoItemTag(todo_id=new_item.id, tag_id=tag.id))
    db.commit()
    db.refresh(new_item)
    return {"completed": _serialize(item), "new": _serialize(new_item)}


@router.delete("/{todo_id}")
def delete_todo(todo_id: int, db: Session = Depends(get_db)):
    item = db.query(TodoItem).filter(TodoItem.id == todo_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Todo not found")
    db.delete(item)
    db.commit()
    return {"ok": True}


def _get_git_root():
    """Get the git repository root directory."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _check_git_commit():
    """Check git status and return (commit_hash, commit_msg) if working tree is clean, else (None, None)."""
    git_root = _get_git_root()
    if not git_root:
        return None, None
    try:
        # Check for uncommitted changes (ignore untracked files)
        status = subprocess.run(
            ["git", "status", "--porcelain", "-uno"],
            capture_output=True, text=True, timeout=5, cwd=git_root,
        )
        if status.returncode != 0:
            return None, None
        has_changes = bool(status.stdout.strip())
        if has_changes:
            return None, None
        # Get HEAD commit
        log = subprocess.run(
            ["git", "log", "-1", "--format=%H%n%s"],
            capture_output=True, text=True, timeout=5, cwd=git_root,
        )
        if log.returncode != 0:
            return None, None
        lines = log.stdout.strip().split("\n", 1)
        commit_hash = lines[0] if lines else None
        commit_msg = lines[1] if len(lines) > 1 else ""
        return commit_hash, commit_msg
    except Exception:
        return None, None


@router.put("/{todo_id}/vibe-status")
def update_vibe_status(todo_id: int, body: VibeStatusUpdate, db: Session = Depends(get_db)):
    item = db.query(TodoItem).filter(TodoItem.id == todo_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Todo not found")
    valid = (None, "", "planning", "implementing", "verifying", "committing", "committed")
    if body.status not in valid:
        raise HTTPException(status_code=400, detail="Invalid vibe status")
    new_status = body.status if body.status else None
    # Revert from committed to verifying: only allowed if no commit_id
    if item.vibe_status == "committed" and new_status == "verifying":
        if item.vibe_commit_id:
            raise HTTPException(status_code=400, detail="已关联Git提交，无法返回验证")
        # Un-complete the task so it returns to pending
        item.completed = False
        item.completed_at = None
    old_status = item.vibe_status
    item.vibe_status = new_status
    if body.plan is not None:
        item.vibe_plan = body.plan
    if body.summary is not None:
        item.vibe_summary = body.summary
    # Auto-detect git commit when marking as committed
    if new_status == "committed" and not item.vibe_commit_id:
        commit_hash, _ = _check_git_commit()
        if commit_hash:
            item.vibe_commit_id = commit_hash
    # Clear commit_id when reverting from committed
    if new_status != "committed":
        item.vibe_commit_id = None
    db.commit()
    db.refresh(item)

    # planning → implementing: trigger claim-{id} (resume session, implement plan)
    if old_status == "planning" and new_status == "implementing":
        try:
            _write_queue_file(f"claim-{item.id}.json", {
                "action": "claim",
                "id": item.id,
                "title": item.title,
                "description": item.description or "",
                "vibe_plan": item.vibe_plan or "",
            })
        except Exception:
            pass

    # entering verifying: auto-claim next vibe task
    if new_status == "verifying":
        try:
            next_task = (
                db.query(TodoItem)
                .filter(
                    TodoItem.completed == False,
                    TodoItem.title.ilike("vibe%"),
                    TodoItem.vibe_status.is_(None),
                    TodoItem.id != item.id,
                )
                .order_by(TodoItem.high_priority.desc(), TodoItem.created_at.asc())
                .first()
            )
            if next_task:
                _write_queue_file("claim.json", {
                    "action": "claim",
                    "id": next_task.id,
                    "title": next_task.title,
                    "description": next_task.description or "",
                })
        except Exception:
            pass

    return _serialize(item)


@router.post("/{todo_id}/check-commit")
def check_commit(todo_id: int, db: Session = Depends(get_db)):
    """Re-check git for a committed task that doesn't have a commit_id yet."""
    item = db.query(TodoItem).filter(TodoItem.id == todo_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Todo not found")
    if item.vibe_status != "committed":
        raise HTTPException(status_code=400, detail="Task is not in committed status")
    if item.vibe_commit_id:
        return _serialize(item)
    commit_hash, _ = _check_git_commit()
    if commit_hash:
        item.vibe_commit_id = commit_hash
        db.commit()
        db.refresh(item)
    return _serialize(item)


class VibeReplanRequest(BaseModel):
    comment: str = ""


class VibeImproveRequest(BaseModel):
    feedback: str


@router.post("/vibe-claim")
def trigger_vibe_claim(db: Session = Depends(get_db)):
    task = (
        db.query(TodoItem)
        .filter(
            TodoItem.completed == False,
            TodoItem.title.ilike("vibe%"),
            TodoItem.vibe_status.is_(None),
        )
        .order_by(TodoItem.high_priority.desc(), TodoItem.created_at.asc())
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="没有待认领的 vibe 任务")

    _write_queue_file("claim.json", {
        "action": "claim",
        "id": task.id,
        "title": task.title,
        "description": task.description or "",
    })
    return {"message": f"已发送认领信号: {task.title}", "task": _serialize(task)}


@router.post("/{todo_id}/vibe-replan")
def trigger_vibe_replan(todo_id: int, body: VibeReplanRequest, db: Session = Depends(get_db)):
    item = db.query(TodoItem).filter(TodoItem.id == todo_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Todo not found")
    if item.vibe_status != "planning":
        raise HTTPException(status_code=400, detail="Task is not in planning status")

    _write_queue_file(f"plan-{todo_id}.json", {
        "action": "replan",
        "id": todo_id,
        "title": item.title,
        "description": item.description or "",
        "current_plan": item.vibe_plan or "",
        "comment": body.comment,
    })
    return _serialize(item)


@router.post("/{todo_id}/vibe-improve")
def trigger_vibe_improve(todo_id: int, body: VibeImproveRequest, db: Session = Depends(get_db)):
    item = db.query(TodoItem).filter(TodoItem.id == todo_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Todo not found")
    if item.vibe_status != "verifying":
        raise HTTPException(status_code=400, detail="只有待验证状态的任务可以改进")

    item.vibe_status = "implementing"
    db.commit()

    _write_queue_file(f"improve-{todo_id}.json", {
        "action": "improve",
        "id": todo_id,
        "title": item.title,
        "description": item.description or "",
        "summary": item.vibe_summary or "",
        "feedback": body.feedback,
    })

    db.refresh(item)
    return _serialize(item)


@router.post("/{todo_id}/vibe-commit")
def trigger_vibe_commit(todo_id: int, db: Session = Depends(get_db)):
    item = db.query(TodoItem).filter(TodoItem.id == todo_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Todo not found")
    if item.vibe_status != "verifying":
        raise HTTPException(status_code=400, detail="只有待验证状态的任务可以提交")

    item.vibe_status = "committing"
    db.commit()

    _write_queue_file(f"commit-{todo_id}.json", {
        "action": "commit",
        "id": todo_id,
        "title": item.title,
        "summary": item.vibe_summary or "",
    })

    db.refresh(item)
    return _serialize(item)


# --- Tag endpoints ---

@router.get("/tags/all")
def list_todo_tags(db: Session = Depends(get_db)):
    tags = db.query(TodoTag).order_by(TodoTag.name).all()
    return [
        {"id": t.id, "name": t.name, "color": t.color, "parent_id": t.parent_id}
        for t in tags
    ]


@router.post("/tags")
def create_todo_tag(body: TagCreate, db: Session = Depends(get_db)):
    existing = db.query(TodoTag).filter(TodoTag.name == body.name).first()
    if existing:
        return {"id": existing.id, "name": existing.name, "color": existing.color}
    tag = TodoTag(name=body.name, color=body.color)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return {"id": tag.id, "name": tag.name, "color": tag.color}


@router.put("/tags/{tag_id}")
def update_todo_tag(tag_id: int, body: TagCreate, db: Session = Depends(get_db)):
    tag = db.query(TodoTag).filter(TodoTag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    if body.name and body.name != tag.name:
        dup = db.query(TodoTag).filter(TodoTag.name == body.name, TodoTag.id != tag_id).first()
        if dup:
            raise HTTPException(status_code=400, detail="标签名已存在")
        tag.name = body.name
    if body.color:
        tag.color = body.color
    db.commit()
    db.refresh(tag)
    return {"id": tag.id, "name": tag.name, "color": tag.color}


@router.delete("/tags/{tag_id}")
def delete_todo_tag(tag_id: int, db: Session = Depends(get_db)):
    tag = db.query(TodoTag).filter(TodoTag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    db.query(TodoItemTag).filter(TodoItemTag.tag_id == tag_id).delete()
    db.delete(tag)
    db.commit()
    return {"message": "已删除"}


# --- Tag organize (one-click) ---

def _build_todo_organize_prompt(tag_names: list[str]) -> str:
    return f"""你是一个标签分类专家。请完成以下两个任务：

## 任务1：合并同义标签
找出语义相同或高度相似的标签组，选择最简洁准确的一个作为保留名，其余作为待合并项。
判断标准：含义本质相同只是措辞不同。
注意：含义不同的标签不要合并。

## 任务2：分层归类
将合并后的标签归类为一级标签（大分类）和二级标签（具体标签）的层级结构。
要求：
1. 一级标签是新创建的大分类名称（如"工作事务"、"个人生活"、"学习成长"等），数量控制在3-8个
2. 每个保留的标签都必须归入某个一级标签下作为二级标签
3. 一级标签名称要简洁、有概括性
4. 所有保留的标签都必须被分配，不能遗漏

现有标签列表：
{json.dumps(tag_names, ensure_ascii=False)}

请严格按以下JSON格式返回，不要包含其他内容：
{{
  "merges": [
    {{"keep": "保留的标签名", "remove": ["待合并标签1", "待合并标签2"]}}
  ],
  "categories": [
    {{
      "name": "一级标签名称",
      "color": "#十六进制颜色",
      "children": ["二级标签1", "二级标签2"]
    }}
  ]
}}

如果没有需要合并的标签，merges 返回空数组 []。"""


def _merge_todo_tags(db: Session, merges: list[dict]) -> list[str]:
    descriptions = []
    for merge in merges:
        keep_name = merge.get("keep", "")
        remove_names = merge.get("remove", [])
        if not keep_name or not remove_names:
            continue
        keep_tag = db.query(TodoTag).filter(TodoTag.name == keep_name).first()
        if not keep_tag:
            continue
        for rm_name in remove_names:
            rm_tag = db.query(TodoTag).filter(TodoTag.name == rm_name).first()
            if not rm_tag or rm_tag.id == keep_tag.id:
                continue
            existing_todo_ids = {
                row.todo_id for row in
                db.query(TodoItemTag).filter(TodoItemTag.tag_id == keep_tag.id).all()
            }
            for link in db.query(TodoItemTag).filter(TodoItemTag.tag_id == rm_tag.id).all():
                if link.todo_id not in existing_todo_ids:
                    link.tag_id = keep_tag.id
                else:
                    db.delete(link)
            db.flush()
            db.delete(rm_tag)
        descriptions.append(f"{', '.join(remove_names)} → {keep_name}")
    if descriptions:
        db.flush()
    return descriptions


def _apply_todo_tag_hierarchy(db: Session, categories: list[dict]):
    tags = db.query(TodoTag).all()
    tag_map = {t.name: t for t in tags}
    for t in tags:
        t.parent_id = None
    db.flush()

    for cat in categories:
        parent_name = cat["name"]
        parent_color = cat.get("color", "#6B7280")
        children_names = cat.get("children", [])
        parent_tag = tag_map.get(parent_name)
        if not parent_tag:
            parent_tag = db.query(TodoTag).filter(TodoTag.name == parent_name).first()
        if not parent_tag:
            parent_tag = TodoTag(name=parent_name, color=parent_color, parent_id=None)
            db.add(parent_tag)
            db.flush()
        else:
            parent_tag.parent_id = None
            parent_tag.color = parent_color
        for child_name in children_names:
            child_tag = tag_map.get(child_name)
            if child_tag and child_tag.id != parent_tag.id:
                child_tag.parent_id = parent_tag.id
                child_tag.color = "#3B82F6"
    db.flush()

    all_tags = db.query(TodoTag).all()
    parent_ids = {t.parent_id for t in all_tags if t.parent_id}
    for t in all_tags:
        if t.parent_id is None and t.id not in parent_ids and len(t.todos) == 0:
            db.delete(t)
    db.commit()


@router.post("/tags/organize")
async def organize_todo_tags(db: Session = Depends(get_db)):
    """Use LLM to organize todo tags with SSE streaming."""
    import asyncio
    import time
    from app.services.llm_service import _record_llm_usage

    tags = db.query(TodoTag).all()
    if not tags:
        raise HTTPException(status_code=400, detail="没有标签需要整理")

    tag_names = [t.name for t in tags]
    prompt = _build_todo_organize_prompt(tag_names)

    async def event_stream():
        import threading
        full_text = ""
        usage = None
        t0 = time.monotonic()
        try:
            from google import genai
            from google.genai import types as genai_types
            from app.config import get_gemini_config, get_model_defaults

            cfg = get_gemini_config()
            api_key = cfg.get("api_key", "")
            if not api_key or api_key == "your-gemini-api-key-here":
                yield f"data: {json.dumps({'type': 'error', 'content': 'LLM模型不可用'}, ensure_ascii=False)}\n\n"
                return

            organize_model = get_model_defaults().get("todo-organize-tags", get_model_defaults().get("organize-tags", "gemini-2.5-pro"))
            client = genai.Client(api_key=api_key)

            queue = asyncio.Queue()
            loop = asyncio.get_event_loop()
            stream_error = [None]

            def produce():
                try:
                    response = client.models.generate_content_stream(
                        model=organize_model,
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
                    yield f"data: {json.dumps({'type': 'thinking', 'elapsed': elapsed}, ensure_ascii=False)}\n\n"
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
                            yield f"data: {json.dumps({'type': 'thinking_chunk', 'content': text}, ensure_ascii=False)}\n\n"
                        else:
                            if in_thinking:
                                in_thinking = False
                                elapsed = int(time.monotonic() - t0)
                                yield f"data: {json.dumps({'type': 'thinking_done', 'elapsed': elapsed}, ensure_ascii=False)}\n\n"
                            full_text += text
                            yield f"data: {json.dumps({'type': 'chunk', 'content': text}, ensure_ascii=False)}\n\n"

            if stream_error[0]:
                raise stream_error[0]

            duration_ms = int((time.monotonic() - t0) * 1000)
            isl = getattr(usage, 'prompt_token_count', 0) or getattr(usage, 'input_tokens', 0) if usage else 0
            osl = getattr(usage, 'candidates_token_count', 0) or getattr(usage, 'output_tokens', 0) if usage else 0
            _record_llm_usage(organize_model, "todo-organize-tags", duration_ms, isl, osl)

            text = full_text.strip()
            if text.startswith("```"):
                text = re.sub(r'^```\w*\n?', '', text)
                text = re.sub(r'\n?```$', '', text)
            result = json.loads(text)

            merges = result.get("merges", [])
            if merges:
                merge_descs = _merge_todo_tags(db, merges)
                if merge_descs:
                    yield f"data: {json.dumps({'type': 'merge', 'merges': merge_descs}, ensure_ascii=False)}\n\n"

            categories = result.get("categories", [])
            if not categories:
                yield f"data: {json.dumps({'type': 'error', 'content': '未返回分类结果'}, ensure_ascii=False)}\n\n"
                return

            _apply_todo_tag_hierarchy(db, categories)

            all_tags = db.query(TodoTag).order_by(TodoTag.name).all()
            tag_list = [
                {"id": t.id, "name": t.name, "color": t.color, "parent_id": t.parent_id}
                for t in all_tags
            ]
            yield f"data: {json.dumps({'type': 'done', 'tags': tag_list}, ensure_ascii=False)}\n\n"

        except json.JSONDecodeError:
            yield f"data: {json.dumps({'type': 'error', 'content': 'LLM返回格式错误'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Todo tag organize error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- Auto-tag helper ---

async def _auto_tag(title: str) -> list[str]:
    """Use LLM to generate 1-3 short tags for a todo item."""
    from app.services.llm_service import _call_model_text

    prompt = f"""为以下任务生成1-3个简短的分类标签（每个标签2-4个字）。
标签应反映任务的类别或领域（如"工作"、"学习"、"健康"、"购物"、"社交"等）。

任务：{title}

请严格按JSON数组格式返回标签列表，不要包含其他内容：
["标签1", "标签2"]"""

    try:
        text = await _call_model_text(prompt, call_type="todo-auto-tag")
        if not text:
            return []
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r'^```\w*\n?', '', text)
            text = re.sub(r'\n?```$', '', text)
        tags = json.loads(text)
        if isinstance(tags, list):
            return [str(t).strip() for t in tags if str(t).strip()][:3]
    except Exception as e:
        logger.warning(f"Auto-tag LLM call failed: {e}")

    return []


def _assign_tags(db: Session, item: TodoItem, tag_names: list[str]):
    """Create tags if needed and assign them to a todo item."""
    for name in tag_names:
        tag = db.query(TodoTag).filter(TodoTag.name == name).first()
        if not tag:
            tag = TodoTag(name=name)
            db.add(tag)
            db.flush()
        existing = db.query(TodoItemTag).filter(
            TodoItemTag.todo_id == item.id,
            TodoItemTag.tag_id == tag.id,
        ).first()
        if not existing:
            db.add(TodoItemTag(todo_id=item.id, tag_id=tag.id))
    db.commit()


# ---- Daily Todo Analysis (3:30 AM) ----

def _format_duration(created_at, completed_at):
    """Format duration between two datetimes as human-readable Chinese string."""
    if not created_at or not completed_at:
        return "未知"
    delta = completed_at - created_at
    total_minutes = int(delta.total_seconds() / 60)
    days = total_minutes // (24 * 60)
    hours = (total_minutes % (24 * 60)) // 60
    minutes = total_minutes % 60
    if days > 0:
        return f"{days}天{hours}小时" if hours > 0 else f"{days}天"
    if hours > 0:
        return f"{hours}小时{minutes}分钟" if minutes > 0 else f"{hours}小时"
    return f"{minutes}分钟" if minutes > 0 else "不到1分钟"


async def run_daily_todo_analysis():
    """Run by scheduler at 3:30 AM. Analyzes recently completed todos with LLM."""
    from app.database import SessionLocal
    from app.services.llm_service import _call_model_text, get_current_model_name
    from app.config import get_model_defaults

    db = SessionLocal()
    try:
        prompt, count = _build_analysis_prompt(db)
        if not prompt:
            logger.info("No recently completed todos to analyze")
            return

        result = await _call_model_text(prompt, call_type="todo-analysis")
        if not result:
            logger.warning("Todo analysis LLM call returned empty result")
            return

        effective_model = get_model_defaults().get("todo-analysis") or get_current_model_name()
        today = datetime.utcnow().strftime("%Y-%m-%d")
        old = db.query(TodoAnalysis).order_by(TodoAnalysis.created_at.desc()).offset(6).all()
        for o in old:
            db.delete(o)
        db.add(TodoAnalysis(content=result, generated_date=today, model_name=effective_model))
        db.commit()
        logger.info(f"Todo analysis generated for {today} ({count} tasks)")
    except Exception as e:
        logger.error(f"Todo analysis failed: {e}")
    finally:
        db.close()


def run_daily_todo_analysis_sync():
    """Synchronous wrapper for APScheduler."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(run_daily_todo_analysis())
        else:
            loop.run_until_complete(run_daily_todo_analysis())
    except RuntimeError:
        asyncio.run(run_daily_todo_analysis())


# ---- Analysis API Endpoints ----

@router.get("/analysis")
def get_analyses(db: Session = Depends(get_db)):
    """Get recent todo analyses."""
    analyses = (
        db.query(TodoAnalysis)
        .order_by(TodoAnalysis.created_at.desc())
        .limit(7)
        .all()
    )
    return [
        {
            "id": a.id,
            "content": a.content,
            "generated_date": a.generated_date,
            "model_name": a.model_name or "",
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in analyses
    ]


def _build_analysis_prompt(db):
    """Build the analysis prompt from recently completed todos. Returns (prompt, count) or (None, 0)."""
    week_ago = datetime.utcnow() - timedelta(days=7)
    completed_items = (
        db.query(TodoItem)
        .filter(TodoItem.completed == True, TodoItem.completed_at >= week_ago)
        .order_by(TodoItem.completed_at.desc())
        .all()
    )
    if not completed_items:
        return None, 0

    task_lines = []
    for item in completed_items:
        tags_str = ", ".join(t.name for t in item.tags) if item.tags else "无标签"
        duration = _format_duration(item.created_at, item.completed_at)
        priority = "高优先级" if item.high_priority else "普通"
        desc = item.description.strip() if item.description else ""
        line = f"- 任务：{item.title}"
        if desc:
            line += f"\n  详情：{desc}"
        line += f"\n  标签：{tags_str} | 优先级：{priority} | 耗时：{duration}"
        if item.deadline:
            line += f" | 截止日：{item.deadline}"
        if item.completed_at:
            line += f" | 完成时间：{item.completed_at.strftime('%Y-%m-%d %H:%M')}"
        task_lines.append(line)

    tasks_text = "\n".join(task_lines)
    prompt = f"""你是一个任务管理效率顾问。以下是用户最近7天完成的任务列表，包括任务标题、详情、标签、优先级、耗时和完成时间。

{tasks_text}

请分析这些已完成的任务，给出以下方面的建议：
1. **效率概览**：总体完成情况，平均耗时，效率趋势
2. **时间管理**：哪些任务耗时过长？可能的原因和改进建议
3. **优先级管理**：高优先级任务的处理是否及时？
4. **规律与模式**：发现的工作模式（如哪类任务效率高/低）
5. **具体建议**：3-5条可操作的效率优化建议

请用简洁的中文回答，使用 Markdown 格式，方便阅读。"""
    return prompt, len(completed_items)


@router.post("/analysis/trigger")
async def trigger_analysis_stream(db: Session = Depends(get_db)):
    """Stream todo analysis via SSE."""
    import asyncio
    import time
    import threading
    from app.services.llm_service import _record_llm_usage, _get_local_model_config
    from app.config import get_gemini_config, get_model_defaults

    prompt, count = _build_analysis_prompt(db)

    async def event_stream():
        if not prompt:
            yield f"data: {json.dumps({'type': 'error', 'content': '最近7天没有已完成的任务'}, ensure_ascii=False)}\n\n"
            return

        full_text = ""
        usage = None
        t0 = time.monotonic()

        # Determine model
        model_name = get_model_defaults().get("todo-analysis") or get_gemini_config().get("current_model", "gemini-2.5-flash")
        local_cfg = _get_local_model_config(model_name)

        try:
            if local_cfg:
                # Stream from local model via OpenAI-compatible API
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
                                    yield f"data: {json.dumps({'type': 'chunk', 'content': text}, ensure_ascii=False)}\n\n"
                                u = chunk.get("usage")
                                if u:
                                    isl = u.get("prompt_tokens", isl)
                                    osl = u.get("completion_tokens", osl)
                            except (json.JSONDecodeError, IndexError, KeyError):
                                pass
                duration_ms = int((time.monotonic() - t0) * 1000)
                _record_llm_usage(model_name, "todo-analysis", duration_ms, isl, osl)
            else:
                # Stream from Gemini
                from google import genai
                from google.genai import types as genai_types

                cfg = get_gemini_config()
                api_key = cfg.get("api_key", "")
                if not api_key or api_key == "your-gemini-api-key-here":
                    yield f"data: {json.dumps({'type': 'error', 'content': 'LLM模型不可用'}, ensure_ascii=False)}\n\n"
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
                        yield f"data: {json.dumps({'type': 'thinking', 'elapsed': elapsed}, ensure_ascii=False)}\n\n"
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
                                yield f"data: {json.dumps({'type': 'thinking_chunk', 'content': text}, ensure_ascii=False)}\n\n"
                            else:
                                if in_thinking:
                                    in_thinking = False
                                    elapsed = int(time.monotonic() - t0)
                                    yield f"data: {json.dumps({'type': 'thinking_done', 'elapsed': elapsed}, ensure_ascii=False)}\n\n"
                                full_text += text
                                yield f"data: {json.dumps({'type': 'chunk', 'content': text}, ensure_ascii=False)}\n\n"

                if stream_error[0]:
                    raise stream_error[0]

                duration_ms = int((time.monotonic() - t0) * 1000)
                isl = getattr(usage, 'prompt_token_count', 0) or getattr(usage, 'input_tokens', 0) if usage else 0
                osl = getattr(usage, 'candidates_token_count', 0) or getattr(usage, 'output_tokens', 0) if usage else 0
                _record_llm_usage(model_name, "todo-analysis", duration_ms, isl, osl)

            # Save to DB
            if full_text.strip():
                from app.database import SessionLocal
                save_db = SessionLocal()
                try:
                    today = datetime.utcnow().strftime("%Y-%m-%d")
                    old = save_db.query(TodoAnalysis).order_by(TodoAnalysis.created_at.desc()).offset(6).all()
                    for o in old:
                        save_db.delete(o)
                    save_db.add(TodoAnalysis(content=full_text.strip(), generated_date=today, model_name=model_name))
                    save_db.commit()
                finally:
                    save_db.close()

            yield f"data: {json.dumps({'type': 'done', 'content': full_text.strip()}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"Todo analysis stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
