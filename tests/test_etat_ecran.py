"""/api/state porte ce que l'écran affiche de loin : état de lecture, signal,
volume réel, réglages d'affichage ; le muet suit l'Eversolo."""

import copy
import json
import os

from conftest import RACINE, connecter

with open(os.path.join(RACINE, "tests", "fixtures", "dmp-a6-tidal-arret.json"), encoding="utf-8") as f:
    REEL = json.load(f)


class Reponse:
    def __init__(self, donnees):
        self.donnees = donnees

    def json(self):
        return self.donnees

    def raise_for_status(self):
        pass


def brancher(srv, monkeypatch, etat, appels=None):
    def faux_get(url, *a, **k):
        if appels is not None:
            appels.append(url)
        if "getState" in url:
            return Reponse(etat)
        if "getInputAndOutputList" in url:
            return Reponse(REEL["getInputAndOutputList"])
        if "getPlayQueue" in url:
            return Reponse(REEL["getPlayQueue"])
        if "setMuteVolume" in url:
            return Reponse({})
        raise OSError("hors du test")
    monkeypatch.setattr(srv.http, "get", faux_get)
    monkeypatch.setattr(srv, "device_model", lambda *a, **k: "DMP-A6")
    # Les recherches d'artiste partent en fond : sans objet ici.
    monkeypatch.setattr(srv, "PREFETCH", {"artist": ("bloqué",)})


def etat(srv, client):
    return client.get("/api/state").get_json()


def test_etat_reel_a_l_arret(configure, local, monkeypatch):
    brancher(configure, monkeypatch, REEL["getState"])
    configure.PREFETCH["artist"] = ("Carla Bruni", "French Touch", "Stand By Your Man")
    e = etat(configure, local)
    assert e["etat"] == "arret" and e["playing"] is False
    assert e["live"] is False  # à l'arrêt la durée vaut 0 : ce n'est pas une radio
    assert e["signal"]["source"] == "Tidal" and e["signal"]["resolution"] == "24 bit / 48 kHz"
    assert e["volume"] == {"pct": 100, "texte": "0 dB", "muet": False}
    assert e["display"]["profil"] == "salon"


def test_radio_en_lecture_reste_en_direct(configure, local, monkeypatch):
    radio = copy.deepcopy(REEL["getState"])
    radio.update(state=3, duration=0, position=0)
    brancher(configure, monkeypatch, radio)
    e = etat(configure, local)
    assert e["etat"] == "lecture" and e["live"] is True


def test_pause_pendant_le_chargement_n_est_pas_en_direct(configure, local, monkeypatch):
    """Au démarrage d'un morceau, l'Eversolo annonce un instant une durée nulle."""
    morceau = copy.deepcopy(REEL["getState"])
    morceau.update(state=4, duration=0, position=0)
    brancher(configure, monkeypatch, morceau)
    e = etat(configure, local)
    assert e["etat"] == "pause" and e["live"] is False


def test_decouvertes_lues_dans_les_caches(configure, local, monkeypatch):
    brancher(configure, monkeypatch, REEL["getState"])
    configure.ALBUM_CACHE[("carla bruni", "french touch", "fr")] = (
        9e12, {"title": "French Touch", "facts": ["2017", "Barclay"], "tracks": [], "credits": []})
    e = etat(configure, local)
    assert {"k": "Album", "v": "2017, Barclay"} in e["decouvertes"]
    assert any(d["k"] == "Signal" for d in e["decouvertes"])


def test_sortie_active_relevee_en_fond(configure, monkeypatch):
    brancher(configure, monkeypatch, REEL["getState"])
    configure.rafraichir_entrees_sorties()
    assert configure.IO_CACHE["sortie"] == "Sortie OPT/COAX"


def test_plage_suivante_en_fin_de_morceau(configure, monkeypatch):
    brancher(configure, monkeypatch, REEL["getState"])
    configure.FILE_CACHE["etat"] = (("Captain Bacardi", 0), None)
    configure.chercher_suivant(("Captain Bacardi", 0), 0, "Captain Bacardi")
    assert configure.FILE_CACHE["etat"][1] == {"title": "The Long Way Home", "artist": "Norah Jones"}


