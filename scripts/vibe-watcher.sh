#!/bin/bash
set -euo pipefail

REPO_DIR="/home/ubuntu/workspace/teamgr"
QUEUE_DIR="$REPO_DIR/data/vibe-queue"
SESSIONS_DIR="$REPO_DIR/data/vibe-sessions"
API="https://localhost:6443/api/todos"
CLAUDE="/home/ubuntu/.nvm/versions/node/v20.20.0/bin/claude"
LOG="$REPO_DIR/data/vibe-watcher.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

# Generate a fresh JWT token using the backend's own secret
generate_token() {
    cd "$REPO_DIR/backend"
    python3 -c "
from app.config import get_jwt_secret
from jose import jwt
from datetime import datetime, timedelta
payload = {'exp': datetime.utcnow() + timedelta(days=365), 'sub': 'admin'}
print(jwt.encode(payload, get_jwt_secret(), algorithm='HS256'))
"
}

TOKEN="${VIBE_TOKEN:-$(generate_token)}"
api_call() { curl -sk -H "Authorization: Bearer $TOKEN" "$@"; }

mkdir -p "$QUEUE_DIR" "$SESSIONS_DIR"

# ========== Session Management ==========

get_session() {
    local task_id="$1"
    local session_file="$SESSIONS_DIR/$task_id"
    [ -f "$session_file" ] && cat "$session_file" || echo ""
}

save_session() {
    local task_id="$1" session_id="$2"
    echo "$session_id" > "$SESSIONS_DIR/$task_id"
}

end_session() {
    local task_id="$1"
    rm -f "$SESSIONS_DIR/$task_id"
}

# Extract session ID from Claude's output/state
get_latest_session_id() {
    # Claude stores conversations in project dirs
    local conv_dir
    conv_dir=$(find ~/.claude/projects/ -name "conversations" -type d 2>/dev/null | head -1)
    if [ -n "$conv_dir" ] && [ -d "$conv_dir" ]; then
        ls -t "$conv_dir"/ 2>/dev/null | head -1 | sed 's/\.json$//'
    fi
}

# Run Claude, managing session create/resume
# Usage: run_claude <task_id> <prompt>
# Uses --output-format stream-json for real-time progress display
# Final result (assistant text) is returned via stdout for caller capture
run_claude() {
    local task_id="$1"
    local prompt="$2"
    local session_id
    session_id=$(get_session "$task_id")

    cd "$REPO_DIR"

    # --dangerously-skip-permissions: 非交互模式下必须跳过权限确认，否则进程会卡住
    local CLAUDE_FLAGS="--dangerously-skip-permissions --output-format stream-json"
    local tmpout
    tmpout=$(mktemp)

    # Parse stream-json: display events in real-time, extract final assistant message
    _stream_and_extract() {
        "$@" 2>>"$LOG" | while IFS= read -r line; do
            local type
            type=$(echo "$line" | jq -r '.type // empty' 2>/dev/null)
            case "$type" in
                assistant)
                    # Extract and display assistant text content
                    local text
                    text=$(echo "$line" | jq -r '.message.content[]? | select(.type=="text") | .text // empty' 2>/dev/null)
                    [ -n "$text" ] && log "[Claude] $text"
                    ;;
                content_block_delta)
                    # Streaming text delta
                    local delta
                    delta=$(echo "$line" | jq -r '.delta.text // empty' 2>/dev/null)
                    [ -n "$delta" ] && printf '%s' "$delta" >&2
                    ;;
                content_block_stop)
                    printf '\n' >&2
                    ;;
                result)
                    # Final result — extract full text, save to tmpout for caller
                    local result_text
                    result_text=$(echo "$line" | jq -r '.result // empty' 2>/dev/null)
                    if [ -n "$result_text" ]; then
                        echo "$result_text" > "$tmpout"
                        log "[Claude] === Done ==="
                    fi

                    # Check for subtype (e.g. tool_use)
                    local subtype
                    subtype=$(echo "$line" | jq -r '.subtype // empty' 2>/dev/null)
                    [ -n "$subtype" ] && log "[Claude event] $subtype"
                    ;;
                system)
                    local sys_msg
                    sys_msg=$(echo "$line" | jq -r '.message // .subtype // empty' 2>/dev/null)
                    [ -n "$sys_msg" ] && log "[System] $sys_msg"
                    ;;
                *)
                    # Log other event types for debugging
                    [ -n "$type" ] && log "[Event] $type"
                    ;;
            esac
        done
        # Return the pipeline exit status of the Claude process
        return ${PIPESTATUS[0]}
    }

    if [ -n "$session_id" ]; then
        log "Resume session $session_id for task #$task_id"
        if _stream_and_extract $CLAUDE --resume "$session_id" $CLAUDE_FLAGS -p "$prompt"; then
            cat "$tmpout" 2>/dev/null
        else
            log "Resume failed, creating new session"
            _stream_and_extract $CLAUDE $CLAUDE_FLAGS -p "$prompt" || {
                log "Claude CLI failed: task #$task_id"
                rm -f "$tmpout"
                return 1
            }
            local new_sid
            new_sid=$(get_latest_session_id)
            [ -n "$new_sid" ] && save_session "$task_id" "$new_sid"
            cat "$tmpout" 2>/dev/null
        fi
    else
        log "New session for task #$task_id"
        _stream_and_extract $CLAUDE $CLAUDE_FLAGS -p "$prompt" || {
            log "Claude CLI failed: task #$task_id"
            rm -f "$tmpout"
            return 1
        }
        local new_sid
        new_sid=$(get_latest_session_id)
        [ -n "$new_sid" ] && save_session "$task_id" "$new_sid"
        cat "$tmpout" 2>/dev/null
    fi

    rm -f "$tmpout"
}

