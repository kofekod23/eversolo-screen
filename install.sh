#!/usr/bin/env bash
# Installation sur Raspberry Pi OS (Lite ou Desktop).
# Usage :
#   ./install.sh            serveur seul (configuration via le navigateur)
#   ./install.sh --kiosk    serveur + plein ecran automatique sur le HDMI du Pi
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
CURRENT_USER="$(whoami)"
KIOSK=""
IR=""
for arg in "$@"; do
    case "$arg" in
        --kiosk) KIOSK="--kiosk" ;;
        --ir) IR="--ir" ;;
    esac
done

echo "== Installation eversolo-screen =="

sudo apt-get update
sudo apt-get install -y python3-venv curl
if [ "$KIOSK" = "--kiosk" ]; then
    sudo apt-get install -y cage
    sudo apt-get install -y chromium-browser || sudo apt-get install -y chromium
fi

if [ ! -d "$APP_DIR/venv" ]; then
    python3 -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

sudo cp "$APP_DIR/eversolo-screen.service" /etc/systemd/system/eversolo-screen@.service
sudo systemctl daemon-reload
sudo systemctl enable "eversolo-screen@$CURRENT_USER"
sudo systemctl restart "eversolo-screen@$CURRENT_USER"

if [ "$KIOSK" = "--kiosk" ]; then
    sudo cp "$APP_DIR/eversolo-kiosk.service" /etc/systemd/system/eversolo-kiosk@.service
    sudo systemctl daemon-reload
    sudo systemctl disable getty@tty1.service || true
    sudo systemctl set-default graphical.target || true
    sudo systemctl enable "eversolo-kiosk@$CURRENT_USER"
    sudo systemctl restart "eversolo-kiosk@$CURRENT_USER"
fi

# 6. Recepteur infrarouge (optionnel)
if [ "$IR" = "--ir" ]; then
    sudo apt-get install -y ir-keytable
    BOOTCFG="/boot/firmware/config.txt"
    [ -f "$BOOTCFG" ] || BOOTCFG="/boot/config.txt"
    if ! grep -q "^dtoverlay=gpio-ir" "$BOOTCFG"; then
        echo "dtoverlay=gpio-ir,gpio_pin=17" | sudo tee -a "$BOOTCFG" > /dev/null
        echo "Overlay infrarouge ajoute a $BOOTCFG (GPIO17): un redemarrage sera necessaire."
    fi
    sudo cp "$APP_DIR/eversolo-ir.service" /etc/systemd/system/eversolo-ir@.service
    sudo systemctl daemon-reload
    sudo systemctl enable "eversolo-ir@$CURRENT_USER"
    sudo systemctl restart "eversolo-ir@$CURRENT_USER" || true
fi

PI_IP="$(hostname -I | awk '{print $1}')"
echo ""
echo "== Termine =="
echo "Ouvrez http://$PI_IP:8080 : l'assistant de premiere configuration se lance"
echo "(mot de passe administrateur, detection automatique du DMP-A6, langue)."
echo "Logs : journalctl -u eversolo-screen@$CURRENT_USER -f"
