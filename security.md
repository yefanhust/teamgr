# TeaMgr 安全方案

本文档记录项目的认证安全架构、设计决策、已知风险和未来升级路径。

---

## 1. 整体架构

```
用户浏览器 (iPhone / Mac / PC)
    │
    │  HTTPS (Cloudflare 签发的合法证书，浏览器信任)
    ▼
Cloudflare 代理 (DNS + CDN + SSL 终结)
    │
    │  HTTPS (服务器自签名证书，Cloudflare "Full" 模式接受)
    ▼
Nginx (端口 6443，TLS 终结)
    │
    │  HTTP (内部网络，容器间通信)
    ▼
FastAPI 后端 (端口 8000)
```

**关键点**：
- 用户到 Cloudflare 之间使用 Cloudflare 自动签发的合法证书，浏览器不会报警告
- Cloudflare 到源站之间使用自签名证书（`ssl/cert.pem`），由 Nginx entrypoint 脚本首次启动时自动生成
- Nginx 与后端之间是容器内网 HTTP 通信，不经过公网

## 2. 认证流程

### 2.1 登录

```
用户输入密码
    │
    ▼
POST /api/auth/login  { password, device_id }
    │
    ├─ 速率限制检查（每 IP 每分钟 5 次）
    ├─ 封禁检查（累计失败达阈值则封禁 IP）
    ├─ 密码验证
    │
    ▼  验证通过
签发 Access Token (JWT, 24h) → Set-Cookie: teamgr_access
    │
    ├─ 设备已信任 → 签发 Refresh Token (JWT, 30d) → Set-Cookie: teamgr_refresh
    ├─ 设备已拉黑 → 不签发 Refresh Token
    └─ 未知设备 → 前端弹窗询问是否信任
```

### 2.2 请求认证（require_auth 中间件）

每个受保护的 API 请求按以下顺序验证身份：

1. **Authorization Header** — `Bearer <access_token>`（标准路径，前端 localStorage 存储）
2. **Access Token Cookie** — `teamgr_access`（当 localStorage 被清理时的后备）
3. 都没有 → 返回 401，前端自动尝试 refresh

### 2.3 Token 续期

```
前端收到 401
    │
    ▼
POST /api/auth/refresh  (refresh_token 来自 body 或 HTTP-only cookie)
    │
    ├─ 验证 refresh token 签名和有效期
    ├─ 验证设备仍在信任列表中
    │
    ▼  验证通过
签发新 Access Token + 新 Refresh Token（轮换）
```

### 2.4 状态检查（页面加载时）

`GET /api/auth/status` 端点在页面加载时调用，按以下顺序判断认证状态：

1. 检查 Bearer token → 已认证
2. 检查 access cookie → 已认证
3. 检查 refresh cookie → 自动续期，返回新 token
4. 都没有 → 未认证，跳转登录页

## 3. Token 设计

### 3.1 Access Token

| 属性 | 值 |
|------|------|
| 格式 | JWT (HS256) |
| 有效期 | 24 小时 |
| Payload | `{exp, sub: "admin", type: "access"}` |
| 存储 | 前端 localStorage + HTTP-only Secure cookie (`teamgr_access`) |
| Cookie Path | `/api` |

### 3.2 Refresh Token

| 属性 | 值 |
|------|------|
| 格式 | JWT (HS256) |
| 有效期 | 30 天 |
| Payload | `{exp, sub: "admin", type: "refresh", device_id}` |
| 存储 | 前端 localStorage + HTTP-only Secure cookie (`teamgr_refresh`) |
| Cookie Path | `/api/auth`（更窄的路径，减少暴露面） |

### 3.3 JWT 密钥

- 从 `config.yaml` 的 `auth.jwt_secret` 读取
- 如未配置，回退到默认值 `"teamgr-default-secret"`（**生产环境必须配置**）

## 4. Cookie 安全属性

所有认证 cookie 均设置以下属性：

| 属性 | 值 | 作用 |
|------|------|------|
| `HttpOnly` | `true` | 阻止 JavaScript 读取 cookie，防御 XSS 窃取 token |
| `Secure` | `true` | 仅通过 HTTPS 传输，防止 HTTP 明文泄露 |
| `SameSite` | `lax` | 阻止大部分跨站请求携带 cookie，防御 CSRF |
| `Path` | `/api` 或 `/api/auth` | 限制 cookie 发送范围 |

## 5. 设备信任系统

### 5.1 设备状态

每个设备有三种状态：

- **trusted**（信任）— 获得 30 天 refresh token，免密续期
- **blacklisted**（拉黑）— 每次都需要输入密码，不再弹出信任询问
- **unknown**（未知）— 登录后弹窗询问用户选择