# ========== Handle claim signal (new task, new session) ==========
handle_claim() {
    local file="$1"
    local task_id title description plan
    task_id=$(jq -r '.id' "$file")
    title=$(jq -r '.title' "$file")
    description=$(jq -r '.description // empty' "$file")
    plan=$(jq -r '.vibe_plan // empty' "$file")
    rm -f "$file"

    log "=== Claim task #$task_id: $title ==="

    if [ -n "$plan" ]; then
        # Has plan → resume session, implement per plan
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
        # No plan → new session, Claude judges complexity
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

    log "=== Task #$task_id processing complete ==="
}

# ========== Handle replan signal (三思而行, resume session) ==========
handle_replan() {
    local file="$1"
    local task_id title description current_plan comment
    task_id=$(jq -r '.id' "$file")
    title=$(jq -r '.title' "$file")
    description=$(jq -r '.description // empty' "$file")
    current_plan=$(jq -r '.current_plan // empty' "$file")
    comment=$(jq -r '.comment // empty' "$file")
    rm -f "$file"

    log "=== Replan task #$task_id: $title ==="

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

    log "=== Replan #$task_id complete ==="
}

# ========== Handle improve signal (resume session) ==========
handle_improve() {
    local file="$1"
    local task_id title description summary feedback
    task_id=$(jq -r '.id' "$file")
    title=$(jq -r '.title' "$file")
    description=$(jq -r '.description // empty' "$file")
    summary=$(jq -r '.summary // empty' "$file")
    feedback=$(jq -r '.feedback // empty' "$file")
    rm -f "$file"

    log "=== Improve task #$task_id: $title ==="

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

    log "=== Improve #$task_id complete ==="
}

# ========== Handle commit signal (resume session, then end it) ==========
handle_commit() {
    local file="$1"
    local task_id title summary
    task_id=$(jq -r '.id' "$file")
    title=$(jq -r '.title' "$file")
    summary=$(jq -r '.summary // empty' "$file")
    rm -f "$file"

    log "=== Commit task #$task_id: $title ==="

    cd "$REPO_DIR"

    # Check if there are changes to commit
    if git diff --quiet HEAD 2>/dev/null && [ -z "$(git status --porcelain)" ]; then
        log "No changes to commit, marking as committed"
        api_call -X PUT "$API/$task_id/vibe-status" \
            -H "Content-Type: application/json" \
            -d '{"status": "committed"}' > /dev/null
        api_call -X POST "$API/$task_id/complete" > /dev/null
        api_call -X POST "$API/$task_id/check-commit" > /dev/null
        end_session "$task_id"
        return 0
    fi

    # Resume session — Claude generates commit message based on git diff
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
        log "Claude commit msg generation failed, using fallback"
    }

    git add -A
    git commit -m "$commit_msg"

    if git push origin master; then
        local commit_hash
        commit_hash=$(git rev-parse HEAD)
        log "Push successful: $commit_hash"
        api_call -X PUT "$API/$task_id/vibe-status" \
            -H "Content-Type: application/json" \
            -d '{"status": "committed"}' > /dev/null
        api_call -X POST "$API/$task_id/complete" > /dev/null
        api_call -X POST "$API/$task_id/check-commit" > /dev/null
        log "=== Task #$task_id committed and pushed ==="
    else
        log "Push failed, reverting to verifying"
        api_call -X PUT "$API/$task_id/vibe-status" \
            -H "Content-Type: application/json" \
            -d '{"status": "verifying"}' > /dev/null
    fi

    end_session "$task_id"
}

# ========== Main Loop ==========
log "Vibe Watcher started, monitoring $QUEUE_DIR"

process_file() {
    local filepath="$1"
    local filename
    filename=$(basename "$filepath")
    [ -f "$filepath" ] || return

    case "$filename" in
        claim.json)      handle_claim "$filepath" ;;
        claim-*.json)    handle_claim "$filepath" ;;
        plan-*.json)     handle_replan "$filepath" ;;
        improve-*.json)  handle_improve "$filepath" ;;
        commit-*.json)   handle_commit "$filepath" ;;
        *)               log "Ignoring: $filename" ;;
    esac
}

# Process backlog first
for f in "$QUEUE_DIR"/*.json; do
    [ -f "$f" ] || continue
    process_file "$f"
done

# Continuous monitoring
inotifywait -m "$QUEUE_DIR" -e create -e moved_to --format '%f' 2>/dev/null | while read filename; do
    sleep 0.5
    process_file "$QUEUE_DIR/$filename"
done
