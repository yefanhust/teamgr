#!/bin/bash
set -uo pipefail
# NOTE: intentionally NOT using set -e — this is a long-running daemon,
# individual handler errors should not kill the watcher

REPO_DIR="/home/ubuntu/workspace/teamgr"
QUEUE_DIR="$REPO_DIR/data/vibe-queue"
SESSIONS_DIR="$REPO_DIR/data/vibe-sessions"
API="https://localhost:6443/api/todos"
CLAUDE="/home/ubuntu/.nvm/versions/node/v20.20.0/bin/claude"
CLAUDE_PTY="python3 $REPO_DIR/autovibe/claude-pty.py"
LOG="$REPO_DIR/data/vibe-watcher.log"

# ANSI colors
C_RESET='\033[0m'
C_DIM='\033[2m'
C_BOLD='\033[1m'
C_CYAN='\033[36m'
C_GREEN='\033[32m'
C_YELLOW='\033[33m'
C_RED='\033[31m'
C_MAGENTA='\033[35m'
C_BLUE='\033[34m'

log()      { echo -e "${C_DIM}[$(date '+%Y-%m-%d %H:%M:%S')]${C_RESET} $*"; }
log_head() { echo -e "${C_DIM}[$(date '+%Y-%m-%d %H:%M:%S')]${C_RESET} ${C_BOLD}${C_CYAN}=== $* ===${C_RESET}"; }
log_ok()   { echo -e "${C_DIM}[$(date '+%Y-%m-%d %H:%M:%S')]${C_RESET} ${C_GREEN}✔ $*${C_RESET}"; }
log_warn() { echo -e "${C_DIM}[$(date '+%Y-%m-%d %H:%M:%S')]${C_RESET} ${C_YELLOW}⚠ $*${C_RESET}"; }
log_err()  { echo -e "${C_DIM}[$(date '+%Y-%m-%d %H:%M:%S')]${C_RESET} ${C_RED}✘ $*${C_RESET}"; }

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

# Extract session ID from claude-pty.py sidecar file
get_latest_session_id() {
    local sidecar="${CLAUDE_OUTPUT_FILE}.session"
    if [ -f "$sidecar" ]; then
        cat "$sidecar"
        rm -f "$sidecar"
    fi
}

# Run Claude with --output-format stream-json for real-time progress.
# `claude -p` writes NOTHING to stdout until completion (not even with a tty),
# but --output-format stream-json streams JSON events line by line as it works.
# We parse these events via a Python script for human-readable output.
# Final result saved to $CLAUDE_OUTPUT_FILE for callers (e.g. commit message).
CLAUDE_OUTPUT_FILE=""
run_claude() {
    local task_id="$1"
    local prompt="$2"
    local session_id
    session_id=$(get_session "$task_id")

    cd "$REPO_DIR"

    CLAUDE_OUTPUT_FILE=$(mktemp)
    local base_flags="--dangerously-skip-permissions --verbose --output-format stream-json"

    if [ -n "$session_id" ]; then
        log "Resume session ${C_MAGENTA}${session_id:0:8}${C_RESET} for task ${C_BOLD}#$task_id${C_RESET}"
    else
        log "New session for task ${C_BOLD}#$task_id${C_RESET}"
    fi

    _run_stream() {
        local flags="$1"
        local rc=0
        python3 "$REPO_DIR/autovibe/claude-pty.py" --output-file "$CLAUDE_OUTPUT_FILE" -- \
            $CLAUDE $flags -p "$prompt" 2>>"$LOG" || rc=$?
        return $rc
    }

    local session_flag=""
    [ -n "$session_id" ] && session_flag="--resume $session_id"

    _run_stream "$session_flag $base_flags"
    local rc=$?

    if [ $rc -ne 0 ] && [ -n "$session_id" ]; then
        log_warn "Resume failed, creating new session"
        _run_stream "$base_flags"
        rc=$?
        if [ $rc -ne 0 ]; then
            log_err "Claude CLI failed: task #$task_id"
            rm -f "$CLAUDE_OUTPUT_FILE"
            return 1
        fi
        local new_sid
        new_sid=$(get_latest_session_id)
        [ -n "$new_sid" ] && save_session "$task_id" "$new_sid"
    elif [ $rc -ne 0 ]; then
        log "Claude CLI failed: task #$task_id"
        rm -f "$CLAUDE_OUTPUT_FILE"
        return 1
    else
        if [ -z "$session_id" ]; then
            local new_sid
            new_sid=$(get_latest_session_id)
            if [ -n "$new_sid" ]; then
                save_session "$task_id" "$new_sid"
                log "Saved session ${C_MAGENTA}${new_sid:0:8}${C_RESET} for task ${C_BOLD}#$task_id${C_RESET}"
            else
                log_warn "No session ID captured for task #$task_id"
            fi
        fi
    fi
}

# ========== Service rebuild ==========

has_code_changes() {
    cd "$REPO_DIR"
    # Check tracked file modifications
    if ! git diff --quiet HEAD 2>/dev/null; then
        return 0
    fi
    # Check untracked files (excluding gitignored)
    if [ -n "$(git ls-files --others --exclude-standard 2>/dev/null)" ]; then
        return 0
    fi
    return 1
}

