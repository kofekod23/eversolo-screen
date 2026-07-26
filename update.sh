#!/usr/bin/env bash
# Mise a jour depuis GitHub puis redemarrage du service.
set -e
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"
git pull
"$APP_DIR/venv/bin/pip" install -r requirements.txt
sudo systemctl restart "eversolo-screen@$(whoami)"
echo "Mise a jour terminee."
