"""Commandes réservées : un invité sur le Wi-Fi ne pilote ni l'Eversolo par le
Pi, ni l'émetteur infrarouge."""

import os

from conftest import connecter

ENTETE = {"X-Requested-With": "eversolo"}


def test_pilotage_refuse_sans_session(configure, distant, monkeypatch):
    appels = []
    monkeypatch.setattr(configure, "do_action", lambda a: appels.append(a) or True)
    r = distant.post("/api/control/next", headers=ENTETE)
    assert r.status_code == 401
    assert appels == []


def test_pilotage_accepte_pour_l_admin(configure, distant, monkeypatch):
    monkeypatch.setattr(configure, "do_action", lambda a: True)
    connecter(distant)
    assert distant.post("/api/control/next", headers=ENTETE).status_code == 200


def test_emetteur_refuse_sans_session(configure, distant, monkeypatch):
    envoyes = []
    monkeypatch.setattr(configure, "send_raw", lambda p: envoyes.append(p) or True)
    r = distant.post("/api/blast/tv_power", headers=ENTETE)
    assert r.status_code == 401
    assert envoyes == []


def test_emetteur_refuse_sans_jeton_csrf(configure, distant, monkeypatch):
    monkeypatch.setattr(configure, "send_raw", lambda p: True)
    connecter(distant)
    assert distant.post("/api/blast/tv_power", headers=ENTETE).status_code == 403


def test_emetteur_accepte_pour_l_admin(configure, distant, monkeypatch):
    os.makedirs(configure.IR_CODES_DIR, exist_ok=True)
    with open(os.path.join(configure.IR_CODES_DIR, "tv_power.ir"), "w") as f:
        f.write("+900 -450\n")
    envoyes = []
    monkeypatch.setattr(configure, "send_raw", lambda p: envoyes.append(p) or True)
    jeton = connecter(distant)
    r = distant.post("/api/blast/tv_power", headers=dict(ENTETE, **{"X-CSRF-Token": jeton}))
    assert r.status_code == 200
    assert len(envoyes) == 1


def test_donnees_dans_le_dossier_de_donnees(configure, tmp_path):
    assert configure.CONFIG_PATH.startswith(str(tmp_path))
    assert configure.IR_CODES_DIR.startswith(str(tmp_path))


def test_changer_le_mot_de_passe_ferme_les_autres_sessions(configure, srv):
    from conftest import HOTE_PI, client, connecter
    autre = client(srv, "192.168.1.77", HOTE_PI)
    connecter(autre)
    assert autre.get("/config").status_code == 200
    from werkzeug.security import generate_password_hash
    srv.save_auth(generate_password_hash("nouveau-secret-123", method="scrypt"))
    assert autre.get("/config").status_code == 302


def test_ancien_cookie_booleen_refuse(configure, srv):
    from conftest import HOTE_PI, client
    c = client(srv, "192.168.1.77", HOTE_PI)
    with c.session_transaction() as s:
        s["auth"] = True
    assert c.get("/config").status_code == 302


def test_blocage_global_quand_les_adresses_changent(configure, srv):
    for i in range(srv.MAX_ECHECS_CONNEXION):
        srv.record_failure(f"10.0.{i // 250}.{i % 250}")
    assert srv.is_locked("10.9.9.9")


def test_nom_de_code_ir_sans_retour_a_la_ligne(srv):
    assert srv.NAME_RE.fullmatch("abc")
    assert not srv.NAME_RE.fullmatch("abc\n")
