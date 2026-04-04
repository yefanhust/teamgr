# TeaMgr - 个人工作台

个人工作台工具。集人才卡管理、Studio（任务管理 + Vibe Coding）、灵感碎片于一体。通过 LLM（Gemini / 本地模型）提供智能辅助，通过 Claude Code 驱动自动化编码。

## 1. 功能概览

- **人才卡管理** - 统一维度的人才画像，支持标签分类和搜索
- **信息录入** - 对话式录入 + PDF简历上传，LLM自动整理到人才卡
- **智能搜索** - 拼音模糊搜索 + AI语义搜索
- **Studio** - 任务管理 + 标签分类 + 重复任务 + 截止日期 + 效率分析 + Vibe Coding
- **灵感碎片** - 随时记录想法，LLM定时聚合生成洞见
- **Vibe Coding** - 自动化研发管理（规划→实现→验证→提交），Claude Code 驱动
- **龙图阁大学士** - AI 问答助手，联网搜索 + PDF 分析 + 多轮对话，Claude Code 驱动
- **消息推送** - 企业微信 Webhook 推送每日总结、灵感洞见、截止提醒
- **安全认证** - 密码认证 + 渐进式封禁 + 自动解封 + IP限流
- **数据备份** - 每日自动备份到腾讯云COS
- **响应式设计** - 支持 iPhone / Android 和 PC 浏览器

## 2. 部署与运维

详见 [DEPLOY.md](DEPLOY.md)，包含：配置、构建启动、日常运维（`ops.sh`）、域名访问、本地 LLM 部署、反向代理双机部署、灾难恢复。

## 3. 配置说明

### 3.1 config/config.yaml 完整配置

| 配置项 | 说明 | 必填 |
|--------|------|------|
| `auth.password` | 访问密码，留空则无密码模式 | 推荐 |
| `auth.jwt_secret` | JWT签名密钥 | 推荐 |
| `gemini.api_key` | Gemini API Key | 是 |
| `gemini.current_model` | 当前使用的模型 | 否 |
| `gemini.available_models` | 可选模型列表 | 否 |
| `local_models` | 本地模型配置列表 | 否 |
| `local_models[].name` | 模型名称 | 是 |
| `local_models[].api_base` | OpenAI 兼容 API 地址 | 是 |
| `local_models[].api_key` | API Key（如需要） | 否 |
| `notification.enabled` | 是否启用消息推送 | 否 |
| `notification.channels.wecom_webhook.enabled` | 是否启用企业微信推送 | 否 |
| `notification.channels.wecom_webhook.webhook_url` | 企业微信机器人 Webhook URL | 推送时必填 |
| `notification.triggers.*` | 各推送时机开关 | 否 |
| `cos.enabled` | 是否启用COS备份 | 否 |
| `cos.secret_id` | 腾讯云SecretId | 备份时必填 |
| `cos.secret_key` | 腾讯云SecretKey | 备份时必填 |
| `cos.region` | COS地域，如 ap-guangzhou | 备份时必填 |
| `cos.bucket` | COS桶名 | 备份时必填 |
| `backup.enabled` | 是否启用定时备份 | 否 |
| `backup.cron_hour` | 每天备份时间（小时） | 否 |

### 3.2 安全机制

| 措施 | 说明 |
|------|------|
| 强密码认证 | 从config.yaml读取密码 |
| 渐进式封禁 | 5次失败→封30分钟，10次→2小时，20次→24小时 |
| 自动解封 | 封禁到期自动恢复 |
| IP限流 | 每IP每分钟最多5次登录请求 |

## 4. Gemini API Key 获取

