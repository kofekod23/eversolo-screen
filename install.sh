#!/usr/bin/env bash
# Installation sur Raspberry Pi OS (Lite ou Desktop).
# Usage : ./install.sh [IP_DU_DMP_A6]
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
CURRENT_USER="$(whoami)"

echo "== Installation eversolo-screen dans $APP_DIR =="

# 1. Dependances systeme
sudo apt-get update
sudo apt-get install -y python3-venv python3-dev libsdl2-2.0-0 libsdl2-image-2.0-0 libsdl2-ttf-2.0-0 fonts-dejavu

# 2. Environnement virtuel Python
if [ ! -d "$APP_DIR/venv" ]; then
    python3 -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

# 3. IP du streamer si passee en argument
if [ -n "$1" ]; then
    python3 - "$1" "$APP_DIR/config.json" << 'PYEOF'
import json, sys
path = sys.argv[2]
with open(path) as f:
    cfg = json.load(f)
cfg["eversolo_ip"] = sys.argv[1]
with open(path, "w") as f:
    json.dump(cfg, f, indent=2)
print(f"IP configuree : {sys.argv[1]}")
PYEOF
fi

# 4. Service systemd (demarrage automatique au boot)
sudo cp "$APP_DIR/eversolo-screen.service" "/etc/systemd/system/eversolo-screen@.service"
sudo systemctl daemon-reload
sudo systemctl enable "eversolo-screen@$CURRENT_USER"
sudo systemctl restart "eversolo-screen@$CURRENT_USER"

echo ""
echo "== Termine =="
echo "Statut  : sudo systemctl status eversolo-screen@$CURRENT_USER"
echo "Logs    : journalctl -u eversolo-screen@$CURRENT_USER -f"
echo "IP DMP  : editable dans $APP_DIR/config.json puis sudo systemctl restart eversolo-screen@$CURRENT_USER"
