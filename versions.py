#!/usr/bin/env python3
"""Mises à jour sûres : une version par dossier, signature vérifiée, bascule
atomique et retour arrière automatique.

Disposition sur le Pi (utilisateur u) :
  /home/u/eversolo-screen          dépôt de référence (récupère les tags) et
                                    données : config.json, auth.json, caches
  /home/u/eversolo-versions/v1.2.0 une version installée, avec son venv
  /home/u/eversolo-versions/courante   lien vers la version en service
  /home/u/eversolo-versions/precedente lien vers la version d'avant

Seule la bibliothèque standard est utilisée : le garde (`garde`), lancé par
systemd avant chaque démarrage, doit fonctionner avec le Python du système
même si la version installée est cassée.

Commandes : python3 versions.py garde | installer [vX.Y.Z] | revenir | etat
"""

import contextlib
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass

VERSION_RE = re.compile(r"v([0-9]{1,6})\.([0-9]{1,6})\.([0-9]{1,6})")
LOCAL_RE = re.compile(r"local-[0-9a-f]{7,40}")
NOTE_MAX = 200
EN_COURS = ("telechargement", "verification", "installation")
PERIME_S = 30 * 60        # une étape « en cours » plus vieille a été interrompue
ESSAIS_MAX = 3            # démarrages ratés avant le retour arrière
DUREE_GIT = 120           # secondes, par commande git
DUREE_PIP = 900           # secondes : un Pi 3 est lent
IMPORTS_CONTROLE = "flask, requests, waitress"
ETAPES = ("telechargement", "verification", "installation", "redemarrage",
          "a_jour", "echec", "retour")


class ErreurMaj(Exception):
    """Échec d'une étape ; le message est montré à l'utilisateur."""


@dataclass(frozen=True)
class Disposition:
    depot: str      # dépôt de référence et données
    racine: str     # dossier des versions

    @property
    def courante(self):
        return os.path.join(self.racine, "courante")

    @property
    def precedente(self):
        return os.path.join(self.racine, "precedente")

    @property
    def fichier_etat(self):
        return os.path.join(self.depot, "maj.json")

    @property
    def fichier_verrou(self):
        return os.path.join(self.depot, "maj.verrou")

    @property
    def config(self):
        """Hors du dépôt git : un `git pull` ne peut rien y remplacer."""
        return os.path.join(os.path.dirname(self.depot), ".config", "eversolo-screen")

    @property
    def signataires(self):
        return os.path.join(self.config, "signataires")

    @property
    def garde_installe(self):
        return os.path.join(self.config, "garde.py")

    def dossier(self, version):
        return os.path.join(self.racine, version)


def disposition_par_defaut(maison=None):
    maison = maison or os.path.expanduser("~")
    return Disposition(os.path.join(maison, "eversolo-screen"),
                       os.path.join(maison, "eversolo-versions"))


def disposition_de(base_dir):
    """Disposition si le code tourne depuis un dossier de versions, sinon None."""
    reel = os.path.realpath(base_dir)
    racine = os.path.dirname(reel)
    if not est_version(os.path.basename(reel)):
        return None
    if os.path.basename(racine) != "eversolo-versions":
        return None
    return Disposition(os.path.join(os.path.dirname(racine), "eversolo-screen"), racine)


# ------------------------------------------------------------- versions

def est_version(nom):
    return bool(VERSION_RE.fullmatch(nom or "") or LOCAL_RE.fullmatch(nom or ""))


def cle_version(nom):
    m = VERSION_RE.fullmatch(nom or "")
    return tuple(int(x) for x in m.groups()) if m else None


def tags_de_ls_remote(sortie):
    """Noms vX.Y.Z d'une sortie `git ls-remote --tags`."""
    tags = set()
    for ligne in sortie.splitlines():
        ref = ligne.split("\t")[-1].strip()
        nom = ref.removeprefix("refs/tags/").removesuffix("^{}")
        if cle_version(nom):
            tags.add(nom)
    return sorted(tags, key=cle_version)


def version_de_lien(lien):
    try:
        return os.path.basename(os.path.realpath(lien)) if os.path.islink(lien) else None
    except OSError:
        return None


# ------------------------------------------------------------- état

class Occupe(Exception):
    """Une autre opération de mise à jour tient le verrou."""


@contextlib.contextmanager
def verrou(dispo):
    """Une seule opération à la fois (installation, retour, garde,
    validation, recherche) : verrou de fichier, jamais bloquant."""
    os.makedirs(dispo.depot, exist_ok=True)
    with open(dispo.fichier_verrou, "a", encoding="utf-8") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Occupe("une mise à jour est déjà en cours") from exc
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def en_cours(etat, maintenant=None):
    """Vrai si une installation tourne vraiment (pas une étape interrompue)."""
    if etat.get("etape") not in EN_COURS:
        return False
    try:
        age = (maintenant or time.time()) - float(etat.get("depuis") or 0)
    except (TypeError, ValueError):
        return False
    return age < PERIME_S