1. 访问 [Google AI Studio](https://aistudio.google.com/)
2. 登录 Google 账号
3. 点击 "Get API Key" -> "Create API Key"
4. 复制 API Key 到 `config/config.yaml`

## 5. 项目结构

```
teamgr/
├── ops.sh               # 日常运维脚本（frontend/backend/rebuild/full）
├── config/              # 配置文件
├── docker/              # Docker相关
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── nginx.conf
│   └── nginx-entrypoint.sh
├── scripts/             # 脚本
│   ├── start_web.sh     # 启动 uvicorn（容器内）
│   └── restart_web.sh   # 重启 uvicorn（容器内）
├── autovibe/            # AutoVibe + Scholar 自动化
│   ├── autovibe.md      # AutoVibe 系统文档
│   ├── scholar.md       # 龙图阁大学士系统文档
│   ├── vibe-watcher.sh  # Vibe Watcher 守护进程（宿主机）
│   ├── scholar-watcher.sh  # Scholar Watcher 守护进程（宿主机）
│   ├── scholar-runner.py   # Claude CLI PTY 包装器（Scholar 专用）
│   ├── claude-pty.py    # Claude CLI PTY 包装器（AutoVibe）
│   └── claude-stream-parser.py  # 独立流式解析器（备用）
├── backend/             # Python FastAPI后端
│   └── app/
│       ├── main.py      # 入口
│       ├── models/      # 数据库模型 (talent, todo)
│       ├── routers/     # API路由 (talents, todos, ideas, auth)
│       ├── services/    # 业务服务(LLM/PDF/拼音/备份/推送)
│       └── middleware/  # 认证/限流中间件
├── frontend/            # Vue 3前端
│   └── src/
│       ├── views/       # 页面组件
│       ├── stores/      # Pinia状态管理
│       └── api/         # API封装
├── proxy/               # 反向代理部署（Machine B 公网代理机）
│   ├── nginx.conf.template  # Nginx 配置模板
│   ├── docker-compose.yml   # 代理容器编排
│   ├── deploy.sh            # 一键部署脚本
│   └── entrypoint.sh        # 证书生成 + 启动
├── data/                # 运行时数据（SQLite、队列文件、日志）
│   ├── teamgr.db        # SQLite数据库
│   ├── vibe-queue/      # Vibe Watcher 信号队列
│   ├── vibe-sessions/   # Claude Code 会话 ID 存储
│   ├── scholar-queue/   # Scholar 信号队列
│   ├── scholar-stream/  # Scholar 流式输出文件
│   ├── scholar-sessions/# Scholar Claude 会话 ID 存储
│   └── scholar-files/   # Scholar 上传文件存储
└── ssl/                 # 自签名证书(自动生成)
```

## 6. AutoVibe 自动化研发

系统内置 AutoVibe 工作流，通过 Claude Code CLI 驱动自动化编码。在 Studio 的「研发进度」中创建需求，完善后提交即可触发自动研发。详见 [autovibe/autovibe.md](autovibe/autovibe.md)。

### 6.1 工作流

```
需求 → 提交 → 规划中 ⇄ 三思而行 → 实现中 → 待验证 ⇄ 改进 → 提交中 → 已提交
```

| 阶段 | 说明 |
|------|------|
| 需求 | 创建需求，LLM 自动打标，可编辑标题/描述/标签，准备好后点击"提交" |
| 规划中 | Claude Code 分析复杂度，生成实现计划。人工审核后可"同意"或"三思而行" |
| 实现中 | Claude Code 按计划修改代码 |
| 待验证 | 人工验证实现结果。可"改进"退回附带反馈，或确认通过 |
| 提交中 | Claude Code 生成 commit message，自动 git add + commit + push |
| 已提交 | 任务完成，关联 git commit hash |

### 6.2 核心设计

- **Claude Code 驱动**：所有代码修改、计划生成、变更总结均由 Claude Code（宿主机）完成
- **Session 绑定**：一个任务绑定一个 Claude Code session，全生命周期 resume 同一 session
- **串行执行**：任何时刻最多一个活跃 session，Watcher 串行处理队列
- **信号文件**：容器通过共享 volume（`data/vibe-queue/`）写信号文件，宿主机 Watcher 通过 inotifywait 监听并处理

### 6.3 启动 Watcher

```bash
# 安装依赖（仅首次）
sudo apt-get install -y inotify-tools jq tmux

# 创建 tmux session 并启动 watcher
tmux new-session -s autovibe "bash autovibe/vibe-watcher.sh 2>&1 | tee -a data/vibe-watcher.log"

# 查看实时输出
tmux attach -t autovibe
```

## 7. 龙图阁大学士（AI 问答助手）

龙图阁大学士是一个 AI 驱动的智能问答助手，基于 Claude Code CLI（Max Plan）运行。支持联网搜索实时信息、PDF 文档上传分析、多轮对话，以及历史对话 LLM 自动分类。详见 [autovibe/scholar.md](autovibe/scholar.md)。

### 7.1 前置要求

- Claude Code CLI 已安装并登录（Max Plan）
- 宿主机安装 `inotify-tools`、`jq`
- Node.js 20+、Python 3.11+

### 7.2 启动 Scholar Watcher

```bash
# 安装依赖（仅首次，如果 AutoVibe 已安装则跳过）
sudo apt-get install -y inotify-tools jq tmux

# 创建 tmux session 并启动 watcher
tmux new-session -s scholar "bash autovibe/scholar-watcher.sh 2>&1 | tee -a data/scholar-watcher.log"

# 查看实时输出
tmux attach -t scholar
```

> Scholar Watcher 和 AutoVibe Watcher 是独立的守护进程，可以同时运行。

### 7.3 使用

1. 在前端进入「龙图阁」标签页，即可看到「龙图阁大学士」
2. 输入问题后点击发送，大学士会联网搜索并给出回答
3. 支持拖拽 PDF 文件到输入区域，上传后可对文档内容提问
4. 点击右上角时钟图标查看历史对话（LLM 自动按主题分类）
5. 点击 + 号新建对话

### 7.4 功能特性

| 功能 | 说明 |
|------|------|
| 联网搜索 | 自动调用 WebSearch / WebFetch 获取实时信息（股价、新闻等） |
| PDF 文档分析 | 拖拽或点击上传 PDF，提取文本后注入上下文 |
| 多轮对话 | 同一对话 resume 同一个 Claude session，保持上下文连贯 |
| 历史对话分类 | LLM 自动按主题分类历史对话，带缓存，秒开 |
| Markdown 渲染 | 支持表格、代码块、链接、列表等 Markdown 格式 |
| 流式输出 | 实时显示思考过程、搜索动态、回答文本 |

### 7.5 分类模型配置

历史对话分类所使用的 LLM 可在「设置」页面的 Studio 分组下配置「大学士-历史对话分类」模型。

## 8. 消息推送（企业微信）

系统支持通过企业微信群机器人 Webhook 推送消息通知，无需登录网站即可接收每日总结和提醒。

### 8.1 创建企业微信群机器人

1. 在企业微信中创建一个群聊（可以只有自己）
2. 群聊设置 → 群机器人 → 添加机器人
3. 复制机器人的 Webhook URL

### 8.2 配置

在 `config/config.yaml` 中添加：

```yaml
notification:
  enabled: true
  channels:
    wecom_webhook:
      enabled: true
      webhook_url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY"
  triggers:
    scheduled_query: true   # 每日定时查询完成后推送
    idea_insight: true      # 灵感洞见生成后推送
    todo_analysis: true     # 任务效率分析后推送
    todo_deadline: true     # 任务截止日期提醒
    todo_daily_list: true   # 每日任务清单
```

### 8.3 推送内容

| 推送项 | 触发时间 | 内容 |
|--------|----------|------|
| 每日定时查询 | 05:00 | 所有定时查询的问答结果 |
| 灵感洞见 | 03:00 | 当日生成的灵感洞见摘要 |
| 任务效率分析 | 03:30 | 近 7 天任务完成率与效率趋势 |
| 截止日期提醒 | 08:00 | 当天到期 + 已逾期的任务列表 |
| 每日任务清单 | 08:05 | 所有待办任务汇总（按优先级分组） |

### 8.4 说明

- 消息以 Markdown 格式推送，企业微信客户端原生渲染
- 推送失败不影响主业务（静默处理错误）
- 各推送项可通过 `triggers` 独立开关
- 频率限制：企业微信 Webhook 支持 20 条/分钟，各定时任务自然错开，不会触发限制

## 9. 备份

系统每日自动将所有关键数据打包加密后备份到腾讯云 COS。备份内容包括：数据库、配置文件、自定义提示词、龙图阁对话历史和上传文件。

### 9.1 配置

1. 登录 [腾讯云控制台](https://console.cloud.tencent.com/cos) 创建存储桶
2. 在 访问管理 -> API密钥管理 获取 SecretId 和 SecretKey
3. 配置 `config/config.yaml`:
   ```yaml
   cos:
     enabled: true
     secret_id: "your-secret-id"
     secret_key: "your-secret-key"
     region: "ap-guangzhou"
     bucket: "your-bucket-1234567890"
   backup:
     enabled: true
     cron_hour: 3
     cron_minute: 0
     encryption_password: "your-strong-backup-password"  # 务必牢记！
   ```

### 9.2 备份内容

| 数据 | 说明 |
|------|------|
| `data/teamgr.db` | SQLite 数据库（通过 backup API 安全导出） |
| `config/config.yaml` | 配置文件（含 API Key、密码等） |
| `config/instructions.yaml` | 自定义 LLM 提示词 |
| `data/scholar-conversations.json` | 龙图阁对话历史 |
| `data/scholar-sessions/` | 龙图阁会话 ID |
| `data/scholar-files/` | 龙图阁上传文件 |
| `data/vibe-sessions/` | Vibe 会话 ID |

### 9.3 安全机制

- **AES-256-GCM 加密**：备份包在上传前加密，COS 泄露也不会暴露数据
- **未设置加密密码时不上传**：防止明文备份泄露，系统会记录失败日志并推送企微告警
- **两把钥匙**：恢复需要 COS 凭证（访问备份）+ 加密密码（解密内容）

### 9.4 备份日志

点击页面顶部导航栏的盾牌图标可查看备份日志，包括：
- 备份健康状态（最后成功时间、包大小、加密状态）
- 历史备份记录（成功/失败、时间、大小、错误信息）
- 手动触发备份按钮

当备份失败或超过 36 小时未成功备份时，盾牌图标会显示红色角标。

### 9.5 灾难恢复

详见 [DEPLOY.md § 10](DEPLOY.md#10-灾难恢复)。
