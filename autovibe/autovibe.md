# AutoVibe - 自动化 Vibe Coding 工作流

## 概述

AutoVibe 是一个基于 Claude Code CLI 的自动化研发系统。它将任务管理与 AI 编码能力深度集成，实现了从任务认领、代码生成、人工审核到自动提交的完整工作流。

核心理念：**人类负责决策（审批计划、验证结果、提供反馈），AI 负责执行（阅读代码、生成计划、编写代码、生成 commit message）。**

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    前端 (Vue 3)                          │
│  Studio 页面 → 创建 vibe 任务、审核计划、验证结果、提交    │
└──────────────┬──────────────────────────────────────────┘
               │ HTTPS API
┌──────────────▼──────────────────────────────────────────┐
│           后端 (FastAPI, Docker 容器内)                   │
│  API 端点 → 状态流转 → 写信号文件到共享 volume             │
└──────────────┬──────────────────────────────────────────┘
               │ 信号文件 (data/vibe-queue/*.json)
               │ 共享 volume: 容器 /app/data ↔ 宿主机 data/
┌──────────────▼──────────────────────────────────────────┐
│         Vibe Watcher (宿主机 Bash 守护进程)               │
│  inotifywait 监听 → 解析信号 → 调用 Claude Code CLI      │
│  Claude Code → 阅读/修改代码 → 调 API 更新状态            │
└──────────────┬──────────────────────────────────────────┘
               │ git add + commit + push
┌──────────────▼──────────────────────────────────────────┐
│              Git 远程仓库 (GitHub)                        │
└─────────────────────────────────────────────────────────┘
```

### 为什么需要信号文件？

后端运行在 Docker 容器内，没有 git、没有 SSH key、没有 Claude Code CLI。宿主机有这些能力但无法直接接收 API 请求。

解决方案：**共享 volume + 文件信号**。容器写 JSON 文件到 `data/vibe-queue/`，宿主机 Watcher 通过 `inotifywait` 实时监听并处理。

## 任务生命周期

```
┌──────────┐
│   需求    │  (requirement)
│ 创建/编辑 │  用户创建需求，LLM 自动打标
│ 细化描述  │  用户可编辑标题、描述、标签
└────┬─────┘
     │ 用户点击"提交"
     ▼
┌────────┐    复杂任务     ┌────────┐  三思而行  ┌────────┐
│  认领   │──────────────→│ 规划中  │◄──────────│ 重新规划 │
│        │                │planning│───────────→│        │
└───┬────┘                └───┬────┘            └────────┘
    │ 简单任务                 │ 同意
    │                         ▼
    │                   ┌──────────┐
    └──────────────────→│  实现中   │◄─────────────┐
                        │implement │               │
                        └────┬─────┘               │
                             │ Claude 完成          │ 改进
                             ▼                     │
                        ┌──────────┐          ┌────┴────┐
                        │  待验证   │─────────→│  改进中   │
                        │verifying │          │(feedback)│
                        └────┬─────┘          └─────────┘
                             │ 验证通过
                             ▼
                        ┌──────────┐
                        │  提交中   │
                        │committing│
                        └────┬─────┘
                             │ git commit + push
                             ▼
                        ┌──────────┐
                        │  已提交   │
                        │committed │
                        └──────────┘
```

### 状态说明

| 状态 | 含义 | 触发者 |
|------|------|--------|
| `null` | 普通 TODO 任务 | - |
| `requirement` | 需求阶段，等待用户完善后提交 | 用户创建 |
| `planning` | Claude 已分析代码，生成了实现计划，等待人工审核 | Claude |
| `implementing` | Claude 正在按计划修改代码 | 用户提交需求 / 人工同意计划 / Claude 判断为简单任务 |
| `verifying` | Claude 已完成修改，等待人工验证 | Claude |
| `committing` | 正在生成 commit 并推送 | 人工验证通过 |
| `committed` | 代码已提交到远程仓库 | Watcher |

### 人机交互点

1. **创建需求** (requirement)：用户在研发进度页面创建需求，LLM 自动打标，可编辑完善
2. **提交需求**：用户确认需求描述完善后，点击"提交"触发 Claude 处理
3. **审核计划** (planning)：人工查看 Claude 的实现计划，可以「同意」或「三思而行」附带修改意见
4. **验证结果** (verifying)：人工查看 Claude 的变更总结，可以「通过」或「改进」附带反馈意见

## 核心设计原则

### 1. Claude Code 驱动一切

所有代码相关的智能操作（分析复杂度、生成计划、编写代码、总结变更、生成 commit message）均由 Claude Code 完成。Claude Code 拥有完整的代码仓库上下文，能力远超通用 LLM API。

### 2. Session 绑定

每个任务绑定一个 Claude Code session。任务生命周期内的所有交互（规划、重规划、实现、改进、提交）都 resume 同一个 session，确保 Claude 保持对任务的完整上下文理解。Session 在任务 committed 后销毁。

### 3. 串行执行

Watcher 串行处理队列中的信号文件，任何时刻最多一个 Claude Code 实例在运行。这避免了并发冲突（多个 Claude 同时修改代码）和资源竞争。

### 4. 需求驱动

需求由用户手动创建和提交，而非自动触发。用户可以在提交前充分编辑标题、描述和标签，确保需求描述清晰后再交给 Claude 处理。

## 信号文件协议

所有信号文件写入 `data/vibe-queue/` 目录，JSON 格式。

| 文件名 | 触发时机 | 内容 |
|--------|---------|------|
| `claim.json` | 新建 vibe 任务 / 自动认领 | `{id, title, description}` |
| `claim-{id}.json` | 同意计划进入实现 | `{id, title, description, vibe_plan}` |
| `plan-{id}.json` | 三思而行 | `{id, title, description, current_plan, comment}` |
| `improve-{id}.json` | 提出改进意见 | `{id, title, description, summary, feedback}` |
| `commit-{id}.json` | 验证通过，提交 | `{id, title, summary}` |

## 组件详解

### 1. Vibe Watcher (`vibe-watcher.sh`)

宿主机上的 Bash 守护进程，核心循环：

```
启动 → 处理积压的 JSON 文件 → inotifywait 监听新文件 → 调用对应 handler → 循环
```

**关键实现细节：**

- **不使用 `set -e`**：长时间运行的守护进程不能因为单个 handler 错误而退出。每个 handler 用 `|| log "ERROR: ..."` 捕获错误。
- **进程替代避免子 shell**：`while read ... done < <(inotifywait ...)` 而非 `inotifywait | while read ...`，后者会在子 shell 中执行循环体，导致变量修改不可见。
- **自动生成 JWT**：直接调用后端的 `get_jwt_secret()` 生成长期有效的 token，无需手动配置。
- **Session 文件存储**：`data/vibe-sessions/{task_id}` 文件存储 Claude session ID，简单高效。

**五种信号处理器：**

| Handler | 信号 | 行为 |
|---------|------|------|
| `handle_claim` | claim / claim-{id} | 新建或恢复 session，Claude 判断复杂度或按 plan 实现 |
| `handle_replan` | plan-{id} | Resume session，Claude 根据人工意见重新规划 |
| `handle_improve` | improve-{id} | Resume session，Claude 根据反馈修改代码 |
| `handle_commit` | commit-{id} | Resume session，Claude 生成 commit msg，git commit + push |

### 2. Claude PTY 包装器 (`claude-pty.py`)

解决 Claude Code CLI 的输出问题：

**问题**：`claude -p` 模式在 stdout 不是终端时会缓冲输出，即使使用 `--output-format stream-json` 也无法实时获取进度。

**方案**：Python 脚本创建伪终端 (pty)，让 Claude 以为自己在真正的终端中运行，从而实时刷新 stream-json 输出。

```
Watcher → claude-pty.py → [pty] → claude CLI
                ↑                      ↓
           解析 JSON 事件        stream-json 事件
           显示实时进度          (因 pty 实时刷新)
           保存最终结果
```

**主要功能：**

- **PTY 创建**：`pty.openpty()` + 禁用 OPOST（防止 CR/LF 转换）
- **实时解析**：解析 Claude Code stream-json 事件（`system`、`assistant`、`result` 类型）
- **时间戳 + 耗时**：每个步骤显示 `[HH:MM:SS]` 时间戳，上一步骤完成时追加耗时 `(Xs)`
- **工具摘要**：显示 Claude 使用的工具名称和关键参数（文件路径、命令、搜索模式等）
- **结果提取**：从 `result` 事件中提取最终文本，保存到 `--output-file` 供 Watcher 使用

**Claude Code stream-json 格式**（非 Anthropic API SSE 格式）：

```json
{"type": "system", "subtype": "init", "model": "claude-opus-4-6"}
{"type": "assistant", "message": {"content": [{"type": "text", "text": "..."}, {"type": "tool_use", "name": "Read", "input": {"file_path": "..."}}]}}
{"type": "user", ...}
{"type": "result", "result": "最终文本", "cost_usd": 0.05, "duration_ms": 30000}
```

### 3. 后端 API 端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/todos/requirements` | POST | 创建需求（vibe_status=requirement），LLM 自动打标 |
| `/api/todos/{id}/vibe-submit` | POST | 提交需求，触发 Claude Code 处理 |
| `/api/todos/{id}/vibe-status` | PUT | Claude 更新任务状态和计划/总结 |
| `/api/todos/{id}/vibe-replan` | POST | 三思而行：附带修改意见 |
| `/api/todos/{id}/vibe-improve` | POST | 改进：附带反馈意见 |
| `/api/todos/{id}/vibe-commit` | POST | 验证通过，触发提交 |

### 4. 数据模型扩展

TodoItem 新增字段：

| 字段 | 类型 | 用途 |
|------|------|------|
| `vibe_status` | String(20) | 当前状态：requirement / planning / implementing / verifying / committing / committed |
| `vibe_plan` | Text | Claude 生成的实现计划 (Markdown) |
| `vibe_summary` | Text | Claude 生成的变更总结 (Markdown) |
| `vibe_commit_id` | String(40) | 关联的 git commit hash |

## 部署与运维

### 前置要求

| 环境 | 要求 |
|------|------|
| 宿主机 | Claude Code CLI、git + SSH push 权限、inotify-tools、jq、tmux |
| Docker | 后端容器可读写 `data/` 目录 |

### 启动 Watcher

```bash
# 安装依赖（仅首次）
sudo apt-get install -y inotify-tools jq tmux

# 创建 tmux session 启动 watcher
tmux new-session -s autovibe "bash autovibe/vibe-watcher.sh 2>&1 | tee -a data/vibe-watcher.log"

# 查看实时输出
tmux attach -t autovibe

# 脱离 tmux（watcher 继续运行）：Ctrl+B 然后 D

# 停止 watcher
tmux kill-session -t autovibe
```

### 实时输出示例

Watcher 在 tmux 中显示 Claude 的每一步操作：

```
[2026-03-07 14:30:01] === Claim task #42: vibe: 优化搜索性能 ===
[2026-03-07 14:30:01] New session for task #42
  [14:30:02] init  model=claude-opus-4-6
  [14:30:03] 让我先阅读相关代码...  (1.2s)
  [14:30:05] [tool] Read  backend/app/routers/talents.py  (2.1s)
  [14:30:08] [tool] Read  backend/app/services/llm_service.py  (3.2s)
  [14:30:12] [tool] Grep  /search/  backend/  (4.0s)
  [14:30:15] 这是一个简单任务，我直接实现...  (3.5s)
  [14:30:18] [tool] Edit  backend/app/routers/talents.py  (2.8s)
  [14:30:25] [tool] Bash  cd backend && python -m pytest tests/  (7.2s)
  [14:30:28] [tool] Bash  curl -sk -X PUT ...  (2.5s)

  [14:30:29] [done] $0.0523 29.1s
[2026-03-07 14:30:29] === Task #42 processing complete ===
```

### 边界情况处理

| 场景 | 处理方式 |
|------|---------|
| 没有变更可提交 | 直接标记 committed，跳过 git commit |
| git push 失败 | 回退到 verifying，用户可重试 |
| Claude session resume 失败 | 自动创建新 session（丢失上下文但不中断） |
| Watcher 意外退出 | 队列文件持久化，重启后自动处理积压 |
| 多个信号同时到达 | inotifywait 按到达顺序逐个串行处理 |
| 任务标题去掉 vibe 前缀 | 自动清除 vibe 相关字段，退出研发流程 |

## 文件清单

```
autovibe/
├── autovibe.md              # 本文档
├── vibe-watcher.sh          # Watcher 守护进程
├── claude-pty.py            # PTY 包装器 + stream-json 解析器
└── claude-stream-parser.py  # 独立 stream-json 解析器（备用，功能已集成到 claude-pty.py）
```

## 关键经验

### Claude Code CLI 的输出行为

- `claude -p` 在非 tty 环境下**不输出**任何中间结果，只有最终 result
- `--output-format stream-json` 可以流式输出 JSON 事件，但需要配合 `--verbose`
- 即使使用 stream-json，stdout 为 pipe 时仍会缓冲——必须使用 pty 才能实时刷新

### Claude Code stream-json vs Anthropic API SSE

两者格式完全不同：
- **Anthropic API**：`content_block_start` → `content_block_delta` × N → `content_block_stop`（增量式）
- **Claude Code CLI**：每个 `assistant` 事件包含完整的 `message.content` 数组（完整式）

### Bash 守护进程的稳定性

- `set -e` 会让长时间运行的脚本在任何非零退出码时崩溃——守护进程不应使用
- 用 `|| log "ERROR: ..."` 替代，让错误可见但不致命
- `inotifywait | while read` 会让 while 在子 shell 中运行，用进程替代 `< <(...)` 避免
