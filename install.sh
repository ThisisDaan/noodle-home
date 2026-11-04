#!/usr/bin/env bash
# Installs Docker on a fresh Raspberry Pi OS and starts the containers in compose.yaml.
# Run as your normal user (not root):  ./install.sh
set -euo pipefail

cd "$(dirname "$0")"

if [ "$(id -u)" -eq 0 ]; then
  echo "Run this as your normal user, not root. It uses sudo where needed." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "==> Installing Docker"
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo usermod -aG docker "$USER"

if [ ! -f .env ]; then
  cp .env.example .env
fi

# Timezone from the system
if tz="$(timedatectl show -p Timezone --value 2>/dev/null)" && [ -n "$tz" ]; then
  sed -i "s|^TZ=.*|TZ=${tz}|" .env
fi

# Zigbee stick, if exactly one is plugged in
sticks=(/dev/serial/by-id/*)
if [ -e "${sticks[0]}" ] && [ "${#sticks[@]}" -eq 1 ]; then
  sed -i "s|^ZIGBEE_DEVICE=.*|ZIGBEE_DEVICE=${sticks[0]}|" .env
  echo "==> Zigbee stick: ${sticks[0]}"
else
  echo "==> Could not pick a Zigbee stick automatically. Set ZIGBEE_DEVICE in .env (ls /dev/serial/by-id/)."
fi

for var in UNIFI_DB_ROOT_PASSWORD UNIFI_DB_PASSWORD; do
  if ! grep -qE "^${var}=.{16,}" .env; then
    sed -i "/^${var}=/d" .env
    echo "${var}=$(openssl rand -hex 16)" >> .env
  fi
done

mkdir -p data/mosquitto data/zigbee2mqtt data/homeassistant
if [ ! -f data/zigbee2mqtt/configuration.yaml ]; then
  cp zigbee2mqtt/configuration.example.yaml data/zigbee2mqtt/configuration.yaml
  echo "==> Created a fresh Zigbee2MQTT config. Restoring a backup? See README before continuing."
fi

echo "==> Starting containers"
sudo docker compose up -d

ip="$(hostname -I | awk '{print $1}')"
echo
echo "Done."
echo "  Home Assistant:  http://${ip}:8123"
echo "  Zigbee2MQTT:     http://${ip}:8081"
echo "Log out and back in once so 'docker' works without sudo."
