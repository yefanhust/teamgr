# TeaMgr 部署指南

## 1. 前置依赖

- Docker
- docker-compose

所有运行环境（Python、Node.js、依赖库等）均封装在 Docker 容器内，宿主机无需安装任何开发环境。

## 2. 配置

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

完整配置项说明见 [README.md 配置说明](../README.md#3-配置说明)。

## 3. 构建并启动

```bash
# 构建镜像并启动容器
docker-compose -f docker/docker-compose.yml up -d --build
```

启动后会运行以下容器：

| 容器 | 作用 |
|------|------|
| `teamgr-app` | 后端运行环境，等待通过 exec 启动 uvicorn |
| `teamgr-sglang` | 本地 LLM 推理服务（Gemma-4-26B-A4B，需要 GPU） |
| `teamgr-nginx` | HTTPS 反向代理（端口 6443），首次启动自动生成自签名证书 |

> 如果没有 GPU，`sglang` 容器会启动失败但不影响其他服务，Gemini 云端模型仍可正常使用。

## 4. 启动 Web 服务

```bash
# 在容器内启动 uvicorn（可反复调用，会自动杀掉旧进程再启动新的）
docker-compose -f docker/docker-compose.yml exec teamgr /workspace/scripts/start_web.sh

# 重启 Web 服务
docker-compose -f docker/docker-compose.yml exec teamgr /workspace/scripts/restart_web.sh
```

## 5. 访问

服务运行在 **6443 端口**（HTTPS，自签名证书）。

打开浏览器访问：`https://your-server-ip:6443`（浏览器会提示证书不受信任，确认继续即可）

## 6. 日常运维

提供 `scripts/ops.sh` 脚本统一管理各场景的更新操作：

```bash
bash scripts/ops.sh <command>
```

| 命令 | 场景 | 说明 |
|------|------|------|
| `frontend` | 仅修改前端代码 | 构建 + 复制到容器，刷新浏览器即可 |
| `backend` | 仅修改后端 Python 代码 | 复制 + 重启 uvicorn，无需重建容器 |
| `rebuild` | 前后端代码都改了，但依赖没变 | 只重建 teamgr 容器，不影响 nginx / tacox |
| `full` | Dockerfile / docker-compose.yml / 依赖变更 | 先 down 再 up，完整重建所有容器 |

其他常用命令：

```bash
# 查看 uvicorn 日志
docker-compose -f docker/docker-compose.yml exec teamgr tail -f /var/log/uvicorn.log

# 查看容器日志
docker-compose -f docker/docker-compose.yml logs -f

# 停止所有容器
docker-compose -f docker/docker-compose.yml down
```

## 7. 域名访问（Cloudflare）

如需通过域名访问，在 Cloudflare 做以下配置：

### 7.1 DNS 记录

添加 A 记录指向服务器公网 IP，开启代理（橙色云朵）：

| 类型 | 名称 | 内容 | 代理状态 |
|------|------|------|----------|
| A | `talent`（或你想要的子域名） | 服务器公网IP | 已代理 |

### 7.2 SSL 模式

在 **SSL/TLS** 页面，将加密模式设置为 **Full**。

> Full 模式下 Cloudflare 会通过 HTTPS 连接源站，但接受自签名证书。

### 7.3 Origin Rules（端口重写）

由于服务运行在 6443 端口而非默认的 443，需要配置 Origin Rules 让 Cloudflare 连接到正确端口：

1. 进入 **Rules** → **Origin Rules**
2. 点击 **Create rule**
3. 配置规则：
   - **When**：Hostname equals `talent.yourdomain.com`
   - **Then**：Destination Port → Rewrite to `6443`
4. 保存并部署

### 7.4 防火墙

确保服务器安全组/防火墙开放 **6443** 端口。

## 8. 本地 LLM 部署（SGLang + Gemma-4-26B-A4B）

系统支持通过 SGLang 在本地部署 LLM，减少对 Gemini API 的依赖。当前预配置了 Google Gemma-4-26B-A4B-it 模型（MoE 架构，26B 总参数 / 4B 激活参数），使用 2 张 L20 GPU（TP2）进行推理。

### 8.1 前置要求

- 2 张 NVIDIA GPU（如 L20，每张 ≥ 24GB 显存）
- NVIDIA 驱动 + nvidia-container-toolkit
- 预下载的 Gemma-4-26B-A4B-it 模型权重

### 8.2 模型准备

模型需预先下载到 `~/.cache/huggingface/` 目录。可通过 `huggingface-cli` 下载：

```bash
pip install huggingface_hub
huggingface-cli download google/gemma-4-26B-A4B-it
```

> Gemma 模型需要先在 HuggingFace 上同意许可协议，并通过 `huggingface-cli login` 登录。

### 8.3 配置

在 `config/config.yaml` 中添加：

```yaml
local_models:
  - name: "Gemma-4-26B-A4B"
    api_base: "http://sglang:18080/v1"
    model_id: "Gemma-4-26B-A4B"
```

### 8.4 使用

`docker-compose up -d` 后，`sglang` 容器会自动启动推理服务（首次加载模型约需 2-3 分钟）。

在页面的模型选择器中，可以看到带"本地"标签的 Gemma-4-26B-A4B 选项。选择后所有文本生成类 LLM 调用（人才查询、信息录入、语义搜索）会路由到本地模型。PDF/图片解析等多模态功能仍使用 Gemini。

### 8.5 检查服务状态

```bash
# 查看 sglang 容器状态
docker ps | grep sglang

# 健康检查（sglang 端口未映射到宿主机，需通过容器 IP 访问）
curl -f http://$(docker inspect teamgr-sglang -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'):18080/health

# 测试推理
curl http://$(docker inspect teamgr-sglang -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'):18080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"Gemma-4-26B-A4B","messages":[{"role":"user","content":"你好"}],"max_tokens":32}'
```

> 也可以从 `teamgr-app` 容器内通过 Docker 服务名访问：`curl http://sglang:18080/health`

## 9. 反向代理部署（双机模式）

当 Machine A（运行 TeaMgr 的主机）因合规要求不能暴露公网时，可在同地域的 Machine B（有公网 IP）上部署反向代理，通过内网转发所有请求。

### 9.1 架构

```
用户 → HTTPS (443) → Machine B (Nginx 反向代理, 公网) → HTTPS 内网 → Machine A (6443, TeaMgr)
```

| 机器 | 角色 | 网络 |
|------|------|------|
| Machine A | TeaMgr 主服务 | 仅内网 |
| Machine B | 反向代理 | 公网 + 内网 |

### 9.2 前置要求

- Machine B 安装 Docker 和 docker-compose
- Machine B 与 Machine A 内网互通
- Machine A 的 TeaMgr 已正常运行

### 9.3 Machine B 部署

```bash
# 1. 克隆项目
git clone <repo-url> teamgr && cd teamgr

# 2. 创建代理配置
cp config/proxy.example.yaml config/proxy.yaml
vi config/proxy.yaml
```

**config/proxy.yaml 配置项：**

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `backend_ip` | Machine A 内网 IP | `10.2.0.16` |
| `backend_port` | Machine A Nginx 端口 | `6443` |
| `listen_port` | Machine B 对外监听端口 | `6443` |

```bash
# 3. 一键部署
bash proxy/deploy.sh
```

部署脚本会自动：读取配置 → 从模板生成 nginx.conf → 生成自签名证书（首次） → 启动容器。

### 9.4 日常运维

```bash
# 查看日志
docker-compose -f proxy/docker-compose.yml logs -f

# 停止代理
docker-compose -f proxy/docker-compose.yml down

# 修改配置后重新部署
vi config/proxy.yaml
bash proxy/deploy.sh

# 重建容器（Dockerfile 或 docker-compose.yml 变更后）
docker-compose -f proxy/docker-compose.yml down
bash proxy/deploy.sh --build
```

### 9.5 Machine A 侧配置

Machine A 的 Nginx 已预配置信任 RFC 1918 内网地址段的 `X-Forwarded-For` 头，无需额外修改。这确保 Machine A 的安全中间件（IP 限流、渐进式封禁）使用的是用户真实 IP 而非 Machine B 的内网 IP。

如果是全新部署，只需正常按第 3 节启动 TeaMgr 即可。如果是已有部署升级，重启 Nginx 容器使配置生效：

```bash
docker-compose -f docker/docker-compose.yml restart nginx
```

### 9.6 Cloudflare 域名配置（如使用）

将 Cloudflare 指向 Machine B：

1. **DNS A 记录**：IP 改为 Machine B 的公网 IP，保持代理开启（橙色云朵）
2. **Origin Rule**：端口重写为 `6443`（或你配置的 `listen_port`）
3. **SSL 模式**：保持 **Full** 不变

> HTTPS 协议与端口号无关，Nginx 可在任意端口提供 HTTPS 服务。Cloudflare Full 模式下，Origin Rule 指定端口 6443 后，Cloudflare 会以 HTTPS 协议连接 Machine B 的 6443 端口。

### 9.7 防火墙

确保：
- Machine B 安全组开放 `listen_port`（默认 6443）对公网
- Machine A 安全组开放 `6443` 对 Machine B 内网 IP
- Machine A 关闭 `6443` 对公网的访问（合规要求）

### 9.8 配置文件说明

| 文件 | 是否提交 Git | 是否参与备份 |
|------|-------------|-------------|
| `config/proxy.example.yaml` | 是 | - |
| `config/proxy.yaml` | 否（.gitignore） | 是（每日加密备份） |
| `proxy/nginx.conf.template` | 是 | - |
| `proxy/nginx.conf`（生成） | 否（.gitignore） | - |
| `proxy/ssl/`（证书） | 否（.gitignore） | - |

## 10. 灾难恢复

假设机器完全崩溃，需要在新机器上恢复：

```bash
# 1. 拉取代码
git clone <repo-url> teamgr && cd teamgr

# 2. 安装恢复脚本依赖
pip install cos-python-sdk-v5 cryptography

# 3. 从 COS 下载并恢复备份
python scripts/restore_from_cos.py \
  --secret-id YOUR_COS_SECRET_ID \
  --secret-key YOUR_COS_SECRET_KEY \
  --region ap-singapore \
  --bucket taco-sg-1251783334 \
  --password YOUR_BACKUP_PASSWORD

# 4. 构建并启动容器
docker-compose -f docker/docker-compose.yml up -d --build
docker-compose -f docker/docker-compose.yml exec teamgr /workspace/scripts/start_web.sh
```

恢复特定时间点版本：
```bash
python scripts/restore_from_cos.py ... --timestamp 20260315_043000
```

恢复旧格式（未加密 .db 文件）：
```bash
python scripts/restore_from_cos.py ... --legacy
```

> **重要**：请在安全的地方（如密码管理器）记录以下三个信息：COS SecretId、COS SecretKey、备份加密密码。加密密码遗忘后加密备份将无法恢复。
