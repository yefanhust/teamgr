#!/bin/sh
# Auto-generate self-signed certificate if not present

if [ ! -f /etc/nginx/ssl/cert.pem ] || [ ! -f /etc/nginx/ssl/key.pem ]; then
    echo "🔐 Generating self-signed SSL certificate..."
    apk add --no-cache openssl > /dev/null 2>&1
    mkdir -p /etc/nginx/ssl
    openssl req -x509 -nodes -days 3650 \
        -newkey rsa:2048 \
        -keyout /etc/nginx/ssl/key.pem \
        -out /etc/nginx/ssl/cert.pem \
        -subj "/CN=teamgr/O=TeaMgr" \
        2>/dev/null
    echo "   Certificate generated"
fi

exec nginx -g 'daemon off;'
