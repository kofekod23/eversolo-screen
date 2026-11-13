"""Pannes rares qui ne doivent ni vider l'écran ni passer sous silence :
réponse incomplète du streamer, volet fermé pendant un relevé, caches
partagés entre fils, modèle introuvable, écritures inutiles sur la carte."""

import copy
import json
import os
import threading

from conftest import RACINE

with open(os.path.join(RACINE, "tests", "fixtures", "dmp-a6-tidal-arret.json"), encoding="utf-8") as f:
    REEL = json.load(f)


class Reponse:
    def __init__(self, donnees, ok=True):
        self.donnees = donnees
        self.ok = ok

    def json(self):
        return self.donnees

    def raise_for_status(self):
        pass


def brancher(srv, monkeypatch, etat):
    def faux_get(url, *a, **k):
        if "getState" in url:
            return Reponse(etat)
        if "getInputAndOutputList" in url:
            return Reponse(REEL["getInputAndOutputList"])
        if "getPlayQueue" in url:
            return Reponse(REEL["getPlayQueue"])
        raise OSError("hors du test")
    monkeypatch.setattr(srv.http, "get", faux_get)
    monkeypatch.setattr(srv, "device_model", lambda *a, **k: "DMP-A6")
    monkeypatch.setattr(srv, "PREFETCH", {"artist": ("bloqué",)})


# ------------------------------------------------- réponses incomplètes

def test_bloc_de_lecture_nul_ne_casse_pas_la_lecture(configure, monkeypatch):
    monkeypatch.setattr(configure, "device_model", lambda *a, **k: "DMP-A6")
    brut = copy.deepcopy(REEL["getState"])
    brut["everSoloPlayInfo"] = None
    info = configure.normalize(brut)
    assert info["connected"] is True
    assert info["title"] == REEL["getState"]["playingMusic"]["title"]


def test_reponse_inexploitable_est_journalisee_sans_accuser_le_reseau(configure, local, monkeypatch, capsys):
    brancher(configure, monkeypatch, REEL["getState"])

    def casse(*a, **k):
        raise ValueError("champ inattendu")
    monkeypatch.setattr(configure, "infos_ecran", casse)
    for _ in range(4):
        e = local.get("/api/state").get_json()
    assert e["connected"] is False
    sortie = capsys.readouterr().out
    assert sortie.count("inexploitable") == 1, "une ligne par minute au plus"
    assert "ValueError" in sortie
    assert "injoignable" not in sortie


def test_streamer_muet_reste_signale_injoignable(configure, local, monkeypatch, capsys):
    def panne(url, *a, **k):
        raise OSError("réseau coupé")
    monkeypatch.setattr(configure.http, "get", panne)
    for _ in range(3):
        local.get("/api/state")
    assert "injoignable" in capsys.readouterr().out


# ------------------------------------------------------------ volet

def test_volet_ferme_pendant_le_releve(configure, local, monkeypatch):
    brancher(configure, monkeypatch, REEL["getState"])
    # état transitoire d'une fermeture : l'échéance n'est pas encore remise à zéro
    configure.ARTIST_PANEL.update({"until": configure.time.time() + 30, "data": None})
    e = local.get("/api/state").get_json()
    assert e["connected"] is True and "panel" not in e
    assert configure.STATE_CACHE["failures"] == 0


def ouvrir_volet_a_froid(srv, monkeypatch, bio_attend=None, credits_attendent=None):
    """Ouvre le volet sans rien en cache et rend la liste des appels aux
    crédits de plage, avec l'état du verrou du volet à chaque appel."""
    etat = {"artist": "Nina Simone", "album": "Pastel Blues", "title": "Sinnerman"}
    sous_verrou = []
    monkeypatch.setattr(srv.http, "get", lambda *a, **k: Reponse({}))
    monkeypatch.setattr(srv, "normalize", lambda brut: dict(etat))

    def bio(*a, **k):
        if bio_attend:
            bio_attend.wait(2)
        return {"artist": "Nina Simone", "text": "Biographie", "image": None,
                "facts": [], "source": "essai"}

    def credits(*a, **k):
        sous_verrou.append(srv.VERROU_VOLET.locked())
        if credits_attendent:
            credits_attendent.wait(2)
        return [{"role": "Producteur", "name": "Hal Mooney"}]

    monkeypatch.setattr(srv, "fetch_artist_info", bio)
    monkeypatch.setattr(srv, "fetch_album_info", lambda *a, **k: {
        "title": "Pastel Blues", "facts": [], "text": "Disque", "tracks": [],
        "credits": [], "prod_facts": [], "source": "essai"})
    monkeypatch.setattr(srv, "fetch_track_credits", credits)
    avant = set(threading.enumerate())
    assert srv.toggle_artist_panel() is True
    return sous_verrou, [t for t in threading.enumerate() if t not in avant]


