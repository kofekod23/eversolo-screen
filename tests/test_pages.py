"""Les pages touchées par le lot 0 s'affichent et portent ce qu'il faut."""

from conftest import connecter


def test_ecran_tv_d_installation(srv, local):
    page = local.get("/setup").get_data(as_text=True)
    assert "/api/setup/etat" in page and ".local:8080" in page
    assert 'name="code"' not in page


def test_formulaire_reseau_demande_le_code(srv, distant):
    page = distant.get("/setup").get_data(as_text=True)
    assert 'name="code"' in page and "X-Code-Installation" in page


def test_page_emetteur_envoie_le_jeton(configure, distant):
    jeton = connecter(distant)
    page = distant.get("/blaster").get_data(as_text=True)
    assert f"'X-CSRF-Token': \"{jeton}\"" in page


def test_reglages_proposent_la_capture(configure, distant):
    connecter(distant)
    page = distant.get("/config").get_data(as_text=True)
    assert 'value="capture"' in page and 'value="qobuz"' in page


def test_capture_impossible_sans_eversolo(configure, distant, monkeypatch):
    def panne(*a, **k):
        raise OSError("injoignable")
    monkeypatch.setattr(configure.http, "get", panne)
    jeton = connecter(distant)
    page = distant.post("/config", data={"csrf": jeton, "op": "capture", "situation": "radio"})
    assert "Eversolo injoignable" in page.get_data(as_text=True)


def test_situation_inconnue_devient_autre(configure, distant, monkeypatch):
    class R:
        def json(self):
            return {"state": 4}
    monkeypatch.setattr(configure.http, "get", lambda *a, **k: R())
    jeton = connecter(distant)
    distant.post("/config", data={"csrf": jeton, "op": "capture", "situation": "../../x"})
    assert configure.liste_captures()[0].endswith("-autre.json")
