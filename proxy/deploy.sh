#!/bin/bash
# TeaMgr Proxy - One-click deploy script
# Reads config/proxy.yaml, generates nginx.conf from template, starts container

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_FILE="$PROJECT_ROOT/config/proxy.yaml"
TEMPLATE="$SCRIPT_DIR/nginx.conf.template"
OUTPUT="$SCRIPT_DIR/nginx.conf"

# --- Check config ---
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: $CONFIG_FILE not found."
    echo "Run:  cp config/proxy.example.yaml config/proxy.yaml"
    echo "Then edit config/proxy.yaml with your actual settings."
    exit 1
fi

# --- Parse YAML (simple key: value format) ---
parse_yaml_value() {
    grep "^${1}:" "$CONFIG_FILE" | sed 's/^[^:]*: *"\{0,1\}\([^"]*\)"\{0,1\}/\1/' | tr -d ' \r'
}

BACKEND_IP=$(parse_yaml_value "backend_ip")
BACKEND_PORT=$(parse_yaml_value "backend_port")
LISTEN_PORT=$(parse_yaml_value "listen_port")

BACKEND_IP="${BACKEND_IP:-10.2.0.16}"
BACKEND_PORT="${BACKEND_PORT:-6443}"
LISTEN_PORT="${LISTEN_PORT:-80}"

echo "=== TeaMgr Proxy Deploy ==="
echo "  Backend:  ${BACKEND_IP}:${BACKEND_PORT}"
echo "  Listen:   ${LISTEN_PORT}"
echo ""

# --- Generate nginx.conf from template ---
export BACKEND_IP BACKEND_PORT LISTEN_PORT
# Only substitute our variables, leave nginx variables ($host, $remote_addr, etc.) untouched
envsubst '${BACKEND_IP} ${BACKEND_PORT} ${LISTEN_PORT}' < "$TEMPLATE" > "$OUTPUT"
echo "  Generated nginx.conf"

# --- Ensure entrypoint is executable ---
chmod +x "$SCRIPT_DIR/entrypoint.sh"

# --- Create ssl dir ---
mkdir -p "$SCRIPT_DIR/ssl"

# --- Stop old container (avoid recreate issues with docker-compose v1) ---
docker-compose -f "$SCRIPT_DIR/docker-compose.yml" down 2>/dev/null || true

# --- Start container ---
export LISTEN_PORT
docker-compose -f "$SCRIPT_DIR/docker-compose.yml" up -d "$@"

echo ""
echo "=== Proxy is running ==="
echo "  Access: https://<this-machine-public-ip>:${LISTEN_PORT}"
echo "  Logs:   docker-compose -f proxy/docker-compose.yml logs -f"
echo "  Stop:   docker-compose -f proxy/docker-compose.yml down"
