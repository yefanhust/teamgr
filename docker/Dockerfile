# Stage 1: Build frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend + serve frontend
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-noto-cjk fonts-wqy-zenhei procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./

# Copy built frontend
COPY --from=frontend-builder /build/dist /app/frontend/dist

# Create directories
RUN mkdir -p /app/data /var/log

# Environment
ENV TEAMGR_CONFIG=/app/config/config.yaml
ENV TEAMGR_DATA_DIR=/app/data
ENV PYTHONPATH=/app
ENV TZ=Asia/Shanghai

EXPOSE 8000

# Container stays alive; uvicorn is started via exec scripts/start_web.sh
CMD ["sleep", "infinity"]
