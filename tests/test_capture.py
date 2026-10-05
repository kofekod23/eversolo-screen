"""Capture de l'état de l'Eversolo : un bouton, des fichiers sans adresse de
flux signée ni identifiant, réservés à l'administrateur."""

import json
import os
import stat

from conftest import connecter


def test_masque_les_adresses_de_flux(srv):
    srv.CONFIG["eversolo_ip"] = "192.168.1.42"
    brut = {"playingMusic": {
        "streamUrl": "https://streaming-qobuz-std.akamaized.net/file?uid=1&hmac=SECRET",
        "trackUrl": "https://sp-pr-fa.audio.tidal.com/mediatracks/JETON/0.flac",
        "albumArt": "http://192.168.1.42:9529/ZidooMusicControl/v2/getImage?id=3",
        "title": "Titre",
    }, "liste": [{"uri": "https://x.example/a?token=SECRET"}]}
    propre = srv.masquer(brut)
    texte = json.dumps(propre)
    assert "SECRET" not in texte and "JETON" not in texte
    assert propre["playingMusic"]["streamUrl"].startswith("https://streaming-qobuz-std.akamaized.net/")
    assert propre["playingMusic"]["albumArt"] == brut["playingMusic"]["albumArt"]
    assert propre["playingMusic"]["title"] == "Titre"


def test_masque_les_champs_sensibles(srv):
    propre = srv.masquer({"userName": "julien", "token": "abc", "password": "x", "volume": 30})
    assert propre["userName"] != "julien" and propre["token"] != "abc" and propre["password"] != "x"
    assert propre["volume"] == 30


def test_capture_reservee_a_l_admin(configure, distant):
    r = distant.post("/config", data={"op": "capture", "situation": "qobuz"})
    assert r.status_code == 302
    assert not os.path.isdir(configure.CAPTURES_DIR) or not os.listdir(configure.CAPTURES_DIR)


def test_capture_enregistre_un_fichier_masque(configure, distant, monkeypatch):
    reponses = {
        "getState": {"state": 3, "playingMusic": {"streamUrl": "https://q.example/f?hmac=SECRET"},
                     "volumeData": {"currentVolume": 30, "maxVolume": 100, "isMute": False}},
        "getInputAndOutputList": {"inputData": [], "outputData": []},
        "getPlayQueue": {"array": []},
        "getModel": {"model": "DMP-A6"},
    }

    class R:
        def __init__(self, d):
            self._d = d
            self.ok = True

        def json(self):
            return self._d

    def faux_get(url, **k):
        for nom, d in reponses.items():
            if nom in url:
                return R(d)
        raise AssertionError(url)

    monkeypatch.setattr(configure.http, "get", faux_get)
    jeton = connecter(distant)
    r = distant.post("/config", data={"csrf": jeton, "op": "capture", "situation": "qobuz"})
    assert r.status_code == 200
    fichiers = os.listdir(configure.CAPTURES_DIR)
    assert len(fichiers) == 1 and fichiers[0].endswith("-qobuz.json")
    chemin = os.path.join(configure.CAPTURES_DIR, fichiers[0])
    assert stat.S_IMODE(os.stat(chemin).st_mode) == 0o600
    contenu = open(chemin, encoding="utf-8").read()
    assert "SECRET" not in contenu and '"currentVolume": 30' in contenu
    page = distant.get("/captures/" + fichiers[0])
    assert page.status_code == 200


def test_telechargement_reserve_et_nom_controle(configure, distant):
    assert distant.get("/captures/20261005-120000-qobuz.json").status_code in (302, 401)
    connecter(distant)
    assert distant.get("/captures/..%2Fauth.json").status_code == 404
    assert distant.get("/captures/inexistant.json").status_code == 404
