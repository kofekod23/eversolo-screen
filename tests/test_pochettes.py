"""Le proxy ne sert que les images que le serveur a lui-même désignées :
plus d'URL libre, donc plus de relais ouvert vers Internet ou le réseau."""

from urllib.parse import quote


class FausseReponse:
    def __init__(self, contenu=b"\xff\xd8\xffJPEG", ctype="image/jpeg"):
        self.headers = {"Content-Type": ctype, "Content-Length": str(len(contenu))}
        self.is_redirect = False
        self._contenu = contenu

    def raise_for_status(self):
        pass

    def iter_content(self, taille):
        yield self._contenu

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_identifiant_inconnu_refuse(srv, distant):
    assert distant.get("/api/cover?id=" + "0" * 32).status_code == 404


def test_url_libre_refusee(srv, distant, monkeypatch):
    appels = []
    monkeypatch.setattr(srv.http, "get", lambda *a, **k: appels.append(a) or FausseReponse())
    r = distant.get("/api/cover?u=" + quote("https://exemple.org/a.jpg", safe=""))
    assert r.status_code == 404
    assert appels == []


def test_image_designee_servie(srv, distant, monkeypatch):
    monkeypatch.setattr(srv, "host_is_private", lambda h: False)
    monkeypatch.setattr(srv.http, "get", lambda *a, **k: FausseReponse())
    chemin = srv.cover_ref("https://static.qobuz.com/images/covers/ab/cd/x_600.jpg")
    assert chemin.startswith("/api/cover?id=")
    r = distant.get(chemin)
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "image/jpeg"


def test_meme_image_meme_identifiant(srv):
    url = "https://static.qobuz.com/images/covers/ab/cd/x_600.jpg"
    assert srv.cover_ref(url) == srv.cover_ref(url)


def test_ancienne_forme_du_cache_reconvertie(srv):
    url = "https://www.theaudiodb.com/images/media/artist/thumb/x.jpg"
    assert srv.cover_ref("/api/cover?u=" + quote(url, safe="")) == srv.cover_ref(url)


def test_sans_image_rien(srv):
    assert srv.cover_ref(None) is None
    assert srv.cover_ref("") is None


def test_etat_de_lecture_designe_la_pochette(srv):
    srv.CONFIG["eversolo_ip"] = "192.168.1.42"
    etat = {"state": 3, "playType": 1, "position": 1000, "duration": 200000,
            "playingMusic": {"title": "Titre", "artist": "Artiste", "albumArt": "https://img.example/a.jpg"}}
    srv.MODEL_CACHE.update({"ip": "192.168.1.42", "name": "DMP-A6"})
    info = srv.normalize(etat)
    assert info["cover"].startswith("/api/cover?id=")


def test_photo_d_artiste_designee(srv):
    bio = {"artist": "A", "text": "Biographie", "image": "https://img.example/p.jpg",
           "facts": [], "source": "TheAudioDB"}
    fiche = srv.fiche_artiste(bio, "A", "fr")
    assert fiche["image"].startswith("/api/cover?id=")


def test_refus_si_la_connexion_aboutit_sur_le_reseau_local(srv, distant, monkeypatch):
    """Rebinding DNS : le nom semblait public, la connexion arrive sur le LAN."""
    reponse = FausseReponse()
    monkeypatch.setattr(srv, "host_is_private", lambda h: False)
    monkeypatch.setattr(srv.http, "get", lambda *a, **k: reponse)
    monkeypatch.setattr(srv, "ip_du_pair", lambda r: "192.168.1.1")
    chemin = srv.cover_ref("https://img.example/rebond.jpg")
    assert distant.get(chemin).status_code == 502