def test_publications_du_volet_ne_s_ecrasent_pas(configure, monkeypatch):
    """La fiche d'artiste et les crédits arrivent dans le désordre : rien ne se perd,
    et aucune recherche ne se fait pendant qu'on retouche le volet."""
    srv = configure
    credits_publies = threading.Event()
    publie = srv.publier_volet

    def publier_et_signaler(jeton, mutateur, *a, **k):
        fait = publie(jeton, mutateur, *a, **k)
        if ((srv.ARTIST_PANEL["data"] or {}).get("album") or {}).get("credits"):
            credits_publies.set()
        return fait
    monkeypatch.setattr(srv, "publier_volet", publier_et_signaler)

    # la biographie n'arrive qu'après les crédits
    sous_verrou, fils = ouvrir_volet_a_froid(srv, monkeypatch, bio_attend=credits_publies)
    for fil in fils:
        fil.join(3)
    donnees = srv.ARTIST_PANEL["data"]
    assert donnees["artist"]["text"] == "Biographie"
    assert donnees["album"]["credits"], "les crédits de la plage sont fusionnés"
    assert sous_verrou and not any(sous_verrou), "aucun appel réseau sous le verrou du volet"


def test_recherche_tardive_ne_rouvre_pas_un_volet_ferme(configure, monkeypatch):
    srv = configure
    liberer = threading.Event()
    _, fils = ouvrir_volet_a_froid(srv, monkeypatch, bio_attend=liberer,
                                   credits_attendent=liberer)
    assert srv.toggle_artist_panel() is True  # deuxième appui : fermeture
    liberer.set()
    for fil in fils:
        fil.join(3)
    assert srv.ARTIST_PANEL["data"] is None
    assert srv.ARTIST_PANEL["until"] == 0.0


# ----------------------------------------------------------- caches

def test_elagage_tolere_une_cle_retiree_par_un_autre_fil(srv):
    class CachePartage(dict):
        """Une clé disparaît entre l'énumération et la lecture."""
        def __getitem__(self, cle):
            if cle == "volée":
                raise KeyError(cle)
            return dict.__getitem__(self, cle)

    cache = CachePartage({f"c{i}": (i, "x") for i in range(10)})
    dict.__setitem__(cache, "volée", (0.5, "x"))
    srv._elaguer(cache, maxi=4)
    assert len(cache) <= 6
    assert "c9" in cache, "les plus récentes restent"


def test_modele_introuvable_n_est_pas_redemande_a_chaque_releve(configure, monkeypatch):
    appels = []

    def faux_get(url, *a, **k):
        appels.append(url)
        return Reponse({}, ok=False)
    monkeypatch.setattr(configure.http, "get", faux_get)
    assert configure.device_model() == ""
    assert configure.device_model() == ""
    assert len(appels) == 1
    # passé le délai, on redemande
    configure.MODEL_CACHE["quand"] -= configure.MODELE_NOUVEL_ESSAI + 1
    configure.device_model()
    assert len(appels) == 2


def test_modele_trouve_est_garde(configure, monkeypatch):
    appels = []

    def faux_get(url, *a, **k):
        appels.append(url)
        return Reponse({"model": "DMP-A8"})
    monkeypatch.setattr(configure.http, "get", faux_get)
    assert configure.device_model() == "DMP-A8"
    assert configure.device_model() == "DMP-A8"
    assert len(appels) == 1
    assert configure.device_model(ip="192.168.1.99") == "DMP-A8"
    assert len(appels) == 2, "autre adresse : autre appareil"


def test_fiches_inchangees_ne_sont_pas_reecrites(srv):
    srv.ARTIST_CACHE[("nina simone", "", "fr")] = (1000.0, {"artist": "Nina Simone"})
    srv.sauver_fiches()
    premiere = os.stat(srv.FICHIER_FICHES).st_mtime_ns
    os.utime(srv.FICHIER_FICHES, ns=(1, 1))
    srv.sauver_fiches()
    assert os.stat(srv.FICHIER_FICHES).st_mtime_ns == 1, "rien n'a changé : pas d'écriture"
    srv.ARTIST_CACHE[("bill evans", "", "fr")] = (1001.0, {"artist": "Bill Evans"})
    srv.sauver_fiches()
    assert os.stat(srv.FICHIER_FICHES).st_mtime_ns not in (1, premiere - 1)
    with open(srv.FICHIER_FICHES, encoding="utf-8") as f:
        assert len(json.load(f)["artistes"]) == 2


