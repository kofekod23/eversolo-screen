"""Une mise à jour (git pull, reset --hard, versions par dossier) ne doit
jamais toucher aux réglages de l'utilisateur : clés d'API, mot de passe,
touches associées, codes infrarouges appris, captures."""

import os
import subprocess

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DONNEES = ["config.json", "auth.json", ".secret_key", "cache_fiches.json",
           "ir_codes/tv_power.ir", "captures/qobuz.json", "maj.json"]


def git(*args):
    return subprocess.run(["git", "-C", RACINE, *args], capture_output=True, text=True, check=False)


pytestmark = pytest.mark.skipif(git("rev-parse").returncode != 0, reason="hors dépôt git")


@pytest.mark.parametrize("chemin", DONNEES)
def test_donnee_personnelle_ignoree_par_git(chemin):
    assert git("check-ignore", "-q", "--no-index", chemin).returncode == 0, chemin


@pytest.mark.parametrize("chemin", DONNEES)
def test_donnee_personnelle_jamais_suivie(chemin):
    assert git("ls-files", "--error-unmatch", chemin).returncode != 0, chemin
