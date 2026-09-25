#!/usr/bin/env bash
# Mise à jour depuis GitHub puis redémarrage du service.
set -e
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

# La configuration locale et les secrets ne sont pas suivis par git, mais on
# les protege quand même avant toute opération.
# Copie privée (config.json contient les clés API), pas un chemin /tmp prévisible.
BACKUP="$(umask 077 && mktemp)"
trap 'rm -f "$BACKUP"' EXIT
cp -f config.json "$BACKUP" 2>/dev/null || true

git fetch origin
if ! git pull --ff-only 2>/dev/null; then
    echo "Mise à jour forcee (des fichiers locaux divergent)."
    git reset --hard origin/main
fi

if [ ! -f config.json ] && [ -s "$BACKUP" ]; then
    cp -f "$BACKUP" config.json
    chmod 600 config.json
    echo "Configuration locale restauree."
fi
if [ ! -f config.json ] && [ -f config.example.json ]; then
    cp config.example.json config.json
fi

"$APP_DIR/venv/bin/pip" install --quiet -r requirements.txt
sudo systemctl restart "eversolo-screen@$(whoami)"
systemctl is-enabled "eversolo-ir@$(whoami)" >/dev/null 2>&1 && sudo systemctl restart "eversolo-ir@$(whoami)" || true
echo "Mise à jour terminee."
