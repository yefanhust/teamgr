# Vibe 任务自动化管理方案

## 目标

实现 vibe 任务从认领到提交的全生命周期自动化：

1. 自动认领 TODO 中优先级最高的 vibe 任务，交给 Claude Code 判断复杂度后规划或直接实现
2. 任务进入"待验证"即认领下一个任务，不必等到提交完成
3. 人工可在"待验证"阶段提出改进意见，任务回到"实现中"
4. 人工验证通过后自动 commit + push，流转到"已提交"

## 核心原则

1. **plan 和 summary 全部由 Claude Code 生成**，不由后端 LLM (Gemini/本地模型) 生成。Claude Code 有完整代码仓库上下文。
2. **一个任务绑定一个 Claude session**。任务生命周期内所有 Claude 交互 resume 同一个 session，任务结束 (committed) 则 session 结束。
3. **任何时候只有一个活跃 session**。Watcher 串行处理队列，保证不会有两个 Claude 实例同时运行。

## 环境现状

| 环境 | git | SSH push | Claude Code | API | 代码目录 |
|------|-----|----------|------------|-----|---------|
| 宿主机 | /usr/bin/git | git@github.com:yefanhust/teamgr.git | claude 2.1.71 | via nginx :6443 | /home/ubuntu/workspace/teamgr |
| Docker (teamgr-app) | 无 | 无 | 无 | localhost:8000 | 只读挂载 /app/app |

共享 volume: 宿主机 `data/` <-> 容器 `/app/data` (读写)

## 数据模型

### TodoItem 字段

| 字段 | 类型 | 用途 |
|------|------|------|
| vibe_status | String(20) | null / planning / implementing / verifying / committing / committed |
| vibe_plan | Text | Claude Code 生成的实现计划 |
| vibe_summary | Text | Claude Code 生成的变更总结 |
| vibe_commit_id | String(40) | 关联的 git commit hash |
| vibe_session_id | String(100) | **新增** — Claude Code 会话 ID，用于 resume |

### 需移除

- 后端 `_auto_plan` 函数及 `create_todo` 中的调用
- 后端 `rethink-plan` 端点（改为 `vibe-replan`）

## 状态机

```
                    +-----------+
                    |   TODO    |  (vibe 开头, vibe_status=null)
                    +-----+-----+
                          |
                 [触发: 手动/自动认领]
                    Watcher → claude -p (新 session)
                    Claude Code 阅读任务 + 代码仓库
                    Claude Code 判断复杂度
                          |
              +-----------+-----------+
              |                       |
         复杂任务                  简单任务
              |                       |
              v                       |
       +------+------+               |
       |   规划中     |               |
       |  (planning) |               |
       |             |               |
       | Claude Code |               |
       | 生成 plan   |               |
       | session暂停  |               |
       +------+------+               |
              |                       |
    +---------+---------+             |
    |                   |             |
 [同意]          [三思而行]           |
 (人工确认       (人工编辑plan        |
  plan OK)       +输入comment         |
    |            → resume session     |
    |            → Claude重新思考)    |
    |                   |             |
    |            (留在"规划中",       |
    |             plan已更新)         |
    |                                 |
    v                                 v
+---+---+---+---+---+---+---+-------+
|            实现中                   |
|         (implementing)             |
|                                     |
|   Claude Code 修改代码 (resume)    |
|   Claude Code 生成 summary         |
|   session 暂停                      |
+----------------+-------------------+
                 |
        [Claude 实现完毕]
        [调 API: verifying + summary]
        [同时: 自动认领下一个任务]  <--- 不等提交，立即认领
                 |
                 v
         +-------+-------+
         |    待验证      |
         |  (verifying)  |
         +-------+-------+
                 |
       +---------+---------+
       |                   |
  [验证通过]          [改进]
  (人工勾选)         (人工输入
       |             改进意见
       |             → resume session
       |             → 回到实现中)
       |                   |
       v                   v
+------+------+     +-----+------+
|   提交中     |     |  实现中     |
| (committing)|     |  (改进中)   |
+------+------+     +------------+
       |
  resume session
  Claude生成 commit msg
  git add + commit + push
  session 结束
       |
       v
+------+------+
|   已提交     |
| (committed) |
+-------------+
```

