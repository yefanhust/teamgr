#!/bin/bash
# TeaMgr 日常运维脚本
# 用法: bash ops.sh <command>
#   frontend  — 仅前端代码变更（热更新，不重启容器）
#   backend   — 仅后端 Python 代码变更（热更新，重启 uvicorn）
#   rebuild   — 单服务重建 teamgr（代码都改了但依赖没变）
#   full      — 完整重建所有容器（Dockerfile/依赖变更）

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DC="docker-compose -f $REPO_DIR/docker/docker-compose.yml"
CONTAINER="teamgr-app"

usage() {
    cat <<'EOF'
用法: bash ops.sh <command>

命令:
  frontend   仅前端代码变更（构建 + 复制到容器，刷新浏览器即可）
  backend    仅后端 Python 代码变更（复制 + 重启 uvicorn）
  rebuild    单服务重建 teamgr（前后端都改了但依赖没变）
  full       完整重建（Dockerfile / docker-compose.yml / 依赖变更）
EOF
    exit 1
}

do_frontend() {
    echo "[ops] 构建前端..."
    docker run --rm -v "$REPO_DIR/frontend:/build" -w /build node:20-alpine \
        sh -c "npm install && npm run build"
    echo "[ops] 复制到容器..."
    docker cp "$REPO_DIR/frontend/dist/." "$CONTAINER:/app/frontend/dist/"
    echo "[ops] 前端更新完成，刷新浏览器即可"
}

do_backend() {
    echo "[ops] 重启 uvicorn（backend/app 已 bind-mount，无需复制）..."
    docker exec "$CONTAINER" pkill -f uvicorn || true
    $DC exec -T teamgr /workspace/scripts/start_web.sh
    echo "[ops] 后端更新完成"
}

do_rebuild() {
    echo "[ops] 重建 teamgr 容器..."
    $DC rm -sf teamgr
    $DC up -d --build teamgr
    sleep 2
    $DC exec -T teamgr /workspace/scripts/start_web.sh
    echo "[ops] 单服务重建完成"
}

do_full() {
    echo "[ops] 完整重建所有容器..."
    $DC down --remove-orphans
    $DC up -d --build
    sleep 2
    $DC exec -T teamgr /workspace/scripts/start_web.sh
    echo "[ops] 完整重建完成"
}

[ $# -lt 1 ] && usage

case "$1" in
    frontend)  do_frontend ;;
    backend)   do_backend ;;
    rebuild)   do_rebuild ;;
    full)      do_full ;;
    *)         echo "未知命令: $1"; usage ;;
esac
