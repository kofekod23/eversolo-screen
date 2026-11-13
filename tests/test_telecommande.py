"""Appairage de la télécommande depuis /remote."""

import json

from conftest import connecter

ENTETE = {"X-Requested-With": "eversolo"}


def test_meme_touche_pressee_deux_fois_reste_distinguable(configure, local, distant):
    """La page compare l'instant de réception : une touche déjà pressée juste
    avant de lancer l'appairage doit être reconnue quand on la presse à nouveau."""
    connecter(distant)
    assert distant.get("/api/ir/last").get_json() == {"code": None, "at": 0}
    assert local.post("/internal/ir?code=5172", headers=ENTETE).status_code == 200
    premier = distant.get("/api/ir/last").get_json()
    configure.LAST_IR["time"] += 0.5
    second = distant.get("/api/ir/last").get_json()
    assert premier["code"] == second["code"] == "5172"
    assert premier["at"] != second["at"]


def test_dernier_code_reserve_a_la_session(configure, distant):
    assert distant.get("/api/ir/last").status_code == 401


def test_page_annonce_l_absence_de_signal(configure, distant):
    connecter(distant)
    html = distant.get("/remote").get_data(as_text=True)
    assert 'id="pairres"' in html and 'role="status"' in html
    assert json.dumps(configure.T["fr"]["pair_timeout"]) in html