### 认领时机

| 事件 | 动作 |
|------|------|
| 任务进入 verifying | 自动认领下一个 vibe 任务 (新 session) |
| 任务被提交 (committed) | 不再触发认领 (已在 verifying 时触发过) |
| 无待认领任务 | 静默忽略，等待新任务创建 |

### Session 生命周期

| 阶段 | Session 状态 |
|------|-------------|
| 认领 (claim) | **创建**新 session，存储 session_id |
| 规划 → 三思而行 | **resume** 同一 session |
| 同意 → 实现 | **resume** 同一 session |
| 实现完 → 待验证 | session **暂停** (可能被 improve 恢复) |
| 改进 (improve) | **resume** 同一 session |
| 提交 (commit) | **resume** 同一 session，完成后 session **结束** |

任何时刻最多一个 session 处于活跃状态。Watcher 串行处理保证这一点。

## 架构设计

### 信号文件

```
data/vibe-queue/
  claim.json              # 认领下一个 vibe 任务 (新 session)
  claim-{id}.json         # 认领指定任务 (有 plan，resume session)
  plan-{id}.json          # 三思而行: resume session 重新规划
  improve-{id}.json       # 改进: resume session 按反馈修改
  commit-{id}.json        # 提交: resume session 生成 commit + push
```

### Session ID 存储

```
data/vibe-sessions/
  {task_id}               # 文件内容为 claude session/conversation ID
```

宿主机 Watcher 管理 session 文件。后端不直接接触 session。

## 实现细节

### 1. 后端改动

#### 移除

```python
# 移除 _auto_plan 函数
# 移除 create_todo 中 vibe 自动规划代码
# 移除 rethink-plan 端点
```

#### 新增字段: vibe_session_id

```python
# models/todo.py
vibe_session_id = Column(String(100), nullable=True)

# database.py 迁移
("todo_items", "vibe_session_id", "TEXT"),

# _serialize 中增加
"vibe_session_id": item.vibe_session_id or "",
```

#### 公共函数

```python
def _write_queue_file(filename: str, data: dict):
    data_dir = os.environ.get("TEAMGR_DATA_DIR", "/app/data")
    queue_dir = os.path.join(data_dir, "vibe-queue")
    os.makedirs(queue_dir, exist_ok=True)
    with open(os.path.join(queue_dir, filename), "w") as f:
        json.dump(data, f, ensure_ascii=False)
```

#### update_vibe_status 中增加自动认领

```python
# 进入 verifying 时自动认领下一个任务
if new_status == "verifying":
    try:
        next_task = (
            db.query(TodoItem)
            .filter(TodoItem.completed == False,
                    TodoItem.title.ilike("vibe%"),
                    TodoItem.vibe_status.is_(None),
                    TodoItem.id != item.id)
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
        pass  # 认领失败不影响当前任务

# planning → implementing 时，触发按 plan 实现
if item.vibe_status == "planning" and new_status == "implementing":
    _write_queue_file(f"claim-{item.id}.json", {
        "action": "claim",
        "id": item.id,
        "title": item.title,
        "description": item.description or "",
        "vibe_plan": item.vibe_plan or "",
    })
```

#### POST /api/todos/vibe-claim

```python
@router.post("/vibe-claim")
def trigger_vibe_claim(db: Session = Depends(get_db)):
    task = (
        db.query(TodoItem)
        .filter(TodoItem.completed == False,
                TodoItem.title.ilike("vibe%"),
                TodoItem.vibe_status.is_(None))
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
```

#### POST /api/todos/{id}/vibe-replan

"三思而行" — 需要传入 comment (用户的修改意见)。

```python
class VibeReplanRequest(BaseModel):
    comment: str = ""  # 用户的修改意见

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
```

#### POST /api/todos/{id}/vibe-improve

"改进" — 从待验证退回实现中，附带改进意见。

```python
class VibeImproveRequest(BaseModel):
    feedback: str  # 改进意见 (必填)

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
```

#### POST /api/todos/{id}/vibe-commit

```python
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
```

### 2. 宿主机 Watcher 脚本

