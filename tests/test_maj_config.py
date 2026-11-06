"""Section « Mise à jour » de /config, une fois installé par versions."""

import os

import pytest
from conftest import connecter


@pytest.fixture
def versionne(configure, tmp_path, monkeypatch):
    import versions
    racine = tmp_path / "maison" / "eversolo-versions"
    for nom in ("v1.0.0", "v1.1.0"):
        (racine / nom).mkdir(parents=True)
    depot = tmp_path / "maison" / "eversolo-screen"
    depot.mkdir()
    dispo = versions.Disposition(str(depot), str(racine))
    versions.lier(dispo.courante, str(racine / "v1.1.0"))
    versions.lier(dispo.precedente, str(racine / "v1.0.0"))
    monkeypatch.setattr(configure, "DISPO", dispo)
    monkeypatch.setattr(configure, "VERSION_LOCALE", "v1.1.0")
    monkeypatch.setattr(configure, "chercher_mise_a_jour", lambda: None)
    configure.MAJ_DISPONIBLE.update(version="v1.2.0", notes=["Volume plus lisible"])
    appels = []
    monkeypatch.setattr(configure, "installer_version", lambda v: appels.append(("installer", v)))
    monkeypatch.setattr(configure, "revenir_version", lambda: appels.append(("revenir",)))
    return configure, dispo, appels


def test_section_montre_version_nouveautes_et_retour(versionne, distant):
    connecter(distant)
    page = distant.get("/config").get_data(as_text=True)
    assert "v1.1.0" in page and "v1.2.0" in page and "Volume plus lisible" in page
    assert 'value="update"' in page and 'value="retour"' in page and "v1.0.0" in page


def test_installation_refusee_pendant_la_lecture(versionne, distant):
    srv, _, appels = versionne
    srv.STATE_CACHE["info"] = {"etat": "lecture"}
    jeton = connecter(distant)
    page = distant.post("/config", data={"csrf": jeton, "op": "update"}).get_data(as_text=True)
    assert "pause" in page.lower() and appels == []


def test_installation_lancee_a_l_arret(versionne, distant):
    srv, _, appels = versionne
    srv.STATE_CACHE["info"] = {"etat": "pause"}
    jeton = connecter(distant)
    distant.post("/config", data={"csrf": jeton, "op": "update"})
    assert appels == [("installer", "v1.2.0")]


def test_retour_manuel_et_csrf(versionne, distant):
    _, _, appels = versionne
    connecter(distant)
    distant.post("/config", data={"op": "retour"})  # sans jeton
    assert appels == []
    jeton = connecter(distant)
    distant.post("/config", data={"csrf": jeton, "op": "retour"})
    assert appels == [("revenir",)]


def test_echec_affiche_sur_la_page(versionne, distant):
    import versions
    _, dispo, _ = versionne
    versions.ecrire_etat(dispo, etape="echec", erreur="signature invalide <b>")
    connecter(distant)
    page = distant.get("/config").get_data(as_text=True)
    assert "signature invalide &lt;b&gt;" in page


def test_progression_exposee_a_l_ecran(versionne, local, monkeypatch):
    import versions
    srv, dispo, _ = versionne
    versions.ecrire_etat(dispo, etape="verification", version="v1.2.0")
    assert srv.maj_en_cours() == {"etape": "verification", "version": "v1.2.0"}
    assert os.path.islink(dispo.courante)