rebuild_service() {
    log_head "Rebuilding service"
    cd "$REPO_DIR"
    local dc="docker-compose -f docker/docker-compose.yml"
    if $dc rm -sf teamgr && $dc up -d --build teamgr && sleep 2 && $dc exec -T teamgr /workspace/scripts/start_web.sh; then
        log_ok "Service rebuilt successfully"
    else
        log_err "Service rebuild failed"
    fi
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

    log_head "Claim task #$task_id: $title"

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

    if has_code_changes; then
        rebuild_service
    fi

    log_ok "Task #$task_id processing complete"
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

    log_head "Replan task #$task_id: $title"

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

    log_ok "Replan #$task_id complete"
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

    log_head "Improve task #$task_id: $title"

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

    if has_code_changes; then
        rebuild_service
    fi

    log_ok "Improve #$task_id complete"
}

# ========== Handle commit signal (resume session, then end it) ==========
handle_commit() {
    local file="$1"
    local task_id title summary
    task_id=$(jq -r '.id' "$file")
    title=$(jq -r '.title' "$file")
    summary=$(jq -r '.summary // empty' "$file")
    rm -f "$file"

    log_head "Commit task #$task_id: $title"

    cd "$REPO_DIR"

    # Check if there are changes to commit
    if git diff --quiet HEAD 2>/dev/null && [ -z "$(git status --porcelain)" ]; then
        log_warn "No changes to commit, marking as committed"
        api_call -X PUT "$API/$task_id/vibe-status" \
            -H "Content-Type: application/json" \
            -d '{"status": "committed"}' > /dev/null
        api_call -X POST "$API/$task_id/complete" > /dev/null
        end_session "$task_id"
        return 0
    fi

    # Resume session — Claude generates commit message based on git diff
    run_claude "$task_id" "请查看 git status 和 git diff，为这些变更生成 commit message。

相关任务: $title
变更总结 (仅供参考，请基于实际 diff):
$summary

格式:
- 第一行: feat/fix/refactor: 简短描述
- 空行
- 正文: bullet points 列出主要变更
- 空行
- Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

只输出 commit message，不要其他内容，不要代码块。"

    local commit_msg
    if [ -s "$CLAUDE_OUTPUT_FILE" ]; then
        commit_msg=$(cat "$CLAUDE_OUTPUT_FILE")
        rm -f "$CLAUDE_OUTPUT_FILE"
    else
        commit_msg="$title

$summary

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
        log_warn "Claude commit msg generation failed, using fallback"
    fi

    git add -A
    git commit -m "$commit_msg"

    if git push origin master; then
        local commit_hash
        commit_hash=$(git rev-parse HEAD)
        log_ok "Push successful: ${C_MAGENTA}${commit_hash:0:8}${C_RESET}"
        api_call -X PUT "$API/$task_id/vibe-status" \
            -H "Content-Type: application/json" \
            -d "{\"status\": \"committed\", \"commit_id\": \"$commit_hash\"}" > /dev/null
        api_call -X POST "$API/$task_id/complete" > /dev/null
        log_ok "Task #$task_id committed and pushed"
    else
        log_err "Push failed, reverting to verifying"
        api_call -X PUT "$API/$task_id/vibe-status" \
            -H "Content-Type: application/json" \
            -d '{"status": "verifying"}' > /dev/null
    fi

    end_session "$task_id"
}

# ========== Main Loop ==========
log_head "Vibe Watcher started, monitoring $QUEUE_DIR"

process_file() {
    local filepath="$1"
    local filename
    filename=$(basename "$filepath")
    [ -f "$filepath" ] || return

    # Use || true to prevent set -e from killing the watcher on handler errors
    case "$filename" in
        claim.json)      handle_claim "$filepath"   || log_err "handle_claim failed (rc=$?)" ;;
        claim-*.json)    handle_claim "$filepath"    || log_err "handle_claim failed (rc=$?)" ;;
        plan-*.json)     handle_replan "$filepath"   || log_err "handle_replan failed (rc=$?)" ;;
        improve-*.json)  handle_improve "$filepath"  || log_err "handle_improve failed (rc=$?)" ;;
        commit-*.json)   handle_commit "$filepath"   || log_err "handle_commit failed (rc=$?)" ;;
        *)               log "Ignoring: ${C_DIM}$filename${C_RESET}" ;;
    esac
}

# Process backlog first
for f in "$QUEUE_DIR"/*.json; do
    [ -f "$f" ] || continue
    process_file "$f"
done

# Drain any files that arrived while we were busy processing
drain_queue() {
    for f in "$QUEUE_DIR"/*.json; do
        [ -f "$f" ] || continue
        log "Draining backlog: $(basename "$f")"
        process_file "$f"
    done
}

# Continuous monitoring — use fd 3 so child processes (docker-compose, claude)
# don't accidentally consume inotifywait events from stdin
while read -u 3 filename; do
    sleep 0.5
    process_file "$QUEUE_DIR/$filename"
    drain_queue
done 3< <(inotifywait -m "$QUEUE_DIR" -e create -e moved_to --format '%f' 2>/dev/null)