def test_muet_suit_l_etat_reel(configure, local, monkeypatch):
    coupe = copy.deepcopy(REEL["getState"])
    coupe["volumeData"]["isMute"] = True
    appels = []
    brancher(configure, monkeypatch, coupe, appels)
    etat(configure, local)
    configure.MUTE_STATE["muted"] = False  # drapeau local désynchronisé
    assert configure.do_action("mute")
    assert any("setMuteVolume?isMute=0" in u for u in appels)


def test_reglages_d_affichage_enregistres(configure, distant):
    jeton = connecter(distant)
    page = distant.get("/config").get_data(as_text=True)
    assert 'name="ecran_profil"' in page
    distant.post("/config", data={
        "csrf": jeton, "op": "affichage", "ecran_theme": "affiche", "ecran_profil": "petit", "ecran_nuit": "toujours",
        "nuit_debut": "21", "nuit_fin": "8", "ecran_protection": "1"})
    assert configure.CONFIG["ecran_profil"] == "petit"
    assert configure.CONFIG["ecran_theme"] == "affiche"
    assert configure.CONFIG["ecran_nuit"] == "toujours"
    assert configure.CONFIG["nuit_debut"] == 21 and configure.CONFIG["ecran_protection"] is True
    assert configure.CONFIG["eversolo_ip"] == "192.168.1.42"  # le reste n'a pas bougé


def test_reglages_d_affichage_sans_jeton_refuses(configure, distant):
    connecter(distant)
    distant.post("/config", data={"op": "affichage", "ecran_profil": "petit"})
    assert configure.CONFIG.get("ecran_profil") != "petit"


def test_polices_locales_et_csp_sans_google(configure, local):
    rep = local.get("/")
    html = rep.get_data(as_text=True)
    csp = rep.headers["Content-Security-Policy"]
    assert "googleapis" not in html and "gstatic" not in html
    assert "/static/fonts/fonts.css" in html
    assert "google" not in csp and "font-src 'self'" in csp
    assert local.get("/static/fonts/fonts.css").status_code == 200


def test_les_trois_interfaces_sont_servies(configure, local):
    html = local.get("/").get_data(as_text=True)
    for chemin in ("/static/ecran.css", "/static/ecran.js", "/static/themes/pochette.css",
                   "/static/themes/console.css", "/static/themes/affiche.css"):
        assert chemin in html
        assert local.get(chemin).status_code == 200
    assert "<script>" not in html  # plus de script en ligne sur l'écran


def test_theme_inconnu_ramene_a_pochette(configure, local, monkeypatch):
    brancher(configure, monkeypatch, REEL["getState"])
    configure.CONFIG["ecran_theme"] = "../../etc"
    assert etat(configure, local)["display"]["theme"] == "pochette"


def test_ensuite_jamais_perime_pendant_la_recherche(configure, local, monkeypatch):
    fin = copy.deepcopy(REEL["getState"])
    fin.update(state=3, trackIndex=4, position=200000, duration=210000)
    brancher(configure, monkeypatch, fin)
    lances = []
    monkeypatch.setattr(configure, "_en_fond", lambda cible, *a: lances.append(cible))
    configure.FILE_CACHE["etat"] = (("Plage précédente", 3), {"title": "Stand By Your Man", "artist": "x"})
    e = etat(configure, local)
    assert e["ensuite"] is None  # l'ancien résultat ne s'affiche pas
    assert configure.chercher_suivant in lances


def test_recherche_tardive_n_ecrase_pas_la_plage_suivante(configure, monkeypatch):
    brancher(configure, monkeypatch, REEL["getState"])
    configure.FILE_CACHE["etat"] = (("Autre", 9), None)
    configure.chercher_suivant(("Captain Bacardi", 0), 0, "Captain Bacardi")
    assert configure.FILE_CACHE["etat"] == (("Autre", 9), None)


def test_muet_sans_etat_reel_utilise_le_drapeau_local(configure, monkeypatch):
    appels = []
    brancher(configure, monkeypatch, REEL["getState"], appels)
    configure.STATE_CACHE["info"] = {"volume": {"pct": 10, "texte": "10", "muet": None}}
    configure.MUTE_STATE["muted"] = False
    configure.do_action("mute")
    configure.do_action("mute")
    muets = [u for u in appels if "setMuteVolume" in u]
    assert muets[0].endswith("isMute=1") and muets[1].endswith("isMute=0")
