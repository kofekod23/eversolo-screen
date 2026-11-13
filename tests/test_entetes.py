"""En-têtes de réponse et échappement des pages de réglage."""

import os

import pytest

from conftest import connecter


@pytest.mark.parametrize("chemin", ["/config", "/remote", "/blaster", "/login"])
def test_pages_de_reglage_jamais_gardees_en_cache(configure, distant, chemin):
    connecter(distant)
    rep = distant.get(chemin)
    assert rep.status_code == 200
    assert rep.headers.get("Cache-Control") == "no-store"


def test_ecran_et_fichiers_statiques_restent_en_cache(configure, local):
    assert "no-store" not in local.get("/").headers.get("Cache-Control", "")
    assert "no-store" not in local.get("/static/ecran.js").headers.get("Cache-Control", "")


def test_politique_de_contenu_fermee(configure, local):
    csp = local.get("/").headers["Content-Security-Policy"]
    for directive in ("base-uri 'none'", "form-action 'self'", "object-src 'none'",
                      "frame-ancestors 'none'"):
        assert directive in csp


def test_nom_de_commande_infrarouge_echappe(configure, distant):
    """Un fichier déposé à la main dans ir_codes ne peut pas injecter de balise."""
    os.makedirs(configure.IR_CODES_DIR, exist_ok=True)
    with open(os.path.join(configure.IR_CODES_DIR, "<b>tv.ir"), "w", encoding="utf-8") as f:
        f.write("0000")
    connecter(distant)
    html = distant.get("/blaster").get_data(as_text=True)
    assert "<b>tv" not in html
    assert "&lt;b&gt;tv" in html

