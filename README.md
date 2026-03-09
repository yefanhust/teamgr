# TeaMgr - 个人工作台

个人工作台工具。集人才卡管理、Studio（任务管理 + Vibe Coding）、灵感碎片于一体。通过 LLM（Gemini / 本地模型）提供智能辅助，通过 Claude Code 驱动自动化编码。

## 1. 功能概览

- **人才卡管理** - 统一维度的人才画像，支持标签分类和搜索
- **信息录入** - 对话式录入 + PDF简历上传，LLM自动整理到人才卡
- **智能搜索** - 拼音模糊搜索 + AI语义搜索
- **Studio** - 任务管理 + 标签分类 + 重复任务 + 截止日期 + 效率分析 + Vibe Coding
- **灵感碎片** - 随时记录想法，LLM定时聚合生成洞见
- **Vibe Coding** - 自动化研发管理（规划→实现→验证→提交），Claude Code 驱动
- **消息推送** - 企业微信 Webhook 推送每日总结、灵感洞见、截止提醒
- **安全认证** - 密码认证 + 渐进式封禁 + 自动解封 + IP限流
- **数据备份** - 每日自动备份到腾讯云COS
- **响应式设计** - 支持 iPhone / Android 和 PC 浏览器

## 2. 前置依赖

- Docker
- docker-compose

所有运行环境（Python、Node.js、依赖库等）均封装在 Docker 容器内，宿主机无需安装任何开发环境。

## 3. 快速开始

### 3.1 配置

```bash
# 复制配置文件
cp config/config.example.yaml config/config.yaml

# 编辑配置
vi config/config.yaml
```

**必须配置的项：**

```yaml
auth:
  password: "your-strong-password"    # 设置访问密码
  jwt_secret: "random-secret-string"  # JWT密钥，随机字符串

gemini:
  api_key: "your-gemini-api-key"      # Gemini API Key
  current_model: "gemini-2.5-flash"   # 当前使用的模型
```

### 3.2 构建并启动容器

```bash
# 构建镜像并启动容器（首次执行或代码/依赖变更后）
docker-compose -f docker/docker-compose.yml up -d --build
```

启动后会运行以下容器：

| 容器 | 作用 |
|------|------|
| `teamgr-app` | 后端运行环境，等待通过 exec 启动 uvicorn |
| `teamgr-tacox` | 本地 LLM 推理服务（Qwen3-32B，需要 GPU） |
| `teamgr-nginx` | HTTPS 反向代理（端口 6443），首次启动自动生成自签名证书 |

> 如果没有 GPU，`tacox` 容器会启动失败但不影响其他服务，Gemini 云端模型仍可正常使用。

### 3.3 启动 Web 服务

```bash
# 在容器内启动 uvicorn（可反复调用，会自动杀掉旧进程再启动新的）
docker-compose -f docker/docker-compose.yml exec teamgr /workspace/scripts/start_web.sh

# 重启 Web 服务
docker-compose -f docker/docker-compose.yml exec teamgr /workspace/scripts/restart_web.sh
```

### 3.4 日常运维

```bash
# 查看 uvicorn 日志
docker-compose -f docker/docker-compose.yml exec teamgr tail -f /var/log/uvicorn.log

# 查看容器日志
docker-compose -f docker/docker-compose.yml logs -f

# 停止所有容器
docker-compose -f docker/docker-compose.yml down

# ---- 热更新（最轻量，不重启容器） ----

# 仅修改前端代码：构建 + 复制到容器，刷新浏览器即可
docker run --rm -v "$(pwd)/frontend:/build" -w /build node:20-alpine sh -c "npm install && npm run build" && docker cp frontend/dist/. teamgr-app:/app/frontend/dist/

# 仅修改后端 Python 代码：复制 + 重启 uvicorn
docker cp backend/. teamgr-app:/app/
docker exec teamgr-app pkill -f uvicorn
docker-compose -f docker/docker-compose.yml exec teamgr /workspace/scripts/start_web.sh

# ---- 单服务重建（前后端代码都改了，但依赖没变） ----
# 只重建 teamgr 容器，不影响 nginx / tacox
docker-compose -f docker/docker-compose.yml rm -sf teamgr && docker-compose -f docker/docker-compose.yml up -d --build teamgr && docker-compose -f docker/docker-compose.yml exec teamgr /workspace/scripts/start_web.sh

# ---- 完整重建（仅在以下情况需要） ----
# - 修改了 Dockerfile 或 docker-compose.yml
# - 修改了 requirements.txt 或 package.json（依赖变更）
# 必须先 down 再 up，否则可能报 "No such image" 错误
docker-compose -f docker/docker-compose.yml down
docker-compose -f docker/docker-compose.yml up -d --build
docker-compose -f docker/docker-compose.yml exec teamgr /workspace/scripts/start_web.sh
```

