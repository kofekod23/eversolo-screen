"""Les pages de réglage restent utilisables au clavier et au lecteur d'écran."""

import re

import pytest

from conftest import connecter

CHAMP = re.compile(r"<(input|select)\b([^>]*)>")
ATTRIBUT = re.compile(r'([\w-]+)="([^"]*)"')


def champs_sans_nom(html):
    """Champs visibles qu'aucun <label for>, aria-label ou label englobant ne nomme."""
    nommes = set(re.findall(r'<label[^>]*\bfor="([^"]+)"', html))
    enveloppes = "".join(re.findall(r"<label\b[^>]*>(.*?)</label>", html, re.S))
    orphelins = []
    for balise, brut in CHAMP.findall(html):
        attributs = dict(ATTRIBUT.findall(brut))
        if attributs.get("type") == "hidden":
            continue
        if attributs.get("id") in nommes or "aria-label" in attributs:
            continue
        if f'name="{attributs.get("name")}"' in enveloppes:
            continue
        orphelins.append(f"<{balise}{brut}>")
    return orphelins


@pytest.mark.parametrize("chemin", ["/config", "/remote", "/blaster"])
def test_chaque_champ_des_reglages_a_un_nom(configure, distant, chemin):
    connecter(distant)
    assert champs_sans_nom(distant.get(chemin).get_data(as_text=True)) == []


def test_chaque_champ_de_la_connexion_a_un_nom(configure, distant):
    assert champs_sans_nom(distant.get("/login").get_data(as_text=True)) == []


def test_chaque_champ_de_l_installation_a_un_nom(srv, distant):
    page = distant.get("/setup").get_data(as_text=True)
    assert champs_sans_nom(page) == []
    assert "alert(" not in page, "les erreurs s'affichent dans la page"


def test_erreur_annoncee_au_lecteur_d_ecran(configure, distant):
    page = distant.post("/login", data={"csrf": "x", "password": "faux"}).get_data(as_text=True)
    assert 'class="msg err" role="alert"' in page


def test_mot_de_passe_actuel_avant_le_nouveau(configure, distant):
    connecter(distant)
    page = distant.get("/config").get_data(as_text=True)
    assert page.index('name="current_password"') < page.index('name="new_password"')