`scripts/vibe-watcher.sh`

```bash
#!/bin/bash
set -euo pipefail

REPO_DIR="/home/ubuntu/workspace/teamgr"
QUEUE_DIR="$REPO_DIR/data/vibe-queue"
SESSIONS_DIR="$REPO_DIR/data/vibe-sessions"
API="https://localhost:6443/api/todos"
CLAUDE="/home/ubuntu/.nvm/versions/node/v20.20.0/bin/claude"
LOG="$REPO_DIR/data/vibe-watcher.log"
TOKEN="${VIBE_TOKEN:-}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }
api_call() { curl -sk -H "Authorization: Bearer $TOKEN" "$@"; }

mkdir -p "$QUEUE_DIR" "$SESSIONS_DIR"

# ========== Session 管理 ==========

get_session() {
    local task_id="$1"
    local session_file="$SESSIONS_DIR/$task_id"
    [ -f "$session_file" ] && cat "$session_file" || echo ""
}

save_session() {
    local task_id="$1" session_id="$2"
    echo "$session_id" > "$SESSIONS_DIR/$task_id"
    # 同时存入 DB
    api_call -X PUT "$API/$task_id/vibe-status" \
        -H "Content-Type: application/json" \
        -d "{\"status\": null}" > /dev/null 2>&1 || true
    # 注: session_id 存 DB 需要单独端点或在 vibe-status 中支持
}

end_session() {
    local task_id="$1"
    rm -f "$SESSIONS_DIR/$task_id"
}

# 调用 Claude，自动处理 session 创建/恢复
# 用法: run_claude <task_id> <prompt>
# 返回: claude 输出
run_claude() {
    local task_id="$1"
    local prompt="$2"
    local session_id=$(get_session "$task_id")

    cd "$REPO_DIR"

    if [ -n "$session_id" ]; then
        log "Resume session $session_id for task #$task_id"
        local output
        output=$($CLAUDE --resume "$session_id" -p "$prompt" 2>>"$LOG") || {
            log "Resume 失败，创建新 session"
            output=$($CLAUDE -p "$prompt" 2>>"$LOG")
            # 从 ~/.claude/projects/ 中获取最新 session id
            session_id=$(ls -t ~/.claude/projects/*/conversations/ 2>/dev/null | head -1 | xargs -r basename 2>/dev/null || echo "")
            [ -n "$session_id" ] && echo "$session_id" > "$SESSIONS_DIR/$task_id"
        }
        echo "$output"
    else
        log "新建 session for task #$task_id"
        local output
        output=$($CLAUDE -p "$prompt" 2>>"$LOG") || {
            log "Claude CLI 失败: task #$task_id"
            return 1
        }
        # 获取刚创建的 session id
        session_id=$(ls -t ~/.claude/projects/*/conversations/ 2>/dev/null | head -1 | xargs -r basename 2>/dev/null || echo "")
        [ -n "$session_id" ] && echo "$session_id" > "$SESSIONS_DIR/$task_id"
        echo "$output"
    fi
}

# ========== 处理认领信号 (新任务, 新 session) ==========
handle_claim() {
    local file="$1"
    local task_id=$(jq -r '.id' "$file")
    local title=$(jq -r '.title' "$file")
    local description=$(jq -r '.description // empty' "$file")
    local plan=$(jq -r '.vibe_plan // empty' "$file")
    rm -f "$file"

    log "=== 认领任务 #$task_id: $title ==="

    if [ -n "$plan" ]; then
        # 有 plan → resume session, 按计划实现
        run_claude "$task_id" "你正在继续处理一个 vibe coding 研发任务，现在需要按计划实现。

任务: $title
$([ -n "$description" ] && echo "描述: $description")
实现计划:
$plan

请按照计划实现这个任务。完成后:
1. 确保代码能正常工作
2. 总结你做了哪些修改
3. 调用以下命令更新任务状态:
   curl -sk -X PUT '$API/$task_id/vibe-status' \\
     -H 'Content-Type: application/json' \\
     -H 'Authorization: Bearer $TOKEN' \\
     -d '{\"status\": \"verifying\", \"summary\": \"你的变更总结 (Markdown 格式)\"}'"

    else
        # 无 plan → 新 session, Claude 自行判断
        run_claude "$task_id" "你正在处理一个 vibe coding 研发任务。

任务: $title
$([ -n "$description" ] && echo "描述: $description")

请先阅读相关代码，判断这个任务的复杂度:

**如果是复杂任务** (涉及多个文件改动、前后端联动、数据库变更等):
- 不要开始实现
- 制定详细的实现计划 (包括需要修改的文件、步骤、注意事项)
- 调用:
  curl -sk -X PUT '$API/$task_id/vibe-status' \\
    -H 'Content-Type: application/json' \\
    -H 'Authorization: Bearer $TOKEN' \\
    -d '{\"status\": \"planning\", \"plan\": \"你的实现计划 (Markdown)\"}'

**如果是简单任务** (UI 调整、小功能、bug 修复等):
- 直接实现
- 总结你做了哪些修改
- 调用:
  curl -sk -X PUT '$API/$task_id/vibe-status' \\
    -H 'Content-Type: application/json' \\
    -H 'Authorization: Bearer $TOKEN' \\
    -d '{\"status\": \"verifying\", \"summary\": \"你的变更总结 (Markdown)\"}'"
    fi

    log "=== 任务 #$task_id 处理完成 ==="
}

# ========== 处理三思而行信号 (resume session) ==========
handle_replan() {
    local file="$1"
    local task_id=$(jq -r '.id' "$file")
    local title=$(jq -r '.title' "$file")
    local description=$(jq -r '.description // empty' "$file")
    local current_plan=$(jq -r '.current_plan // empty' "$file")
    local comment=$(jq -r '.comment // empty' "$file")
    rm -f "$file"

    log "=== 三思而行 #$task_id: $title ==="

    run_claude "$task_id" "用户对你上一版的实现计划提出了修改意见，请重新思考。

任务: $title
$([ -n "$description" ] && echo "描述: $description")

当前计划:
$current_plan

用户意见:
$comment

请综合用户的意见和你对代码仓库的理解，重新制定实现计划。
完成后调用:
curl -sk -X PUT '$API/$task_id/vibe-status' \\
  -H 'Content-Type: application/json' \\
  -H 'Authorization: Bearer $TOKEN' \\
  -d '{\"status\": \"planning\", \"plan\": \"你的新计划 (Markdown)\"}'"

    log "=== 三思而行 #$task_id 完成 ==="
}

# ========== 处理改进信号 (resume session) ==========
handle_improve() {
    local file="$1"
    local task_id=$(jq -r '.id' "$file")
    local title=$(jq -r '.title' "$file")
    local description=$(jq -r '.description // empty' "$file")
    local summary=$(jq -r '.summary // empty' "$file")
    local feedback=$(jq -r '.feedback // empty' "$file")
    rm -f "$file"

    log "=== 改进任务 #$task_id: $title ==="

    run_claude "$task_id" "用户验证了你之前的实现，提出了改进意见，请修改。

任务: $title
$([ -n "$description" ] && echo "描述: $description")

之前的变更总结:
$summary

用户改进意见:
$feedback

请根据用户意见修改代码。完成后:
1. 确保修改后代码正常工作
2. 更新变更总结 (包含本次改进)
3. 调用:
   curl -sk -X PUT '$API/$task_id/vibe-status' \\
     -H 'Content-Type: application/json' \\
     -H 'Authorization: Bearer $TOKEN' \\
     -d '{\"status\": \"verifying\", \"summary\": \"更新后的变更总结 (Markdown)\"}'"

    log "=== 改进 #$task_id 完成 ==="
}

# ========== 处理提交信号 (resume session, session 结束) ==========
handle_commit() {
    local file="$1"
    local task_id=$(jq -r '.id' "$file")
    local title=$(jq -r '.title' "$file")
    local summary=$(jq -r '.summary // empty' "$file")
    rm -f "$file"

    log "=== 提交任务 #$task_id: $title ==="

    cd "$REPO_DIR"

    # 检查是否有变更
    if git diff --quiet HEAD 2>/dev/null && [ -z "$(git status --porcelain)" ]; then
        log "没有变更可提交, 直接标记 committed"
        api_call -X PUT "$API/$task_id/vibe-status" \
            -H "Content-Type: application/json" \
            -d '{"status": "committed"}' > /dev/null
        api_call -X POST "$API/$task_id/complete" > /dev/null
        api_call -X POST "$API/$task_id/check-commit" > /dev/null
        end_session "$task_id"
        return 0
    fi

    # Resume session, Claude 基于 git diff 生成 commit message
    local commit_msg
    commit_msg=$(run_claude "$task_id" "请查看 git status 和 git diff，为这些变更生成 commit message。

相关任务: $title
变更总结 (仅供参考，请基于实际 diff):
$summary

格式:
- 第一行: feat/fix/refactor: 简短描述
- 空行
- 正文: bullet points 列出主要变更
- 空行
- Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

只输出 commit message，不要其他内容，不要代码块。") || {
        commit_msg="$title

$summary

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
        log "Claude 生成 commit message 失败，使用 fallback"
    }

    git add -A
    git commit -m "$commit_msg"

    if git push origin master; then
        log "Push 成功: $(git rev-parse HEAD)"
        api_call -X PUT "$API/$task_id/vibe-status" \
            -H "Content-Type: application/json" \
            -d '{"status": "committed"}' > /dev/null
        api_call -X POST "$API/$task_id/complete" > /dev/null
        api_call -X POST "$API/$task_id/check-commit" > /dev/null
        log "=== 任务 #$task_id 已提交并推送 ==="
    else
        log "Push 失败，回退到 verifying"
        api_call -X PUT "$API/$task_id/vibe-status" \
            -H "Content-Type: application/json" \
            -d '{"status": "verifying"}' > /dev/null
    fi

    end_session "$task_id"
}

# ========== 主循环 ==========
log "Vibe Watcher 启动, 监听 $QUEUE_DIR"

process_file() {
    local filepath="$1"
    local filename=$(basename "$filepath")
    [ -f "$filepath" ] || return

    case "$filename" in
        claim.json)      handle_claim "$filepath" ;;
        claim-*.json)    handle_claim "$filepath" ;;
        plan-*.json)     handle_replan "$filepath" ;;
        improve-*.json)  handle_improve "$filepath" ;;
        commit-*.json)   handle_commit "$filepath" ;;
        *)               log "忽略: $filename" ;;
    esac
}

# 先处理积压
for f in "$QUEUE_DIR"/*.json; do
    [ -f "$f" ] || continue
    process_file "$f"
done

# 持续监听
inotifywait -m "$QUEUE_DIR" -e create -e moved_to --format '%f' 2>/dev/null | while read filename; do
    sleep 0.5
    process_file "$QUEUE_DIR/$filename"
done
```

