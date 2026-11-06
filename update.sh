#!/usr/bin/env bash
# Mise à jour en ligne de commande (le bouton de /config fait la même chose).
# Installe la dernière version signée dans son propre dossier, puis redémarre ;
# si elle ne démarre pas, le garde revient tout seul à la précédente.
set -e
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

if [ ! -d "$HOME/eversolo-versions" ]; then
    # Installation d'avant les versions : on récupère le nouveau code puis on
    # relance install.sh, qui met en place les dossiers de versions.
    echo "Passage aux mises à jour par versions..."
    git fetch origin
    git pull --ff-only
    exec ./install.sh
fi

git fetch --quiet --tags origin
python3 "$APP_DIR/versions.py" installer
sudo systemctl restart "eversolo-screen@$(whoami)"
systemctl is-enabled "eversolo-ir@$(whoami)" >/dev/null 2>&1 && sudo systemctl restart "eversolo-ir@$(whoami)" || true
echo "Mise à jour terminée : $(python3 "$APP_DIR/versions.py" etat)"