def test_echec_d_ecriture_des_fiches_est_journalise(srv, monkeypatch, capsys):
    srv.ARTIST_CACHE[("nina simone", "", "fr")] = (1000.0, {"artist": "Nina Simone"})
    monkeypatch.setattr(srv, "FICHIER_FICHES", os.path.join(str(srv.DATA_DIR), "absent", "fiches.json"))
    srv.sauver_fiches()
    assert "fiches" in capsys.readouterr().out


# ------------------------------------------------------ écran de repos

def test_streamer_absent_garde_l_interface_choisie(configure, local, monkeypatch):
    """Sans streamer dès l'allumage, l'écran de repos doit quand même connaître
    l'interface et le mode nuit réglés, sinon il retombe sur ceux par défaut."""
    configure.CONFIG["ecran_theme"] = "cadre"

    def panne(url, *a, **k):
        raise OSError("réseau coupé")
    monkeypatch.setattr(configure.http, "get", panne)
    e = local.get("/api/state").get_json()
    assert e["connected"] is False
    assert e["display"]["theme"] == "cadre"
    assert e["rev"] == configure.LOCAL_REV


# ------------------------------------------- volet pendant un relevé manqué

def test_volet_ouvert_survit_a_un_releve_manque(configure, local, monkeypatch):
    """Un raté isolé du streamer ne doit pas refermer le volet à l'écran."""
    brancher(configure, monkeypatch, REEL["getState"])
    configure.ouvrir_volet({"artist": {"name": "Nina Simone"}, "album": None}, 60)
    assert "panel" in local.get("/api/state").get_json()

    def panne(url, *a, **k):
        raise OSError("réseau coupé")
    monkeypatch.setattr(configure.http, "get", panne)
    configure.ARTIST_PANEL["scroll"] = 3
    e = local.get("/api/state").get_json()
    assert e["connected"] is True, "dernier état connu resservi"
    assert e["panel"]["artist"]["name"] == "Nina Simone"
    assert e["panel"]["scroll"] == 3, "le défilement suit les touches, même pendant le raté"


def test_volet_ferme_ne_revient_pas_avec_l_etat_resservi(configure, local, monkeypatch):
    brancher(configure, monkeypatch, REEL["getState"])
    configure.ouvrir_volet({"artist": {"name": "Nina Simone"}, "album": None}, 60)
    local.get("/api/state")
    configure.ARTIST_PANEL.update({"until": 0.0, "data": None})

    def panne(url, *a, **k):
        raise OSError("réseau coupé")
    monkeypatch.setattr(configure.http, "get", panne)
    assert "panel" not in local.get("/api/state").get_json()


class VerrouEspion:
    """Compte les prises du verrou du volet."""
    def __init__(self, verrou):
        self.verrou = verrou
        self.prises = 0

    def __enter__(self):
        self.prises += 1
        return self.verrou.__enter__()

    def __exit__(self, *a):
        return self.verrou.__exit__(*a)

    def locked(self):
        return self.verrou.locked()


def test_touches_du_volet_passent_par_son_verrou(configure, monkeypatch):
    """Tourner une page ou défiler ne doit pas pouvoir rouvrir à moitié un volet
    qu'une autre touche est en train de fermer."""
    srv = configure
    espion = VerrouEspion(srv.VERROU_VOLET)
    monkeypatch.setattr(srv, "VERROU_VOLET", espion)
    srv.ouvrir_volet({"artist": {"name": "Nina Simone"}, "album": None}, 60)
    avant = espion.prises
    assert srv.do_action("next") is True
    assert srv.ARTIST_PANEL["page"] == "album"
    assert srv.do_action("vol_down") is True
    assert srv.ARTIST_PANEL["scroll"] == 1
    assert espion.prises == avant + 2


def test_touche_sur_volet_ferme_ne_prolonge_rien(configure):
    srv = configure
    srv.ARTIST_PANEL.update({"until": 0.0, "data": None})
    assert srv.piloter_volet("next") is False
    assert srv.ARTIST_PANEL["until"] == 0.0


# ------------------------------------------------------------ appairage

def test_appairage_sans_reference_n_accepte_pas_une_touche_ancienne(configure, local):
    """Si le premier relevé de la dernière touche échoue, la page ne doit pas
    prendre pour un nouvel appui une touche pressée juste avant."""
    connecter = __import__("conftest").connecter
    connecter(local)
    html = local.get("/remote").get_data(as_text=True)
    assert "let seen = 0" not in html
    assert html.count("seen === null") == 2
