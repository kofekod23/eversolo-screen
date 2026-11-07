"""Mises à jour sûres : vrais dépôts git, vraie signature SSH, vrais liens."""

import os
import subprocess
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)

import versions as v

pytestmark = pytest.mark.skipif(subprocess.run(["which", "ssh-keygen"], capture_output=True, check=False).returncode,
                                reason="ssh-keygen absent")
IDENTITE = ["-c", "user.name=Testeur", "-c", "user.email=testeur@exemple.org"]


def sh(*cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True).stdout


def cle(dossier, nom):
    chemin = os.path.join(dossier, nom)
    sh("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", nom, "-f", chemin)
    return chemin


@pytest.fixture
def monde(tmp_path, monkeypatch):
    """Dépôt publié (origine), copie de l'auteur, Pi avec son dépôt de référence."""
    monkeypatch.setattr(v, "IMPORTS_CONTROLE", "json")  # pas de réseau dans les tests
    origine = tmp_path / "origine.git"
    sh("git", "init", "-q", "--bare", str(origine))
    auteur = tmp_path / "auteur"
    sh("git", "clone", "-q", str(origine), str(auteur))
    cles = tmp_path / "cles"
    cles.mkdir()
    bonne, autre = cle(str(cles), "bonne"), cle(str(cles), "autre")

    def publier(version, contenu="print('ok')\n", signer=bonne, verrou=True):
        (auteur / "server.py").write_text(contenu)
        (auteur / "requirements.txt").write_text("")
        if verrou:
            (auteur / "requirements.lock").write_text("")
        elif (auteur / "requirements.lock").exists():
            (auteur / "requirements.lock").unlink()
        sh("git", *IDENTITE, "add", "-A", cwd=auteur)
        sh("git", *IDENTITE, "commit", "-q", "--allow-empty", "-m", version, cwd=auteur)
        if signer:
            sh("git", *IDENTITE, "-c", "gpg.format=ssh", "-c", f"user.signingkey={signer}.pub",
               "tag", "-s", version, "-m", f"{version}\n\nNouveautés de {version}", cwd=auteur)
        else:
            sh("git", *IDENTITE, "tag", "-a", version, "-m", version, cwd=auteur)
        sh("git", "push", "-q", "origin", "HEAD", version, cwd=auteur)

    publier("v1.0.0")
    maison = tmp_path / "maison"
    maison.mkdir()
    sh("git", "clone", "-q", str(origine), str(maison / "eversolo-screen"))
    dispo = v.disposition_par_defaut(str(maison))
    os.makedirs(dispo.config)
    with open(f"{bonne}.pub") as f, open(dispo.signataires, "w") as sortie:
        sortie.write(f'testeur@exemple.org namespaces="git" {f.read()}')
    return dispo, publier, autre


def test_versions_triees_et_candidates():
    sortie = "a\trefs/tags/v1.2.0\nb\trefs/tags/v1.2.0^{}\nc\trefs/tags/v1.10.0\nd\trefs/tags/essai\n"
    assert v.tags_de_ls_remote(sortie) == ["v1.2.0", "v1.10.0"]
    assert v.candidates(["v1.2.0", "v1.10.0"], "v1.9.9") == ["v1.10.0"]
    assert v.candidates(["v1.2.0"], "v1.2.0") == []
    assert v.candidates(["v1.2.0", "v1.10.0"], "local-abc1234") == ["v1.10.0", "v1.2.0"]


def test_disposition_reconnue_depuis_le_dossier_de_version(tmp_path):
    dossier = tmp_path / "eversolo-versions" / "v1.2.0"
    dossier.mkdir(parents=True)
    d = v.disposition_de(str(dossier))
    assert d.depot == str(tmp_path / "eversolo-screen")
    assert v.disposition_de(str(tmp_path / "eversolo-screen")) is None


def test_installation_signee_puis_bascule(monde):
    dispo, publier, _ = monde
    assert v.installer(dispo) == "v1.0.0"
    publier("v1.1.0")
    assert v.installer(dispo) == "v1.1.0"
    assert v.version_de_lien(dispo.courante) == "v1.1.0"
    assert v.version_de_lien(dispo.precedente) == "v1.0.0"
    etat = v.lire_etat(dispo)
    assert etat["etape"] == "redemarrage" and etat["validee"] is False
    assert os.path.isfile(os.path.join(dispo.courante, "venv", "bin", "python"))
    assert "Nouveautés de v1.1.0" in v.notes(dispo, "v1.1.0")


def test_tag_non_signe_refuse(monde):
    dispo, publier, _ = monde
    v.installer(dispo)
    publier("v1.1.0", signer=None)
    with pytest.raises(v.ErreurMaj):
        v.installer(dispo, "v1.1.0")
    assert v.version_de_lien(dispo.courante) == "v1.0.0"
    assert v.lire_etat(dispo)["etape"] == "echec"


def test_tag_signe_par_une_autre_cle_refuse(monde):
    dispo, publier, autre = monde
    v.installer(dispo)
    publier("v1.1.0", signer=autre)
    with pytest.raises(v.ErreurMaj):
        v.installer(dispo, "v1.1.0")
    assert v.version_de_lien(dispo.courante) == "v1.0.0"


def test_sans_signataires_rien_ne_s_installe(monde):
    dispo, _, _ = monde
    os.remove(dispo.signataires)
    with pytest.raises(v.ErreurMaj, match="clé"):
        v.installer(dispo)
    assert not os.path.lexists(dispo.courante)


