# 龙图阁大学士 - AI 问答助手系统

## 概述

龙图阁大学士是一个 AI 驱动的智能问答助手，运行在 TeaMgr 的「龙图阁」标签页下。用户可以向大学士提出任何问题，大学士会联网搜索实时信息、分析上传的 PDF 文档，并给出有深度的回答。

核心约束：**使用 Claude Code CLI（Max Plan），而非 Anthropic API**。因此整个架构基于信号文件 + 宿主机守护进程，与 AutoVibe 的 Vibe Watcher 共享相同的架构模式。

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                前端 ScholarChat.vue                       │
│  提问 → 上传PDF → SSE流式接收 → Markdown渲染 → 历史对话   │
└──────────────┬──────────────────────────────────────────┘
               │ HTTPS API
┌──────────────▼──────────────────────────────────────────┐
│         后端 FastAPI (Docker 容器内)                       │
│  /ask → 写信号文件    /stream/{qid} → 尾读stream文件(SSE) │
│  /upload → PDF文本提取  /conversations → 历史管理          │
└──────────────┬──────────────────────────────────────────┘
               │ 信号文件 (data/scholar-queue/*.json)
               │ 共享 volume
┌──────────────▼──────────────────────────────────────────┐
│       Scholar Watcher (宿主机 Bash 守护进程)               │
│  inotifywait → 读取信号 → scholar-runner.py → Claude CLI │
│  输出 → data/scholar-stream/{qid}.jsonl                   │
└─────────────────────────────────────────────────────────┘
```

### 三 ID 体系

| ID | 作用 | 生命周期 |
|----|------|----------|
| `query_id` | 每次提问的唯一标识 | 单次问答，用于命名 stream 文件 |
| `conversation_id` | 对话组标识 | 一组多轮问答，UI 分组用 |
| `session_id` | Claude CLI session | 跟随 conversation，`--resume` 实现多轮 |

### 为什么需要 PTY 包装器？

Claude Code CLI 在检测到非 TTY 的 stdout 时会缓冲输出，导致后端无法实时读取流式数据。`scholar-runner.py` 创建伪终端（PTY）让 Claude 以为在终端中运行，从而获得逐行输出。

## 关键文件

| 文件 | 位置 | 作用 |
|------|------|------|
| `ScholarChat.vue` | `frontend/src/components/` | 前端聊天 UI |
| `scholar.py` | `backend/app/routers/` | API 路由（6 个端点） |
| `scholar_service.py` | `backend/app/services/` | 核心业务逻辑 |
| `scholar-watcher.sh` | `autovibe/` | 宿主机守护进程 |
| `scholar-runner.py` | `autovibe/` | Claude CLI PTY 包装器 |

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/scholar/upload` | 上传 PDF/文本文件 |
| POST | `/api/scholar/ask` | 提交问题，返回 query_id |
| GET | `/api/scholar/stream/{qid}` | SSE 流式接收回答 |
| GET | `/api/scholar/conversations` | 获取对话列表 |
| GET | `/api/scholar/conversations/categorized` | 获取 LLM 分类后的对话列表（带缓存） |
| GET | `/api/scholar/conversations/{id}` | 获取单个对话详情（含历史问答） |
| DELETE | `/api/scholar/conversations/{id}` | 删除对话 |

## 数据流详解

### 1. 提问流程

```
用户输入 → POST /ask → 后端生成 query_id
  → 写信号文件: data/scholar-queue/{qid}.json
  → 更新对话记录: data/scholar-conversations.json
  → 返回 {query_id, conversation_id}

前端拿到 query_id → GET /stream/{qid} (SSE)
```

### 2. Watcher 处理

```
inotifywait 检测到新 .json → handle_query()
  → 解析信号: qid, conv_id, session_id, prompt, context
  → 构建 full_prompt (系统提示 + 文档上下文 + 用户问题)
  → scholar-runner.py → Claude CLI (PTY)
  → 原始 stream-json 输出 → data/scholar-stream/{qid}.jsonl
  → 提取 session_id → data/scholar-sessions/{conv_id}
  → 写完成标记: data/scholar-stream/{qid}.done
```

### 3. SSE 流式传输

```
后端 stream_response() 异步生成器:
  → 轮询 {qid}.jsonl 文件 (二进制模式, byte offset 追踪)
  → 解析 stream-json events → 转换为前端友好格式
  → 通过 SSE 推送: data: {"type":"text","content":"..."}\n\n
  → 同时积累回答文本
  → 流结束时保存回答到对话记录
```

### 4. 前端 SSE 消费

```
fetch ReadableStream → 逐行解析 SSE
  → thinking: 折叠显示思考过程
  → tool_use: WebSearch/WebFetch 动态展示
  → text: 实时渲染 Markdown (含表格)
  → done: 停止 loading 状态
```

## 多轮对话机制

1. 首次提问：无 session_id，Watcher 在 prompt 前注入系统提示
2. Claude 返回结果，Watcher 从输出中提取 session_id 并保存
3. 后续提问：携带 session_id，Watcher 使用 `--resume {session_id}` 继续
4. 如果 resume 失败，自动降级为新 session 重试

## 历史对话分类

- 打开历史面板时调用 `/conversations/categorized`
- 后端将所有对话标题/问题发给 LLM，要求按主题分为 2-6 类
- 分类结果缓存到 `data/scholar-category-cache.json`
- 缓存基于对话 ID 集合的 MD5 指纹，只有新增/删除对话时才重新分类
- 分类模型可在设置页面配置（Studio 分组 → 大学士-历史对话分类）

## 前端 Markdown 渲染

自研轻量 Markdown 渲染器（未引入第三方库），支持：
- 代码块 (```), 行内代码
- 加粗、斜体
- 标题 (h1-h4)
- 有序/无序列表
- Pipe 表格 (`| col | col |`)
- Markdown 链接 `[text](url)`
- 裸 URL 自动链接
- HTML 转义（防 XSS）

## 踩过的坑

### 1. Claude CLI 输出缓冲

**问题**：直接 `subprocess.Popen` 运行 Claude CLI，stdout 重定向到文件后，输出被缓冲，后端无法实时读取。

**原因**：Claude CLI 检测到 stdout 不是 TTY 时，启用全缓冲（glibc 的默认行为）。

**解决**：`scholar-runner.py` 使用 `pty.openpty()` 创建伪终端，让 Claude 以为在终端中运行。同时 `termios.OPOST` 关闭输出后处理，确保原始 JSON 不被终端转义。

**教训**：不能直接复用 `claude-pty.py`（AutoVibe 的），因为它将输出格式化为人类可读的终端文本（ANSI 颜色等），而 Scholar 需要原始 stream-json 行。

### 2. Stream 文件 byte offset 错乱

**问题**：后端 `stream_response()` 读取 `.jsonl` 文件时，使用 text 模式 `open()` + `f.seek(pos)` + `pos += len(new_data.encode("utf-8"))`，偶尔出现数据重复或丢失。

**原因**：Python text 模式的 `f.seek()` 使用的是「不透明位置」，不等于字节偏移。混用 byte 长度计算和 text seek 导致位置不一致。

**解决**：改为二进制模式 `open(stream_file, "rb")`，`pos += len(new_data)` 直接按字节追踪，然后 `new_data.decode("utf-8", errors="replace")` 手动解码。

### 3. --output-format=stream-json 需要 --verbose

**问题**：Claude CLI 报错 `--output-format=stream-json requires --verbose`。

**原因**：`stream-json` 格式只在 verbose 模式下可用，这是 Claude CLI 的限制。

**解决**：在 `scholar-watcher.sh` 的 flags 中加上 `--verbose`。

### 4. Session resume 偶尔失败

**问题**：`--resume {session_id}` 偶尔返回非零退出码。

**原因**：Claude CLI session 可能过期或损坏。

**解决**：Watcher 中加入 fallback 逻辑：如果 resume 失败且有 session_id，则去掉 `--resume` 重新发起新 session。

### 5. 历史对话只有问题没有回答

**问题**：加载历史对话时只显示用户的问题，不显示大学士的回答。

**原因**：`create_or_update_conversation()` 只保存了 `question`，没有保存 `answer`。

**解决**：在 `stream_response()` 中积累所有 `text` 类型事件的内容，流结束时调用 `update_conversation_answer()` 将完整回答写入对话记录。前端 `loadConversation()` 同时读取 `msg.answer` 并渲染。

### 6. 历史分类每次都调 LLM

**问题**：每次打开历史面板都要等待 LLM 分类，几秒延迟。

**原因**：没有缓存，每次都重新发 prompt 给 LLM。

**解决**：引入 `scholar-category-cache.json`，存储分类结果 + 对话 ID 集合的 MD5 指纹。只有对话列表变化（新增/删除）时才重新分类，否则直接读缓存（但用最新的 message_count/updated_at 刷新元数据）。

### 7. Markdown 表格显示为纯文本

**问题**：Claude 回答中的 pipe 表格 `| col | col |` 显示为纯文本。

**原因**：自研 Markdown 渲染器最初没有表格支持。

**解决**：在 `renderMarkdown()` 中增加表格检测逻辑：先将文本按行扫描，检测「含 `|` 的行 + 紧跟分隔线」模式，提取为表格块单独处理，转换为 HTML `<table>`。非表格文本走原有渲染流程。

## Claude CLI 参数

```bash
claude --allowedTools WebSearch,WebFetch --verbose --output-format stream-json -p "prompt"

# 续接会话
claude --resume {session_id} --allowedTools WebSearch,WebFetch --verbose --output-format stream-json -p "prompt"
```

| 参数 | 说明 |
|------|------|
| `--allowedTools WebSearch,WebFetch` | 授权联网搜索工具 |
| `--verbose` | stream-json 格式的前提条件 |
| `--output-format stream-json` | 逐事件 JSON 输出（而非纯文本） |
| `--resume {id}` | 续接已有 session（多轮对话） |
| `-p "prompt"` | 非交互模式，直接传入 prompt |

## stream-json 事件类型

| type | 说明 | 关键字段 |
|------|------|----------|
| `system` | 初始化 | `model`, `sessionId` |
| `assistant` | 内容块 | `message.content[].type` (thinking/text/tool_use) |
| `result` | 完成 | `result`, `session_id`, `duration_ms`, `cost_usd` |
