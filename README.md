# TeaMgr - 人才卡管理系统

团队整合人才管理工具。通过 LLM（Gemini）智能整理 1:1 交流记录，生成标准化人才卡，支持拼音搜索、标签分类、PDF简历导入/导出。

## 功能概览

- **人才卡管理** - 统一维度的人才画像，支持标签分类和搜索
- **信息录入** - 对话式录入 + PDF简历上传，LLM自动整理到人才卡
- **智能搜索** - 拼音模糊搜索 + AI语义搜索
- **PDF导出** - 一键导出人才卡为PDF
- **动态维度** - LLM可根据输入信息建议新增维度，所有人才卡维度自动对齐
- **安全认证** - 密码认证 + 渐进式封禁 + 自动解封 + IP限流
- **数据备份** - 每日自动备份到腾讯云COS
- **响应式设计** - 支持 iPhone / Android 和 PC 浏览器

## 前置依赖

- Docker
- docker-compose

所有运行环境（Python、Node.js、依赖库等）均封装在 Docker 容器内，宿主机无需安装任何开发环境。

## 快速开始

### 1. 配置

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

### 2. 构建并启动容器

```bash
# 构建镜像并启动容器（首次执行或代码/依赖变更后）
docker-compose -f docker/docker-compose.yml up -d --build
```

启动后会运行两个容器：

| 容器 | 作用 |
|------|------|
| `teamgr-app` | 后端运行环境，等待通过 exec 启动 uvicorn |
| `teamgr-nginx` | HTTPS 反向代理（端口 6443），首次启动自动生成自签名证书 |

### 3. 启动 Web 服务

```bash
# 在容器内启动 uvicorn（可反复调用，会自动杀掉旧进程再启动新的）
docker-compose -f docker/docker-compose.yml exec teamgr /workspace/scripts/start_web.sh

# 重启 Web 服务
docker-compose -f docker/docker-compose.yml exec teamgr /workspace/scripts/restart_web.sh
```

### 4. 日常运维

```bash
# 查看 uvicorn 日志
docker-compose -f docker/docker-compose.yml exec teamgr tail -f /var/log/uvicorn.log

# 查看容器日志
docker-compose -f docker/docker-compose.yml logs -f

# 停止所有容器
docker-compose -f docker/docker-compose.yml down

# 修改代码或依赖后重新构建（必须先 down 再 up，否则可能报 "No such image" 错误）
docker-compose -f docker/docker-compose.yml down
docker-compose -f docker/docker-compose.yml up -d --build
docker-compose -f docker/docker-compose.yml exec teamgr /workspace/scripts/start_web.sh
```

### 5. 访问

服务运行在 **6443 端口**（HTTPS，自签名证书）。

打开浏览器访问：`https://your-server-ip:6443`（浏览器会提示证书不受信任，确认继续即可）

## 配置说明

### config/config.yaml 完整配置

| 配置项 | 说明 | 必填 |
|--------|------|------|
| `auth.password` | 访问密码，留空则无密码模式 | 推荐 |
| `auth.jwt_secret` | JWT签名密钥 | 推荐 |
| `gemini.api_key` | Gemini API Key | 是 |
| `gemini.current_model` | 当前使用的模型 | 否 |
| `gemini.available_models` | 可选模型列表 | 否 |
| `cos.enabled` | 是否启用COS备份 | 否 |
| `cos.secret_id` | 腾讯云SecretId | 备份时必填 |
| `cos.secret_key` | 腾讯云SecretKey | 备份时必填 |
| `cos.region` | COS地域，如 ap-guangzhou | 备份时必填 |
| `cos.bucket` | COS桶名 | 备份时必填 |
| `backup.enabled` | 是否启用定时备份 | 否 |
| `backup.cron_hour` | 每天备份时间（小时） | 否 |

### 安全机制

| 措施 | 说明 |
|------|------|
| 强密码认证 | 从config.yaml读取密码 |
| 渐进式封禁 | 5次失败→封30分钟，10次→2小时，20次→24小时 |
| 自动解封 | 封禁到期自动恢复 |
| IP限流 | 每IP每分钟最多5次登录请求 |

## Gemini API Key 获取

1. 访问 [Google AI Studio](https://aistudio.google.com/)
2. 登录 Google 账号
3. 点击 "Get API Key" -> "Create API Key"
4. 复制 API Key 到 `config/config.yaml`

## 域名访问（Cloudflare）

如需通过域名访问，在 Cloudflare 做以下配置：

### 1. DNS 记录

添加 A 记录指向服务器公网 IP，开启代理（橙色云朵）：

| 类型 | 名称 | 内容 | 代理状态 |
|------|------|------|----------|
| A | `talent`（或你想要的子域名） | 服务器公网IP | 已代理 |

### 2. SSL 模式

在 **SSL/TLS** 页面，将加密模式设置为 **Full**。

> Full 模式下 Cloudflare 会通过 HTTPS 连接源站，但接受自签名证书。

### 3. Origin Rules（端口重写）

由于服务运行在 6443 端口而非默认的 443，需要配置 Origin Rules 让 Cloudflare 连接到正确端口：

1. 进入 **Rules** → **Origin Rules**
2. 点击 **Create rule**
3. 配置规则：
   - **When**：Hostname equals `talent.yourdomain.com`
   - **Then**：Destination Port → Rewrite to `6443`
4. 保存并部署

### 4. 防火墙

确保服务器安全组/防火墙开放 **6443** 端口。

## 项目结构

```
teamgr/
├── config/              # 配置文件
├── docker/              # Docker相关
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── nginx.conf
│   └── nginx-entrypoint.sh
├── scripts/             # 容器内执行的脚本
│   ├── start_web.sh     # 启动 uvicorn
│   └── restart_web.sh   # 重启 uvicorn
├── backend/             # Python FastAPI后端
│   └── app/
│       ├── main.py      # 入口
│       ├── models/      # 数据库模型
│       ├── routers/     # API路由
│       ├── services/    # 业务服务(LLM/PDF/拼音/备份)
│       └── middleware/  # 认证/限流中间件
├── frontend/            # Vue 3前端
│   └── src/
│       ├── views/       # 页面组件
│       ├── stores/      # Pinia状态管理
│       └── api/         # API封装
├── data/                # SQLite数据库(运行时生成)
└── ssl/                 # 自签名证书(自动生成)
```

## 腾讯云COS备份配置

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