### 3.5 访问

服务运行在 **6443 端口**（HTTPS，自签名证书）。

打开浏览器访问：`https://your-server-ip:6443`（浏览器会提示证书不受信任，确认继续即可）

## 4. 配置说明

### 4.1 config/config.yaml 完整配置

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

### 4.2 安全机制

| 措施 | 说明 |
|------|------|
| 强密码认证 | 从config.yaml读取密码 |
| 渐进式封禁 | 5次失败→封30分钟，10次→2小时，20次→24小时 |
| 自动解封 | 封禁到期自动恢复 |
| IP限流 | 每IP每分钟最多5次登录请求 |

## 5. Gemini API Key 获取

1. 访问 [Google AI Studio](https://aistudio.google.com/)
2. 登录 Google 账号
3. 点击 "Get API Key" -> "Create API Key"
4. 复制 API Key 到 `config/config.yaml`

## 6. 域名访问（Cloudflare）

如需通过域名访问，在 Cloudflare 做以下配置：

### 6.1 DNS 记录

添加 A 记录指向服务器公网 IP，开启代理（橙色云朵）：

| 类型 | 名称 | 内容 | 代理状态 |
|------|------|------|----------|
| A | `talent`（或你想要的子域名） | 服务器公网IP | 已代理 |

### 6.2 SSL 模式

在 **SSL/TLS** 页面，将加密模式设置为 **Full**。

> Full 模式下 Cloudflare 会通过 HTTPS 连接源站，但接受自签名证书。

### 6.3 Origin Rules（端口重写）

由于服务运行在 6443 端口而非默认的 443，需要配置 Origin Rules 让 Cloudflare 连接到正确端口：

1. 进入 **Rules** → **Origin Rules**
2. 点击 **Create rule**
3. 配置规则：
   - **When**：Hostname equals `talent.yourdomain.com`
   - **Then**：Destination Port → Rewrite to `6443`
4. 保存并部署

### 6.4 防火墙

确保服务器安全组/防火墙开放 **6443** 端口。

## 7. 项目结构

```
teamgr/
├── config/              # 配置文件
├── docker/              # Docker相关
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── nginx.conf
│   └── nginx-entrypoint.sh
├── scripts/             # 脚本
│   ├── start_web.sh     # 启动 uvicorn（容器内）
│   └── restart_web.sh   # 重启 uvicorn（容器内）
├── autovibe/            # AutoVibe 自动化研发
│   ├── autovibe.md      # AutoVibe 系统文档
│   ├── vibe-watcher.sh  # Vibe Watcher 守护进程（宿主机）
│   ├── claude-pty.py    # Claude CLI PTY 包装器 + 流式解析
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
├── data/                # 运行时数据（SQLite、队列文件、日志）
│   ├── teamgr.db        # SQLite数据库
│   ├── vibe-queue/      # Vibe Watcher 信号队列
│   └── vibe-sessions/   # Claude Code 会话 ID 存储
└── ssl/                 # 自签名证书(自动生成)
```

## 8. 本地 LLM 部署（TACO-X + Qwen3-32B）

系统支持通过 TACO-X 在本地部署 LLM，减少对 Gemini API 的依赖。当前预配置了 Qwen3-32B 模型，使用 2 张 L20 GPU（TP2）进行推理。

### 8.1 前置要求

- 2 张 NVIDIA GPU（如 L20）
- NVIDIA 驱动 + nvidia-container-toolkit
- 预下载的 Qwen3-32B 模型权重

### 8.2 模型准备

模型需预先下载到 `~/.cache/huggingface/hub/models--Qwen--Qwen3-32B/` 目录。可通过 `huggingface-cli` 下载：

```bash
pip install huggingface_hub
huggingface-cli download Qwen/Qwen3-32B
```

### 8.3 配置

在 `config/config.yaml` 中添加：

```yaml
local_models:
  - name: "Qwen3-32B"
    api_base: "http://tacox:18080/v1"
```

### 8.4 使用

`docker-compose up -d` 后，`tacox` 容器会自动启动推理服务（首次加载模型约需 2 分钟）。

在页面的模型选择器中，可以看到带"本地"标签的 Qwen3-32B 选项。选择后所有文本生成类 LLM 调用（人才查询、信息录入、语义搜索）会路由到本地模型。PDF/图片解析等多模态功能仍使用 Gemini。

### 8.5 检查服务状态

```bash
# 查看 tacox 容器状态
docker ps | grep tacox

# 测试 API 是否就绪（发送一个最小请求）
docker exec teamgr-tacox python3 -c "
import urllib.request, json
req = urllib.request.Request(
    'http://localhost:18080/v1/chat/completions',
    data=json.dumps({'messages':[{'role':'user','content':'hi'}],'max_tokens':1}).encode(),
    headers={'Content-Type':'application/json'}
)
print(urllib.request.urlopen(req).read().decode())
"
```

## 9. AutoVibe 自动化研发

系统内置 AutoVibe 工作流，通过 Claude Code CLI 驱动自动化编码。在 Studio 的「研发进度」中创建需求，完善后提交即可触发自动研发。详见 [autovibe/autovibe.md](autovibe/autovibe.md)。

### 9.1 工作流

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

### 9.2 核心设计

- **Claude Code 驱动**：所有代码修改、计划生成、变更总结均由 Claude Code（宿主机）完成
- **Session 绑定**：一个任务绑定一个 Claude Code session，全生命周期 resume 同一 session
- **串行执行**：任何时刻最多一个活跃 session，Watcher 串行处理队列
- **信号文件**：容器通过共享 volume（`data/vibe-queue/`）写信号文件，宿主机 Watcher 通过 inotifywait 监听并处理

### 9.3 启动 Watcher

```bash
# 安装依赖（仅首次）
sudo apt-get install -y inotify-tools jq tmux

# 创建 tmux session 并启动 watcher
tmux new-session -s autovibe "bash autovibe/vibe-watcher.sh 2>&1 | tee -a data/vibe-watcher.log"

# 查看实时输出
tmux attach -t autovibe
```

## 10. 消息推送（企业微信）

系统支持通过企业微信群机器人 Webhook 推送消息通知，无需登录网站即可接收每日总结和提醒。

### 10.1 创建企业微信群机器人

1. 在企业微信中创建一个群聊（可以只有自己）
2. 群聊设置 → 群机器人 → 添加机器人
3. 复制机器人的 Webhook URL

### 10.2 配置

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

### 10.3 推送内容

| 推送项 | 触发时间 | 内容 |
|--------|----------|------|
| 每日定时查询 | 05:00 | 所有定时查询的问答结果 |
| 灵感洞见 | 03:00 | 当日生成的灵感洞见摘要 |
| 任务效率分析 | 03:30 | 近 7 天任务完成率与效率趋势 |
| 截止日期提醒 | 08:00 | 当天到期 + 已逾期的任务列表 |
| 每日任务清单 | 08:05 | 所有待办任务汇总（按优先级分组） |

### 10.4 说明

- 消息以 Markdown 格式推送，企业微信客户端原生渲染
- 推送失败不影响主业务（静默处理错误）
- 各推送项可通过 `triggers` 独立开关
- 频率限制：企业微信 Webhook 支持 20 条/分钟，各定时任务自然错开，不会触发限制

## 11. 备份

### 11.1 腾讯云COS备份

系统支持每日自动备份数据库到腾讯云 COS 对象存储。

1. 登录 [腾讯云控制台](https://console.cloud.tencent.com/cos)
2. 创建存储桶
3. 在 访问管理 -> API密钥管理 获取 SecretId 和 SecretKey
4. 配置 `config/config.yaml`:
   ```yaml
   cos:
     enabled: true
     secret_id: "your-secret-id"
     secret_key: "your-secret-key"
     region: "ap-guangzhou"
     bucket: "your-bucket-1234567890"
   backup:
     enabled: true
     cron_hour: 3   # 每天凌晨3点备份
   ```
