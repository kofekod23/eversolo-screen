#!/usr/bin/env bash
# Mise a jour depuis GitHub puis redemarrage du service.
set -e
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

# La configuration locale et les secrets ne sont pas suivis par git, mais on
# les protege quand meme avant toute operation.
cp -f config.json /tmp/eversolo-config.bak 2>/dev/null || true

git fetch origin
if ! git pull --ff-only 2>/dev/null; then
    echo "Mise a jour forcee (des fichiers locaux divergent)."
    git reset --hard origin/main
fi

if [ ! -f config.json ] && [ -f /tmp/eversolo-config.bak ]; then
    cp -f /tmp/eversolo-config.bak config.json
    echo "Configuration locale restauree."
fi
if [ ! -f config.json ] && [ -f config.example.json ]; then
    cp config.example.json config.json
fi

"$APP_DIR/venv/bin/pip" install --quiet -r requirements.txt
sudo systemctl restart "eversolo-screen@$(whoami)"
systemctl is-enabled "eversolo-ir@$(whoami)" >/dev/null 2>&1 && sudo systemctl restart "eversolo-ir@$(whoami)" || true
echo "Mise a jour terminee."
