#!/usr/bin/env python3
"""Régénère requirements.lock : versions exactes et empreintes SHA-256 de tous
les fichiers publiés sur PyPI (roues de toutes les plateformes et sources),
pour que pip --require-hashes refuse tout paquet modifié.

Usage (poste de développement) : python3 tools/verrouiller.py nom==version ...
"""
import json
import sys
import urllib.request

ENTETE = ("# Généré par tools/verrouiller.py : ne pas modifier à la main.\n"
          "# Installé avec pip install --require-hashes -r requirements.lock\n")


def empreintes(nom, version):
    url = f"https://pypi.org/pypi/{nom}/{version}/json"
    with urllib.request.urlopen(url, timeout=20) as r:
        fichiers = json.load(r)["urls"]
    if not fichiers:
        raise SystemExit(f"{nom}=={version} introuvable sur PyPI")
    return sorted({f["digests"]["sha256"] for f in fichiers})


def main(paquets):
    lignes = [ENTETE]
    for spec in sorted(paquets, key=str.lower):
        nom, version = spec.split("==")
        hachages = " \\\n    ".join(f"--hash=sha256:{h}" for h in empreintes(nom, version))
        lignes.append(f"{nom}=={version} \\\n    {hachages}\n")
    sys.stdout.write("".join(lignes))


if __name__ == "__main__":
    main(sys.argv[1:])
