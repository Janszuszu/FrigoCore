#!/bin/sh
# Renders EMQX's file-based auth.conf from environment variables at container
# startup, so real MQTT credentials never live in git. Runs once via the
# emqx-config-init service before the emqx service starts (see docker-compose.yml).
set -eu

: "${MQTT_BACKEND_PASSWORD:?MQTT_BACKEND_PASSWORD is required}"
: "${MQTT_ESP_PASSWORD:?MQTT_ESP_PASSWORD is required}"

cat > /rendered/auth.conf <<EOF
frigocore-backend:${MQTT_BACKEND_PASSWORD}
frigocore-esp:${MQTT_ESP_PASSWORD}
firmware:${MQTT_ESP_PASSWORD}
EOF

echo "auth.conf rendered ($(wc -l < /rendered/auth.conf) lines)"
