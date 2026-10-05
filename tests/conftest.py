"""Fixtures communes : chaque test charge un serveur neuf dont les fichiers
(config, mot de passe, caches, captures) vivent dans un dossier temporaire."""

import os
import re
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DISTANT = "192.168.1.50"
HOTE_PI = "192.168.1.10:8080"


@pytest.fixture
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("EVERSOLO_SCREEN_DATA", str(tmp_path))
    if RACINE not in sys.path:
        sys.path.insert(0, RACINE)
    sys.modules.pop("server", None)
    import server
    server.app.config["TESTING"] = True
    yield server
    sys.modules.pop("server", None)


def client(srv, adresse, hote):
    c = srv.app.test_client()
    c.environ_base.update({"REMOTE_ADDR": adresse, "HTTP_HOST": hote})
    return c


@pytest.fixture
def distant(srv):
    """Client vu depuis un téléphone du réseau local."""
    return client(srv, DISTANT, HOTE_PI)


@pytest.fixture
def local(srv):
    """Client vu depuis le kiosque du Pi lui-même."""
    return client(srv, "127.0.0.1", "localhost:8080")


@pytest.fixture
def configure(srv, monkeypatch):
    """Pi déjà configuré : mot de passe et adresse du streamer enregistrés."""
    monkeypatch.setattr(srv, "derniere_version", lambda: {"ts": 0.0, "sha": "", "message": ""})
    from werkzeug.security import generate_password_hash
    srv.save_auth(generate_password_hash("motdepasse-solide", method="scrypt"))
    srv.CONFIG.update({"eversolo_ip": "192.168.1.42"})
    srv.save_config(srv.CONFIG)
    return srv


def connecter(client, csrf="jeton-test"):
    with client.session_transaction() as s:
        s["auth"] = True
        s["csrf"] = csrf
    return csrf


def jeton_csrf(html):
    m = re.search(r'name="csrf" value="([0-9a-f]+)"', html)
    assert m, "jeton CSRF absent de la page"
    return m.group(1)