def test_retour_automatique_apres_trois_demarrages_rates(monde):
    dispo, publier, _ = monde
    v.installer(dispo)
    v.valider(dispo)
    publier("v1.1.0", contenu="raise SystemExit(1)\n")
    v.installer(dispo)
    assert [v.garde(dispo) for _ in range(3)] == ["essai"] * 3
    assert v.garde(dispo) == "retour"
    assert v.version_de_lien(dispo.courante) == "v1.0.0"
    etat = v.lire_etat(dispo)
    assert etat["etape"] == "retour" and etat["fautive"] == "v1.1.0"
    assert v.garde(dispo) == "rien"  # plus rien à faire ensuite


def test_validation_puis_nettoyage(monde):
    dispo, publier, _ = monde
    for version in ("v1.1.0", "v1.2.0"):
        v.installer(dispo)
        v.valider(dispo)
        publier(version)
    v.installer(dispo)
    assert v.valider(dispo)
    assert v.lire_etat(dispo)["etape"] == "a_jour"
    restantes = sorted(n for n in os.listdir(dispo.racine) if n.startswith("v"))
    assert restantes == ["v1.1.0", "v1.2.0"]  # en service + précédente
    assert v.garde(dispo) == "rien"


def test_retour_manuel(monde):
    dispo, publier, _ = monde
    v.installer(dispo)
    publier("v1.1.0")
    v.installer(dispo)
    assert v.revenir(dispo) == "v1.0.0"
    assert v.version_de_lien(dispo.courante) == "v1.0.0"
    assert v.version_de_lien(dispo.precedente) == "v1.1.0"


def test_premiere_installation_locale_sans_signature(monde):
    dispo, _, _ = monde
    version = v.installer(dispo, local=True)
    assert version.startswith("local-")
    assert v.version_de_lien(dispo.courante) == version


def test_garde_ne_bloque_jamais(tmp_path):
    dispo = v.disposition_par_defaut(str(tmp_path))
    assert v.garde(dispo) == "rien"


def test_reinstaller_la_version_en_service_ne_l_efface_pas(monde):
    dispo, _, _ = monde
    v.installer(dispo)
    temoin = os.path.join(dispo.courante, "temoin")
    open(temoin, "w").close()
    assert v.installer(dispo) == "v1.0.0"
    assert os.path.exists(temoin)
    assert v.lire_etat(dispo)["etape"] == "a_jour"


def test_rejeu_d_un_vieux_tag_signe_sous_un_nouveau_nom(monde, tmp_path):
    dispo, publier, _ = monde
    v.installer(dispo)
    publier("v1.1.0")
    v.installer(dispo)
    auteur = tmp_path / "auteur"
    objet = sh("git", "rev-parse", "refs/tags/v1.0.0", cwd=auteur).strip()
    sh("git", "update-ref", "refs/tags/v9.9.9", objet, cwd=auteur)
    sh("git", "push", "-q", "origin", "v9.9.9", cwd=auteur)
    with pytest.raises(v.ErreurMaj, match="signature"):
        v.installer(dispo, "v9.9.9")
    assert v.version_de_lien(dispo.courante) == "v1.1.0"


def test_version_signee_qui_ne_prolonge_pas_la_courante_refusee(monde, tmp_path):
    dispo, publier, _ = monde
    v.installer(dispo)
    publier("v1.1.0")
    v.installer(dispo)
    auteur = tmp_path / "auteur"
    sh("git", "checkout", "-q", "-b", "ancienne", "v1.0.0", cwd=auteur)
    publier("v1.2.0")  # signée, mais bâtie sur v1.0.0
    with pytest.raises(v.ErreurMaj, match="prolonge"):
        v.installer(dispo, "v1.2.0")
    assert v.version_de_lien(dispo.courante) == "v1.1.0"


def test_une_seule_operation_a_la_fois(monde):
    dispo, _, _ = monde
    with v.verrou(dispo), pytest.raises(v.Occupe):
        v.installer(dispo)
    assert v.garde(dispo) == "rien"  # le garde ne bloque pas non plus


def test_garde_installe_apres_validation(monde):
    dispo, _, _ = monde
    v.installer(dispo)
    assert not os.path.exists(dispo.garde_installe)
    with open(os.path.join(dispo.courante, "versions.py"), "w") as f:
        f.write("# garde\n")
    v.valider(dispo)
    assert os.path.isfile(dispo.garde_installe)


def test_etape_interrompue_n_est_plus_en_cours():
    assert v.en_cours({"etape": "installation", "depuis": 1000}, maintenant=1000 + 60)
    assert not v.en_cours({"etape": "installation", "depuis": 1000}, maintenant=1000 + 3600)


def test_noms_de_version_stricts():
    assert v.cle_version("v1.2.3") == (1, 2, 3)
    assert v.cle_version("v1.2.3\n") is None
    assert v.cle_version("v١.2.3") is None  # chiffres non ASCII
    assert v.cle_version("v" + "9" * 5000 + ".0.0") is None


def test_tag_non_signe_plus_haut_ne_bloque_pas_les_mises_a_jour(monde):
    dispo, publier, _ = monde
    v.installer(dispo)
    publier("v1.1.0")
    publier("v9.0.0", signer=None)  # poussé par un tiers, sans signature
    assert v.installer(dispo) == "v1.1.0"
    assert v.version_de_lien(dispo.courante) == "v1.1.0"


def test_sans_verrou_des_dependances_rien_ne_s_installe(monde):
    dispo, publier, _ = monde
    v.installer(dispo)
    publier("v1.1.0", verrou=False)
    with pytest.raises(v.ErreurMaj, match="requirements.lock"):
        v.installer(dispo, "v1.1.0")
    assert v.version_de_lien(dispo.courante) == "v1.0.0"