### 5.2 数据存储

设备信任数据存储在 `config/trusted_devices.json`：

```json
{
  "trusted": [
    {
      "device_id": "uuid",
      "device_name": "iPhone",
      "trusted_at": "2026-03-01T...",
      "last_used_at": "2026-03-20T..."
    }
  ],
  "blacklisted": [
    {
      "device_id": "uuid",
      "device_name": "Unknown Device",
      "blacklisted_at": "2026-03-01T..."
    }
  ]
}
```

### 5.3 设备识别

- `device_id`：前端通过 `crypto.randomUUID()` 生成，存储在 localStorage
- `device_name`：从 User-Agent 解析（iPhone / iPad / Mac / Android / Windows PC / Linux）
- **auto_adopt 机制**：当用户用密码登录且 device_id 未知，但 User-Agent 解析出的设备名与已信任设备匹配时，自动将信任转移到新 device_id（这发生在密码验证通过之后，不是安全绕过）

### 5.4 已移除的不安全机制

此前项目存在 **User-Agent 自动登录**机制：当 token 和 cookie 都不可用时，仅凭 User-Agent 字符串匹配受信设备即自动放行。此机制存在严重安全风险（User-Agent 可被伪造，且设备名粒度极粗），已被移除。

移除原因：项目使用 Cloudflare 代理，客户端拿到的是合法证书，Safari 的 cookie 持久化不受影响，因此 User-Agent 回退不再必要。

## 6. 暴力破解防护

### 6.1 速率限制

| 配置 | 值 |
|------|------|
| 限制对象 | 客户端 IP（通过 `X-Forwarded-For` 获取） |
| 频率限制 | 每 IP 每分钟最多 5 次请求 |
| 作用端点 | `POST /api/auth/login` |

### 6.2 累进封禁

| 失败次数 | 封禁时长 |
|----------|----------|
| 5 次 | 30 分钟 |
| 10 次 | 2 小时 |
| 20 次 | 24 小时 |

- 封禁自动过期后重置计数
- 登录成功立即重置该 IP 的失败计数
- 阈值可通过 `config.yaml` 的 `security.ban_thresholds` 自定义

## 7. CORS 策略