### 3. 前端改动

#### "三思而行" — 弹窗输入意见

```javascript
async function rethinkPlan(item) {
  try {
    // 弹窗让用户输入意见
    const comment = await promptForComment('请输入修改意见', '对当前计划的改进建议...')
    if (comment === null) return  // 取消

    rethinkingId.value = item.id
    await api.post(`/api/todos/${item.id}/vibe-replan`, { comment })
    showToast('Claude 正在重新思考...')

    // 轮询等待 plan 更新
    for (let i = 0; i < 60; i++) {
      await new Promise(r => setTimeout(r, 2000))
      await store.fetchAll()
      const updated = store.pending.find(t => t.id === item.id)
      if (updated && updated.vibe_plan !== item.vibe_plan) {
        showToast('计划已更新')
        return
      }
    }
  } catch (e) {
    showToast(e.response?.data?.detail || '操作失败')
  } finally {
    rethinkingId.value = null
  }
}
```

#### "改进" — 待验证页面新增按钮

模板部分 (待验证 tab 每个任务增加改进按钮):

```html
<div class="flex items-center gap-2 mt-2">
  <van-button size="small" type="warning" plain icon="edit"
    @click.stop="openImproveDialog(item)"
  >
    改进
  </van-button>
</div>
```

JS:

```javascript
const showImproveDialog = ref(false)
const improveItem = ref(null)
const improveFeedback = ref('')

function openImproveDialog(item) {
  improveItem.value = item
  improveFeedback.value = ''
  showImproveDialog.value = true
}

async function submitImprove() {
  if (!improveFeedback.value.trim()) {
    showToast('请输入改进意见')
    return
  }
  try {
    await api.post(`/api/todos/${improveItem.value.id}/vibe-improve`, {
      feedback: improveFeedback.value.trim(),
    })
    showImproveDialog.value = false
    showToast('已发送改进意见，Claude 将重新修改')
  } catch (e) {
    showToast(e.response?.data?.detail || '操作失败')
  }
}
```

