"""Première configuration : sans le code affiché sur la TV, personne sur le
réseau ne peut créer le compte administrateur."""

from conftest import jeton_csrf


def formulaire(client, **champs):
    csrf = jeton_csrf(client.get("/setup?ici=1").get_data(as_text=True))
    donnees = {"csrf": csrf, "password": "motdepasse-solide", "password2": "motdepasse-solide",
               "device_ip": "192.168.1.42"}
    donnees.update(champs)
    return client.post("/setup", data=donnees)


def test_code_a_six_chiffres(srv):
    code = srv.code_installation()
    assert len(code) == 6 and code.isdigit()
    assert srv.code_installation() == code


def test_le_code_s_affiche_sur_la_tv(srv, local):
    page = local.get("/setup").get_data(as_text=True)
    assert srv.code_installation() in page


def test_le_code_ne_s_affiche_pas_au_reseau(srv, distant):
    page = distant.get("/setup").get_data(as_text=True)
    assert srv.code_installation() not in page


def test_installation_sans_code_refusee(srv, distant):
    formulaire(distant)
    assert srv.load_auth() is None


def test_installation_avec_mauvais_code_refusee(srv, distant):
    faux = "000000" if srv.code_installation() != "000000" else "111111"
    formulaire(distant, code=faux)
    assert srv.load_auth() is None


def test_installation_avec_le_bon_code(srv, distant):
    r = formulaire(distant, code=srv.code_installation())
    assert r.status_code == 302
    assert srv.load_auth() is not None
    assert srv.CONFIG["eversolo_ip"] == "192.168.1.42"


def faux_code(srv):
    return "000000" if srv.code_installation() != "000000" else "111111"


def test_le_code_reste_stable_apres_des_erreurs(srv, distant):
    initial = srv.code_installation()
    for _ in range(5):
        formulaire(distant, code=faux_code(srv))
    assert srv.code_installation() == initial


def test_adresse_bloquee_apres_cinq_erreurs(srv, distant):
    for _ in range(5):
        formulaire(distant, code=faux_code(srv))
    formulaire(distant, code=srv.code_installation())
    assert srv.load_auth() is None


def test_autre_appareil_non_bloque_par_un_invite(srv, distant):
    for _ in range(5):
        formulaire(distant, code=faux_code(srv))
    from conftest import client
    proprietaire = client(srv, "192.168.1.77", "192.168.1.10:8080")
    formulaire(proprietaire, code=srv.code_installation())
    assert srv.load_auth() is not None


def test_pause_generale_apres_trente_erreurs(srv):
    for i in range(30):
        srv.verifier_code("ab", f"10.0.0.{i}")
    assert not srv.verifier_code(srv.code_installation(), "10.0.1.1")


def test_le_kiosque_peut_configurer_sans_code(srv, local):
    formulaire(local)
    assert srv.load_auth() is not None


def test_etat_d_installation_reserve_au_kiosque(srv, local, distant):
    assert distant.get("/api/setup/etat").status_code == 403
    d = local.get("/api/setup/etat").get_json()
    assert d == {"configure": False, "code": srv.code_installation()}


def test_detection_reseau_exige_le_code(srv, distant, monkeypatch):
    monkeypatch.setattr(srv, "scan_network", lambda: [{"ip": "192.168.1.42", "model": "DMP-A6"}])
    assert distant.get("/api/detect").status_code == 403
    r = distant.get("/api/detect", headers={"X-Code-Installation": srv.code_installation()})
    assert r.status_code == 200
    assert r.get_json()["found"][0]["ip"] == "192.168.1.42"


def test_detection_ouverte_au_kiosque(srv, local, monkeypatch):
    monkeypatch.setattr(srv, "scan_network", lambda: [])
    assert local.get("/api/detect").status_code == 200


def test_mauvais_code_de_detection_compte_comme_erreur(srv, distant, monkeypatch):
    monkeypatch.setattr(srv, "scan_network", lambda: [])
    for _ in range(5):
        distant.get("/api/detect", headers={"X-Code-Installation": faux_code(srv)})
    r = distant.get("/api/detect", headers={"X-Code-Installation": srv.code_installation()})
    assert r.status_code == 403


def test_relais_local_ne_vaut_pas_kiosque(srv):
    from conftest import client
    relais = client(srv, "127.0.0.1", "192.168.1.10:8080")
    assert relais.get("/api/setup/etat", headers={"Host": "192.168.1.10:8080"}).status_code == 403
    tunnel = client(srv, "127.0.0.1", "localhost:8080")
    r = tunnel.get("/api/setup/etat", headers={"X-Forwarded-For": "203.0.113.9"})
    assert r.status_code == 403


def test_code_tire_au_demarrage_pour_le_journal(srv):
    assert srv.INSTALLATION["code"] is not None