def lire_etat(dispo):
    try:
        with open(dispo.fichier_etat, encoding="utf-8") as f:
            etat = json.load(f)
        return etat if isinstance(etat, dict) else {}
    except (OSError, ValueError):
        return {}


def ecrire_etat(dispo, **champs):
    etat = {**lire_etat(dispo), **champs, "depuis": time.time()}
    dossier = os.path.dirname(dispo.fichier_etat)
    fd, tmp = tempfile.mkstemp(dir=dossier, prefix=".maj-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(etat, f, ensure_ascii=False)
        os.replace(tmp, dispo.fichier_etat)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return etat


def noter_echec(dispo, version, erreur):
    """Comme ecrire_etat, sans jamais lever : disque plein, droits..."""
    try:
        ecrire_etat(dispo, etape="echec", version=version, erreur=str(erreur)[:200])
    except OSError:
        pass


def lier(lien, cible):
    """Bascule atomique d'un lien symbolique."""
    tmp = f"{lien}.tmp-{os.getpid()}"
    if os.path.lexists(tmp):
        os.remove(tmp)
    os.symlink(cible, tmp)
    os.replace(tmp, lien)


# ------------------------------------------------------------- commandes

def executer(cmd, cwd=None, duree=DUREE_GIT, env=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=duree, check=False,
                       env={**os.environ, **(env or {})})
    if r.returncode != 0:
        raise ErreurMaj(((r.stderr or r.stdout or "").strip().splitlines() or ["échec"])[-1][:200])
    return r.stdout


def git(dispo, *args, duree=DUREE_GIT):
    return executer(["git", "-C", dispo.depot, *args], duree=duree)


def candidates(tags, actuelle):
    """Versions plus récentes que celle en service, de la plus haute à la plus
    basse. Depuis une copie locale (local-<sha>), toutes : la signature
    vérifiera qu'elles prolongent le code en service."""
    valides = sorted((t for t in tags if cle_version(t)), key=cle_version, reverse=True)
    base = cle_version(actuelle or "")
    return [t for t in valides if base is None or cle_version(t) > base]


def proposable(dispo, tags, actuelle):
    """Plus haute version dont la signature tient et qui prolonge la version
    en service, ou None. Les tags doivent être présents localement (fetch).
    Un tag non signé plus haut (v999.0.0 poussé par un tiers) est ignoré au
    lieu de bloquer toutes les mises à jour suivantes."""
    for tag in candidates(tags, actuelle):
        if LOCAL_RE.fullmatch(actuelle or ""):
            sha = actuelle.removeprefix("local-")
            try:
                commit = git(dispo, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}").strip()
            except ErreurMaj:
                continue
            if commit.startswith(sha):
                return None  # le code en service est déjà cette version
        try:
            verifier_signature(dispo, tag, actuelle)
        except ErreurMaj as exc:
            print(f"[maj] {tag} ignorée : {exc}", file=sys.stderr)
            continue
        return tag
    return None


def notes(dispo, version):
    """Message du tag annoté (nouveautés), au plus 6 lignes."""
    try:
        texte = git(dispo, "for-each-ref", f"refs/tags/{version}",
                    "--format=%(contents:subject)%0a%(contents:body)")
    except ErreurMaj:
        return []
    lignes = [l.strip()[:NOTE_MAX] for l in texte.splitlines() if l.strip()]
    lignes = [l for l in lignes if not l.startswith("-----") and "SSH SIGNATURE" not in l]
    return [l for l in lignes if not re.fullmatch(r"[A-Za-z0-9+/=]{40,}", l)][:6]


def verifier_signature(dispo, version, actuelle=None):
    """Signature valide, nom signé identique au nom du tag (pas de rejeu d'un
    vieux tag sous un nouveau nom), code descendant de la version en service
    (pas de retour en arrière forcé). Renvoie le commit vérifié, figé."""
    if not os.path.isfile(dispo.signataires):
        raise ErreurMaj("aucune clé de signature enregistrée sur ce Pi")
    if not VERSION_RE.fullmatch(version or ""):
        raise ErreurMaj("nom de version invalide")
    git(dispo, "-c", "gpg.format=ssh", "-c", f"gpg.ssh.allowedSignersFile={dispo.signataires}",
        "verify-tag", f"refs/tags/{version}")
    signe = git(dispo, "for-each-ref", "--format=%(tag)", f"refs/tags/{version}").strip()
    if signe != version:
        raise ErreurMaj(f"le tag {version} porte la signature de « {signe} »")
    commit = git(dispo, "rev-parse", "--verify", f"refs/tags/{version}^{{commit}}").strip()
    base = None
    if actuelle and VERSION_RE.fullmatch(actuelle):
        base = f"refs/tags/{actuelle}^{{commit}}"
    elif actuelle and LOCAL_RE.fullmatch(actuelle):
        base = actuelle.removeprefix("local-")
    if base:
        try:
            git(dispo, "merge-base", "--is-ancestor", base, commit)
        except ErreurMaj as exc:
            raise ErreurMaj(f"{version} ne prolonge pas la version en service") from exc
    return commit


def _python_systeme():
    return shutil.which("python3") or sys.executable


def preparer_dossier(dispo, version, reference):
    """Copie de travail détachée + environnement Python verrouillé."""
    dossier = dispo.dossier(version)
    if os.path.lexists(dossier):
        retirer_version(dispo, version)
    git(dispo, "worktree", "add", "--detach", "--force", dossier, reference)
    executer([_python_systeme(), "-m", "venv", os.path.join(dossier, "venv")], duree=300)
    pip = os.path.join(dossier, "venv", "bin", "pip")
    verrou = os.path.join(dossier, "requirements.lock")
    if not os.path.isfile(verrou):
        raise ErreurMaj("requirements.lock absent : dépendances non vérifiables")
    executer([pip, "install", "--quiet", "--require-hashes", "-r", verrou], duree=DUREE_PIP)
    # contrôle à froid : le code se compile et ses dépendances s'importent
    py = os.path.join(dossier, "venv", "bin", "python")
    executer([py, "-m", "py_compile", os.path.join(dossier, "server.py")], duree=120)
    executer([py, "-c", f"import {IMPORTS_CONTROLE}"], duree=120)
    return dossier


def basculer(dispo, version):
    actuelle = os.path.realpath(dispo.courante) if os.path.islink(dispo.courante) else None
    if actuelle and os.path.basename(actuelle) != version:
        lier(dispo.precedente, actuelle)
    lier(dispo.courante, dispo.dossier(version))


def installer(dispo, version=None, local=False):
    with verrou(dispo):
        return _installer(dispo, version, local)


def _installer(dispo, version, local):
    """Télécharge, vérifie et installe une version, puis bascule dessus.

    Le redémarrage est laissé à l'appelant (systemd relance le serveur).
    `local=True` installe la copie actuelle du dépôt de référence sans
    signature : première installation, avant toute version signée."""
    os.makedirs(dispo.racine, exist_ok=True)
    precedente = version_de_lien(dispo.courante)
    gardee = version_de_lien(dispo.precedente)
    try:
        if local:
            sha = git(dispo, "rev-parse", "--short", "HEAD").strip()
            version, reference = f"local-{sha}", "HEAD"
            if version == precedente:
                return version
        else:
            if not os.path.isfile(dispo.signataires):
                raise ErreurMaj("aucune clé de signature enregistrée sur ce Pi")
            ecrire_etat(dispo, etape="telechargement", version=version, erreur=None)
            git(dispo, "fetch", "--quiet", "--tags", "origin", duree=300)
            if not version:
                locaux = tags_de_ls_remote(git(dispo, "ls-remote", "--tags", "."))
                version = proposable(dispo, locaux, precedente) or (
                    precedente if precedente in locaux else None)
            if not version:
                raise ErreurMaj("aucune version signée publiée")
            ecrire_etat(dispo, etape="verification", version=version)
            commit = verifier_signature(dispo, version, None if version == precedente else precedente)
            if version == precedente:
                # déjà en service : ne jamais effacer le dossier qui tourne
                ecrire_etat(dispo, etape="a_jour", version=version, erreur=None)
                return version
            reference = commit  # le commit vérifié, plus le nom du tag
        if version == gardee:
            # dossier de secours : on ne le reconstruit pas, on y revient
            raise ErreurMaj(f"{version} est la version précédente : utilisez « Revenir »")
        ecrire_etat(dispo, etape="installation", version=version, erreur=None)
        preparer_dossier(dispo, version, reference)
        basculer(dispo, version)
        ecrire_etat(dispo, etape="redemarrage", version=version, precedente=precedente,
                    essais=0, validee=False, erreur=None)
        return version
    except (ErreurMaj, OSError, subprocess.TimeoutExpired) as exc:
        noter_echec(dispo, version, exc)
        raise ErreurMaj(str(exc)) from exc


def garde(dispo):
    """Avant chaque démarrage : après ESSAIS_MAX démarrages ratés d'une
    nouvelle version, on revient à la précédente. Ne bloque jamais."""
    try:
        with verrou(dispo):
            return _garde(dispo)
    except (Occupe, OSError, ValueError) as exc:
        print(f"[garde] ignoré : {exc}", file=sys.stderr)
        return "rien"


def _garde(dispo):
    etat = lire_etat(dispo)
    if etat.get("etape") != "redemarrage" or etat.get("validee"):
        return "rien"
    try:
        essais = int(etat.get("essais") or 0) + 1
    except (TypeError, ValueError):
        essais = 1
    precedent = os.path.realpath(dispo.precedente) if os.path.islink(dispo.precedente) else None
    if essais <= ESSAIS_MAX or not precedent or not os.path.isdir(precedent):
        ecrire_etat(dispo, essais=essais)
        return "essai"
    fautive = version_de_lien(dispo.courante)
    lier(dispo.courante, precedent)
    os.remove(dispo.precedente)  # rien vers quoi « revenir » : la fautive
    ecrire_etat(dispo, etape="retour", version=os.path.basename(precedent), fautive=fautive,
                erreur=f"{fautive} ne démarrait pas : retour à {os.path.basename(precedent)}",
                essais=0, validee=True)
    return "retour"


def valider(dispo):
    """Le serveur répond : la version en service est adoptée."""
    with verrou(dispo):
        return _valider(dispo)


def _valider(dispo):
    etat = lire_etat(dispo)
    if etat.get("etape") == "redemarrage" and not etat.get("validee"):
        ecrire_etat(dispo, etape="a_jour", validee=True, erreur=None)
        installer_garde(dispo)
        nettoyer(dispo)
        return True
    return False


def installer_garde(dispo, source=None):
    """Le garde lancé par systemd est la copie de versions.py d'une version
    qui a démarré : une version cassée ne peut pas casser son propre retour."""
    source = source or os.path.join(dispo.courante, "versions.py")
    if not os.path.isfile(source):
        return
    os.makedirs(dispo.config, exist_ok=True)
    tmp = dispo.garde_installe + ".tmp"
    shutil.copyfile(source, tmp)
    os.chmod(tmp, 0o644)
    os.replace(tmp, dispo.garde_installe)


def revenir(dispo):
    """Retour manuel à la version précédente (échange des deux liens)."""
    with verrou(dispo):
        return _revenir(dispo)


def _revenir(dispo):
    if not os.path.islink(dispo.precedente) or not os.path.isdir(os.path.realpath(dispo.precedente)):
        raise ErreurMaj("aucune version précédente")
    avant, apres = os.path.realpath(dispo.courante), os.path.realpath(dispo.precedente)
    lier(dispo.courante, apres)
    lier(dispo.precedente, avant)
    ecrire_etat(dispo, etape="retour", version=os.path.basename(apres),
                fautive=os.path.basename(avant), erreur=None, essais=0, validee=True)
    return os.path.basename(apres)


def retirer_version(dispo, version):
    dossier = dispo.dossier(version)
    try:
        git(dispo, "worktree", "remove", "--force", dossier)
    except ErreurMaj:
        shutil.rmtree(dossier, ignore_errors=True)
        try:
            git(dispo, "worktree", "prune")
        except ErreurMaj:
            pass


def nettoyer(dispo):
    """Garde la version en service et la précédente, retire les autres."""
    gardees = {version_de_lien(dispo.courante), version_de_lien(dispo.precedente)}
    try:
        noms = os.listdir(dispo.racine)
    except OSError:
        return []
    retirees = []
    for nom in noms:
        chemin = os.path.join(dispo.racine, nom)
        if nom in gardees or os.path.islink(chemin) or not os.path.isdir(chemin):
            continue
        if est_version(nom):
            retirer_version(dispo, nom)
            retirees.append(nom)
    return retirees


def main(argv):
    dispo = disposition_par_defaut()
    commande = argv[1] if len(argv) > 1 else "etat"
    try:
        if commande == "garde":
            print(f"[garde] {garde(dispo)}")
            return 0  # ne jamais empêcher le démarrage
        if commande == "installer":
            local = "--local" in argv
            cible = next((a for a in argv[2:] if cle_version(a)), None)
            print(f"Installé : {installer(dispo, cible, local=local)}")
            return 0
        if commande == "revenir":
            print(f"Revenu à : {revenir(dispo)}")
            return 0
        print(json.dumps({**lire_etat(dispo), "courante": version_de_lien(dispo.courante),
                          "precedente": version_de_lien(dispo.precedente)}, ensure_ascii=False))
        return 0
    except (ErreurMaj, Occupe) as exc:
        print(f"Échec : {exc}", file=sys.stderr)
        return 0 if commande == "garde" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
