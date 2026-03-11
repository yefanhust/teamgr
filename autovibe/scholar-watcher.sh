#!/bin/bash
set -uo pipefail
# NOTE: intentionally NOT using set -e — this is a long-running daemon,
# individual handler errors should not kill the watcher

REPO_DIR="/home/ubuntu/workspace/teamgr"
QUEUE_DIR="$REPO_DIR/data/scholar-queue"
STREAM_DIR="$REPO_DIR/data/scholar-stream"
SESSIONS_DIR="$REPO_DIR/data/scholar-sessions"
CLAUDE="/home/ubuntu/.nvm/versions/node/v20.20.0/bin/claude"
LOG="$REPO_DIR/data/scholar-watcher.log"

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

mkdir -p "$QUEUE_DIR" "$STREAM_DIR" "$SESSIONS_DIR"

SYSTEM_PROMPT='你是「龙图阁大学士」，一位博学多才、见解独到的智囊顾问。

## 角色定位
- 你精通技术、商业、金融、历史、文化等各领域
- 用户会问各种问题，不局限于技术
- 回答要有深度、有见地，不是泛泛而谈

## 工具使用
- 如果问题涉及实时信息（如股价、新闻、最新事件、天气），请主动用 WebSearch 搜索
- 如果需要阅读某个网页的具体内容，请用 WebFetch 获取
- 不确定的信息宁可搜索确认，不要编造

## 文档问答
- 如果用户提供了参考文档，请基于文档内容回答
- 可以结合文档内容和网络搜索给出更全面的分析
- 引用文档内容时标注出处

## 回答风格
- 结构清晰，善用列表和分层
- 先给结论，再展开分析
- 中文回答，专业术语保留英文'

# ========== Session Management ==========

get_session() {
    local conv_id="$1"
    local session_file="$SESSIONS_DIR/$conv_id"
    [ -f "$session_file" ] && cat "$session_file" || echo ""
}

save_session() {
    local conv_id="$1" session_id="$2"
    echo "$session_id" > "$SESSIONS_DIR/$conv_id"
}

# Extract session ID from stream-json output file
extract_session_id() {
    local stream_file="$1"
    # Try sessionId from system init event first
    local sid
    sid=$(grep -m1 '"sessionId"' "$stream_file" 2>/dev/null | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        e = json.loads(line.strip())
        sid = e.get('sessionId') or e.get('session_id', '')
        if sid:
            print(sid)
            break
    except: pass
" 2>/dev/null)
    echo "$sid"
}

# ========== Handle query ==========

handle_query() {
    local file="$1"
    local qid conv_id session_id prompt context

    qid=$(jq -r '.query_id' "$file")
    conv_id=$(jq -r '.conversation_id // empty' "$file")
    session_id=$(jq -r '.session_id // empty' "$file")
    prompt=$(jq -r '.prompt' "$file")
    context=$(jq -r '.context // empty' "$file")
    rm -f "$file"

    local stream_file="$STREAM_DIR/$qid.jsonl"
    local done_file="$STREAM_DIR/$qid.done"

    log_head "Scholar query ${C_MAGENTA}$qid${C_RESET} (conv=${C_BLUE}${conv_id:0:8}${C_RESET})"
    log "Question: ${C_CYAN}${prompt:0:80}${C_RESET}"

    # Build the full prompt
    # For new sessions: include system prompt; for resumed sessions: skip it
    local full_prompt=""
    if [ -z "$session_id" ]; then
        full_prompt="$SYSTEM_PROMPT

"
    fi

    if [ -n "$context" ]; then
        full_prompt+="以下是用户提供的参考文档内容：
---
$context
---

用户问题：$prompt"
    else
        full_prompt+="$prompt"
    fi

    # Build Claude flags
    local flags="--allowedTools WebSearch,WebFetch --verbose --output-format stream-json"

    # Session continuation
    if [ -n "$session_id" ]; then
        flags="--resume $session_id $flags"
        log "Resume session ${C_MAGENTA}${session_id:0:8}${C_RESET}"
    else
        log "New session"
    fi

    # Run Claude via scholar-runner.py
    # scholar-runner.py creates a PTY (to prevent buffering), writes raw stream-json
    # lines to --stream-file, and extracts session ID to --session-file.
    local session_sidecar
    session_sidecar=$(mktemp)

    local rc=0
    python3 "$REPO_DIR/autovibe/scholar-runner.py" \
        --stream-file "$stream_file" \
        --session-file "$session_sidecar" \
        -- $CLAUDE $flags -p "$full_prompt" 2>>"$LOG" || rc=$?

    if [ $rc -ne 0 ] && [ -n "$session_id" ]; then
        log_warn "Resume failed (rc=$rc), trying new session"
        flags="--allowedTools WebSearch,WebFetch --verbose --output-format stream-json"
        python3 "$REPO_DIR/autovibe/scholar-runner.py" \
            --stream-file "$stream_file" \
            --session-file "$session_sidecar" \
            -- $CLAUDE $flags -p "$full_prompt" 2>>"$LOG" || rc=$?
        if [ $rc -ne 0 ]; then
            log_err "Claude CLI failed for query $qid (rc=$rc)"
            echo "{\"type\":\"result\",\"result\":\"Claude 调用失败，请重试\"}" >> "$stream_file"
            touch "$done_file"
            rm -f "$session_sidecar"
            return 1
        fi
    elif [ $rc -ne 0 ]; then
        log_err "Claude CLI failed for query $qid (rc=$rc)"
        echo "{\"type\":\"result\",\"result\":\"Claude 调用失败，请重试\"}" >> "$stream_file"
        touch "$done_file"
        rm -f "$session_sidecar"
        return 1
    fi

    # Save session ID for conversation continuity
    if [ -n "$conv_id" ]; then
        local new_sid=""
        if [ -s "$session_sidecar" ]; then
            new_sid=$(cat "$session_sidecar")
        fi
        # Fall back to extracting from stream output
        if [ -z "$new_sid" ]; then
            new_sid=$(extract_session_id "$stream_file")
        fi
        if [ -n "$new_sid" ]; then
            save_session "$conv_id" "$new_sid"
            log "Session ${C_MAGENTA}${new_sid:0:8}${C_RESET} saved for conv ${C_BLUE}${conv_id:0:8}${C_RESET}"
        else
            log_warn "No session ID captured for conv ${conv_id:0:8}"
        fi
    fi

    rm -f "$session_sidecar"

    # Write done marker
    touch "$done_file"
    log_ok "Query $qid completed"
}

# ========== Main Loop ==========
log_head "Scholar Watcher started, monitoring $QUEUE_DIR"

process_file() {
    local filepath="$1"
    local filename
    filename=$(basename "$filepath")
    [ -f "$filepath" ] || return

    case "$filename" in
        *.json) handle_query "$filepath" || log_err "handle_query failed (rc=$?)" ;;
        *)      log "Ignoring: ${C_DIM}$filename${C_RESET}" ;;
    esac
}

# Process backlog first
for f in "$QUEUE_DIR"/*.json; do
    [ -f "$f" ] || continue
    process_file "$f"
done

# Drain any files that arrived while processing
drain_queue() {
    for f in "$QUEUE_DIR"/*.json; do
        [ -f "$f" ] || continue
        log "Draining backlog: $(basename "$f")"
        process_file "$f"
    done
}

# Continuous monitoring
while read -u 3 filename; do
    sleep 0.3
    process_file "$QUEUE_DIR/$filename"
    drain_queue
done 3< <(inotifywait -m "$QUEUE_DIR" -e create -e moved_to --format '%f' 2>/dev/null)