#### confirmVibeVerified → 调用 vibe-commit

```javascript
async function confirmVibeVerified(item) {
  try {
    await showConfirmDialog({
      title: '确认验证通过',
      message: `确认「${item.title}」已验证通过？将自动提交并推送代码。`,
    })
    await api.post(`/api/todos/${item.id}/vibe-commit`)
    showToast('正在提交代码...')

    for (let i = 0; i < 30; i++) {
      await new Promise(r => setTimeout(r, 2000))
      await store.fetchAll()
      const updated = [...store.pending, ...store.completed]
        .find(t => t.id === item.id)
      if (!updated || updated.vibe_status === 'committed') {
        showToast('代码已提交并推送')
        return
      }
      if (updated.vibe_status === 'verifying') {
        showToast('提交失败，请检查日志')
        return
      }
    }
    showToast('提交超时')
  } catch (e) { /* cancelled */ }
}
```

### 4. Watcher 部署

```bash
# 安装依赖
sudo apt-get install -y inotify-tools jq

# 设置 token
export VIBE_TOKEN="your-jwt-token"

# 运行
nohup bash scripts/vibe-watcher.sh >> data/vibe-watcher.log 2>&1 &
```

## 边界情况

| 场景 | 处理方式 |
|------|---------|
| 没有变更可提交 | 直接标记 committed，跳过 commit |
| git push 失败 | 回退到 verifying，用户可重试 |
| Claude session resume 失败 | 自动创建新 session (丢失历史上下文，但功能不中断) |
| 改进和新任务冲突 | Watcher 串行处理，改进信号排在新任务前面处理 |
| 多个信号同时产生 | inotifywait 按到达顺序逐个处理 |
| Watcher 挂了 | 队列文件持久化，重启后自动处理积压 |
| JWT token 过期 | 改用不过期的 API key 或内部 API 路径 |

