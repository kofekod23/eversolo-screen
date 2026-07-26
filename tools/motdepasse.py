#!/usr/bin/env python3
"""Gestion du mot de passe administrateur d'eversolo-screen.

Usage :
    venv/bin/python tools/motdepasse.py nouveau MonMotDePasse
    venv/bin/python tools/motdepasse.py verifier MonMotDePasse
    venv/bin/python tools/motdepasse.py etat

A lancer depuis le dossier du projet, sur le Raspberry.
"""

import json
import os
import sys
import time

from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTH_PATH = os.path.join(BASE_DIR, "auth.json")
SECRET_PATH = os.path.join(BASE_DIR, ".secret_key")


def usage():
    print(__doc__)
    sys.exit(1)


def set_password(password):
    if len(password) < 8:
        print("Refusé : 8 caractères minimum.")
        sys.exit(1)
    fd = os.open(AUTH_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"password_hash": generate_password_hash(password, method="scrypt")}, f)
    print(f"Mot de passe enregistré dans {AUTH_PATH}")
    print("Relancez le serveur : sudo systemctl restart eversolo-screen@$(whoami)")


def verify(password):
    try:
        with open(AUTH_PATH, encoding="utf-8") as f:
            stored = json.load(f)["password_hash"]
    except (OSError, KeyError, ValueError):
        print("Aucun mot de passe enregistré : ouvrez /setup dans le navigateur.")
        sys.exit(1)
    ok = check_password_hash(stored, password)
    print("Ce mot de passe est CORRECT." if ok else "Ce mot de passe est INCORRECT.")
    if not ok:
        print("Pour en définir un nouveau : tools/motdepasse.py nouveau VotreMotDePasse")


def status():
    for path, label in ((AUTH_PATH, "auth.json"), (SECRET_PATH, ".secret_key")):
        if os.path.exists(path):
            st = os.stat(path)
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))
            print(f"{label:12} present  droits {oct(st.st_mode)[-3:]}  modifie {when}")
        else:
            print(f"{label:12} absent")
    try:
        with open(AUTH_PATH, encoding="utf-8") as f:
            algo = json.load(f)["password_hash"].split(":")[0]
        print(f"algorithme   {algo}")
    except Exception:
        pass


def main():
    if len(sys.argv) < 2:
        usage()
    cmd = sys.argv[1]
    if cmd == "etat":
        status()
    elif cmd in ("nouveau", "verifier"):
        if len(sys.argv) < 3:
            usage()
        (set_password if cmd == "nouveau" else verify)(sys.argv[2])
    else:
        usage()


if __name__ == "__main__":
    main()