```python
CORSMiddleware(
    allow_origins=get_cors_origins(),   # 从 config.yaml 读取
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- 允许的来源从 `config.yaml` 的 `server.cors_origins` 读取
- 未配置时回退到 `["*"]`（兼容本地开发）
- 生产环境已配置为具体域名，阻止跨站请求携带凭据

## 8. TLS 配置

### 8.1 Nginx SSL

```
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers HIGH:!aNULL:!MD5;
```

- 仅支持 TLS 1.2 和 1.3，禁用旧版协议
- 排除 NULL 认证和 MD5 摘要的弱密码套件

### 8.2 自签名证书

- 由 `docker/nginx-entrypoint.sh` 首次启动时自动生成
- RSA 2048 位，有效期 10 年
- 存储在 `ssl/` 目录（已 gitignore）
- 此证书仅用于 Cloudflare → 源站之间的加密通信，用户浏览器不直接接触

## 9. 受保护与未保护端点

### 9.1 需要认证的端点

所有业务 API 均通过 `Depends(require_auth)` 保护：

- `/api/chat/*` — 人才查询对话
- `/api/stats/*` — 统计数据
- `/api/talents/*` — 人才卡管理
- `/api/scholar/*` — 龙图阁
- `/api/entry/*` — 信息录入
- `/api/projects/*` — 项目管理
- `/api/todos/*` — 任务管理
- `/api/settings/*` — 系统设置（模型切换、定时任务配置）

### 9.2 无需认证的端点

| 端点 | 原因 |
|------|------|
| `GET /api/auth/status` | 页面加载时检查是否需要登录 |
| `POST /api/auth/login` | 登录本身（有速率限制保护） |
| `POST /api/auth/refresh` | Token 续期（需要有效的 refresh token） |
| `POST /api/auth/logout` | 清除 cookie |
| `GET /{path}` | 前端静态文件 |

## 10. 敏感数据管理

### 10.1 配置文件

所有敏感配置存储在 `config/config.yaml`，此文件已加入 `.gitignore`，不会推送到 GitHub。

包含的敏感信息：
- 登录密码（`auth.password`）
- JWT 签名密钥（`auth.jwt_secret`）
- Gemini API Key（`gemini.api_key`）
- 腾讯云 COS 密钥（`cos.secret_id` / `cos.secret_key`）
- 备份加密密码（`backup.encryption_password`）
- CORS 允许来源域名（`server.cors_origins`）
- 企业微信 Webhook URL

### 10.2 设备信任数据

`config/trusted_devices.json` 存储设备信任列表，同样在 `.gitignore` 中。

### 10.3 公开的示例文件

`config/config.example.yaml` 包含配置结构和占位符，安全地提交到 Git。

## 11. 已知风险与接受理由

### 11.1 密码明文比对（低风险）

**现状**：登录时密码通过字符串直接比对，未使用 bcrypt/argon2 等哈希算法。

**风险**：如果 `config.yaml` 文件泄露，密码直接暴露。

**接受理由**：这是单用户/小团队内部工具，密码存储在服务器本地配置文件中（不是数据库），泄露风险等同于服务器被入侵（此时无论是否哈希都已失守）。

**升级路径**：如需升级，可改为 bcrypt 哈希比对。

### 11.2 JWT 默认密钥回退（已缓解）

**现状**：`config.py` 中 `get_jwt_secret()` 在未配置时回退到 `"teamgr-default-secret"`。

**风险**：如果忘记配置 jwt_secret，攻击者可用默认值伪造任意 token。

**已缓解**：生产环境的 `config.yaml` 已配置了 64 字符的随机密钥。

**升级路径**：可移除默认回退值，启动时如未配置则直接报错拒绝启动。

### 11.3 auto_adopt 设备名匹配粒度粗（低风险）

**现状**：设备名从 User-Agent 解析，粒度为设备类型级别（如所有 iPhone 都是 "iPhone"）。`auto_adopt_device` 在密码验证通过后，基于设备名匹配自动转移信任。

**风险**：如果你有两台 iPhone，一台登录后会"抢走"另一台的信任。

**接受理由**：这仅是 UX 问题，不是安全绕过（auto_adopt 发生在密码验证之后）。且当前使用场景为个人少量设备。

### 11.4 Cloudflare "Full" 模式非严格校验（极低风险）

**现状**：Cloudflare 设置为 "Full"（非 "Full Strict"）模式，接受源站自签名证书但不校验证书合法性。

**风险**：理论上如果有人能拦截 Cloudflare 到源站之间的网络流量（如 VPS 提供商或骨干网运营商），可以发起中间人攻击。

**接受理由**：实施此攻击需要控制网络基础设施层，成本远高于收益。对个人工具场景实际风险极低。

**升级路径**：使用 Cloudflare Origin Certificate（免费，15 年有效）+ "Full (Strict)" 模式。

### 11.5 无 CSRF Token（已缓解）

**现状**：没有独立的 CSRF token 机制。

**已缓解**：
- Cookie 设置了 `SameSite=Lax`，阻止大部分跨站 POST 请求携带 cookie
- CORS 已限定为具体域名，浏览器会阻止非授权来源的跨域请求
- JWT Bearer token 通过 Authorization header 传递（非 cookie 自动附带），天然抗 CSRF

### 11.6 内存级速率限制和封禁（已知局限）

**现状**：速率限制和 IP 封禁状态存储在应用进程内存中。

**局限**：应用重启后封禁状态丢失。

**接受理由**：单实例部署，重启频率低。攻击者在重启后仍需重新尝试，速率限制依然有效。

## 12. 未来升级路径

以下按推荐优先级排列，可根据需要逐步实施：

### P1 — 低成本高收益

| 改进 | 说明 | 工作量 |
|------|------|--------|
| 移除 JWT 默认回退 | `get_jwt_secret()` 未配置时直接抛异常，拒绝启动 | 5 分钟 |
| Cloudflare Origin Certificate | 替换自签名证书，启用 "Full (Strict)" 模式 | 30 分钟 |
| 认证事件日志 | 记录登录成功/失败、设备信任/拉黑事件到持久化日志 | 1 小时 |

### P2 — 中等投入

| 改进 | 说明 | 工作量 |
|------|------|--------|
| 密码 bcrypt 哈希 | 配置文件存储哈希值而非明文，登录时 bcrypt 比对 | 2 小时 |
| Refresh Token 轮换检测 | 检测同一 refresh token 被使用两次（可能被窃取），自动撤销该设备 | 3 小时 |
| 配置加密 | 使用 SOPS 或类似工具加密 config.yaml 的敏感字段 | 3 小时 |

### P3 — 架构级改进

| 改进 | 说明 | 工作量 |
|------|------|--------|
| 设备指纹增强 | 结合 canvas fingerprint、屏幕分辨率等因素提升设备识别精度 | 1 天 |
| WebAuthn / Passkey | 支持指纹/面容认证替代密码 | 2-3 天 |
| 多用户支持 | 从单密码模式升级为独立用户账户体系 | 视需求而定 |

---

*最后更新：2026-03-21*