## 待实现清单

| # | 任务 | 位置 | 说明 |
|---|------|------|------|
| 1 | 移除 _auto_plan 和 rethink-plan | backend router | 不再用后端 LLM |
| 2 | 新增 vibe_session_id 字段 | model + migration | 存储 Claude session ID |
| 3 | 新增 _write_queue_file | backend router | 写队列文件公共函数 |
| 4 | 新增 vibe-claim 端点 | backend router | 认领 |
| 5 | 新增 vibe-replan 端点 (含 comment) | backend router | 三思而行 |
| 6 | 新增 vibe-improve 端点 (含 feedback) | backend router | 改进 |
| 7 | 新增 vibe-commit 端点 | backend router | 提交 |
| 8 | vibe_status 增加 "committing" | router valid list | 过渡态 |
| 9 | verifying 时自动认领下一个任务 | backend router | update_vibe_status 中 |
| 10 | planning→implementing 触发 claim | backend router | 同意时写 claim-{id}.json |
| 11 | 编写 vibe-watcher.sh | scripts/ | 5 种信号 + session 管理 |
| 12 | 前端 rethinkPlan 改造 (输入意见) | TodoView.vue | 弹窗 + 调 vibe-replan |
| 13 | 前端新增"改进"按钮和弹窗 | TodoView.vue | 待验证 tab |
| 14 | 前端 confirmVibeVerified 改造 | TodoView.vue | 调 vibe-commit + 轮询 |
| 15 | 前端"提交中"状态展示 | TodoView.vue | committing loading |
| 16 | 安装 inotify-tools jq | 宿主机 | apt-get install |
| 17 | 部署 watcher | systemd 或 nohup | 常驻运行 |
