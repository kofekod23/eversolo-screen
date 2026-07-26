#!/usr/bin/env bash
# Installation sur Raspberry Pi OS (Lite ou Desktop).
# Usage :
#   ./install.sh 192.168.1.XX            serveur seul (affichage via navigateur)
#   ./install.sh 192.168.1.XX --kiosk    serveur + plein ecran automatique sur le HDMI du Pi
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
CURRENT_USER="$(whoami)"
IP="$1"
KIOSK="$2"

echo "== Installation eversolo-screen =="

# 1. Dependances systeme
sudo apt-get update
sudo apt-get install -y python3-venv curl
if [ "$KIOSK" = "--kiosk" ]; then
    sudo apt-get install -y cage chromium-browser
fi

# 2. Environnement virtuel Python
if [ ! -d "$APP_DIR/venv" ]; then
    python3 -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

# 3. IP du streamer
if [ -n "$IP" ]; then
    python3 - "$IP" "$APP_DIR/config.json" << 'PYEOF'
import json, sys
path = sys.argv[2]
with open(path) as f:
    cfg = json.load(f)
cfg["eversolo_ip"] = sys.argv[1]
with open(path, "w") as f:
    json.dump(cfg, f, indent=2)
print(f"IP du DMP-A6 : {sys.argv[1]}")
PYEOF
fi

# 4. Service serveur
sudo cp "$APP_DIR/eversolo-screen.service" /etc/systemd/system/eversolo-screen@.service
sudo systemctl daemon-reload
sudo systemctl enable "eversolo-screen@$CURRENT_USER"
sudo systemctl restart "eversolo-screen@$CURRENT_USER"

# 5. Kiosque plein ecran (optionnel)
if [ "$KIOSK" = "--kiosk" ]; then
    sudo cp "$APP_DIR/eversolo-kiosk.service" /etc/systemd/system/eversolo-kiosk@.service
    sudo systemctl daemon-reload
    sudo systemctl enable "eversolo-kiosk@$CURRENT_USER"
    sudo systemctl restart "eversolo-kiosk@$CURRENT_USER"
fi

PI_IP="$(hostname -I | awk '{print $1}')"
echo ""
echo "== Termine =="
echo "Interface : http://$PI_IP:8080 (depuis un telephone ou un PC du reseau)"
if [ "$KIOSK" = "--kiosk" ]; then
    echo "Kiosque   : l'ecran HDMI du Pi affiche l'interface automatiquement au boot"
fi
echo "Logs      : journalctl -u eversolo-screen@$CURRENT_USER -f"
