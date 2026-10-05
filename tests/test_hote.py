"""Liste blanche de l'en-tête Host : une page piégée qui rebondit par DNS vers
le Pi arrive avec son propre nom de domaine et doit être refusée."""

import pytest

from conftest import client as nouveau_client


@pytest.mark.parametrize("hote", [
    "192.168.1.10:8080", "192.168.1.10", "127.0.0.1:8080", "[::1]:8080",
    "localhost:8080", "localhost",
])
def test_adresses_ip_et_localhost_acceptees(srv, hote):
    client = nouveau_client(srv, "192.168.1.50", "192.168.1.10:8080")
    assert client.get("/api/state", headers={"Host": hote}).status_code == 200


def test_domaine_etranger_refuse(srv):
    client = nouveau_client(srv, "192.168.1.50", "192.168.1.10:8080")
    r = client.get("/api/state", headers={"Host": "piege.example.com"})
    assert r.status_code == 400


def test_nom_du_pi_et_variante_local_acceptes(srv, monkeypatch):
    monkeypatch.setattr(srv.socket, "gethostname", lambda: "eversolo")
    client = nouveau_client(srv, "192.168.1.50", "192.168.1.10:8080")
    for hote in ("eversolo:8080", "eversolo.local:8080", "EVERSOLO.LOCAL.", "eversolo.local"):
        assert client.get("/api/state", headers={"Host": hote}).status_code == 200, hote


def test_nom_ajoute_dans_la_configuration_accepte(srv):
    srv.CONFIG["hotes_autorises"] = ["eversolo.lan"]
    client = nouveau_client(srv, "192.168.1.50", "192.168.1.10:8080")
    assert client.get("/api/state", headers={"Host": "eversolo.lan:8080"}).status_code == 200
    assert client.get("/api/state", headers={"Host": "autre.lan"}).status_code == 400


def test_refus_explique_comment_s_en_sortir(srv):
    client = nouveau_client(srv, "192.168.1.50", "192.168.1.10:8080")
    r = client.get("/", headers={"Host": "piege.example.com"})
    assert "hotes_autorises" in r.get_data(as_text=True)


def test_nom_court_et_nom_complet_du_pi(srv, monkeypatch):
    monkeypatch.setattr(srv.socket, "gethostname", lambda: "eversolo.maison.lan")
    client = nouveau_client(srv, "192.168.1.50", "192.168.1.10:8080")
    for hote in ("eversolo.maison.lan", "eversolo", "eversolo.local", "monpi"):
        assert client.get("/api/state", headers={"Host": hote}).status_code == 200, hote


def test_nom_ajoute_avec_son_port(srv):
    srv.CONFIG["hotes_autorises"] = ["eversolo.lan:8080"]
    client = nouveau_client(srv, "192.168.1.50", "192.168.1.10:8080")
    assert client.get("/api/state", headers={"Host": "eversolo.lan:8080"}).status_code == 200
