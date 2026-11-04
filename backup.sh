#!/usr/bin/env bash
# Archives all container data (Zigbee2MQTT, Home Assistant, ...) into ./backups.
set -euo pipefail

cd "$(dirname "$0")"
mkdir -p backups
file="backups/pi4_docker_$(date +%Y-%m-%d_%H%M).tar.gz"

sudo tar -czf "$file" data .env
sudo chown "$USER": "$file"
echo "Backup written to $file"
