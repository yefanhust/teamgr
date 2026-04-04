# TeaMgr

个人工作台。人才卡管理 + Studio（任务管理 / Vibe Coding）+ 灵感碎片 + 龙图阁大学士（AI 问答）。

## 技术栈

- **后端**: Python 3.11 / FastAPI / SQLite（`backend/app/`）
- **前端**: Vue 3 / Vite / Pinia（`frontend/src/`）
- **部署**: Docker + docker-compose，Nginx HTTPS 反向代理（端口 6443）
- **LLM**: Gemini API（云端）/ SGLang + Gemma-4-26B-A4B（本地可选）
- **自动化**: AutoVibe（Vibe Coding）+ Scholar（龙图阁），均通过 Claude Code CLI 驱动

## 关键目录

```
backend/app/         后端代码（routers/ models/ services/ middleware/）
frontend/src/        前端代码（views/ stores/ api/）
docker/              Dockerfile + docker-compose.yml + nginx
scripts/             运维脚本（ops.sh 日常运维, start_web.sh / restart_web.sh 容器内）
autovibe/            AutoVibe + Scholar watcher 和 PTY 包装器（宿主机）
config/              配置文件（config.yaml 不入 Git）
data/                运行时数据（SQLite、队列、会话、日志）
doc/                 项目文档（DEPLOY.md 部署指南, SECURITY.md 安全方案）
proxy/               反向代理双机部署（Machine B 侧）
```

## 日常运维

```bash
bash scripts/ops.sh frontend   # 仅前端变更（构建 + 复制到容器）
bash scripts/ops.sh backend    # 仅后端变更（复制 + 重启 uvicorn）
bash scripts/ops.sh rebuild    # 单服务重建 teamgr（依赖没变）
bash scripts/ops.sh full       # 完整重建（Dockerfile / 依赖变更）
```

## 开发约定

- commit message 使用 `feat:` / `fix:` / `refactor:` 等前缀，中文描述
- 敏感配置在 `config/config.yaml`（已 gitignore），示例见 `config/config.example.yaml`
- 前端静态文件由后端 FastAPI 直接 serve（`frontend/dist/`）
- AutoVibe / Scholar watcher 运行在宿主机 tmux session 中，通过 `data/` 下的队列文件与容器通信
