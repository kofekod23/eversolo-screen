#!/usr/bin/env bash
# Publie une version signée, depuis le poste de développement.
#   tools/publier-version.sh v1.2.0 "Volume plus lisible" "Nouvelle interface Console"
# Chaque argument après la version devient une ligne des nouveautés, affichées
# dans /config. Les Pi n'installent qu'une version dont la signature SSH
# correspond à tools/signataires.
set -e
VERSION="$1"; shift || true
if ! [[ "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Usage : $0 vX.Y.Z \"nouveauté 1\" \"nouveauté 2\"..." >&2; exit 1
fi
CLE="${CLE_SIGNATURE:-$HOME/.ssh/id_ed25519.pub}"
[ -f "$CLE" ] || { echo "Clé introuvable : $CLE (variable CLE_SIGNATURE)" >&2; exit 1; }
[ -z "$(git status --porcelain)" ] || { echo "Le dépôt a des changements non commités." >&2; exit 1; }
[ "$(git rev-parse --abbrev-ref HEAD)" = "main" ] || { echo "Publiez depuis main." >&2; exit 1; }

MESSAGE="$VERSION"
if [ "$#" -gt 0 ]; then
    MESSAGE+=$'\n'
    for ligne in "$@"; do MESSAGE+=$'\n'"$ligne"; done
fi
git -c gpg.format=ssh -c user.signingkey="$CLE" tag -s "$VERSION" -m "$MESSAGE"
git -c gpg.format=ssh -c gpg.ssh.allowedSignersFile=tools/signataires verify-tag "$VERSION"
git push origin "$VERSION"
echo "Version $VERSION publiée et signée : les Pi la proposeront dans /config."
