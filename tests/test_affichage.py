"""Ce que l'écran lit dans l'état de l'Eversolo : signal, volume, sortie,
place de la plage, découvertes. Échantillon réel : DMP-A6, micrologiciel
1.6.15, Tidal à l'arrêt (masqué)."""

import copy
import json
import os
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)

import affichage as aff

with open(os.path.join(RACINE, "tests", "fixtures", "dmp-a6-tidal-arret.json"), encoding="utf-8") as f:
    REEL = json.load(f)
ETAT = REEL["getState"]
IO = REEL["getInputAndOutputList"]
FILE = REEL["getPlayQueue"]


def etat_avec(**musique):
    e = copy.deepcopy(ETAT)
    e["playingMusic"].update(musique)
    return e


# ------------------------------------------------------------ état de lecture

@pytest.mark.parametrize("code, attendu", [(3, "lecture"), (4, "pause"), (0, "arret"), (7, "arret")])
def test_etat_de_lecture(code, attendu):
    assert aff.etat_lecture({"state": code}) == attendu


# --------------------------------------------------------------------- signal

def test_signal_tidal_reel():
    s = aff.signal_audio(ETAT, "fr")
    assert s["source"] == "Tidal"
    assert s["format"] == "FLAC"
    assert s["resolution"] == "24 bit / 48 kHz"
    assert s["classe"] == "hires"
    assert s["debit"] is None  # jamais de débit pour du sans perte


def test_signal_qualite_cd_avec_virgule_decimale():
    e = etat_avec(streamId="qobuz", bits=16, sampleRateNumber=44100, sampleRate="44.1 kHz")
    s = aff.signal_audio(e, "fr")
    assert s["source"] == "Qobuz"
    assert s["resolution"] == "16 bit / 44,1 kHz"
    assert s["classe"] == "cd"
    assert aff.signal_audio(e, "en")["resolution"] == "16 bit / 44.1 kHz"


def test_signal_dsd_en_megahertz():
    e = etat_avec(extension="DSF", bits=1, sampleRateNumber=2822400, sampleRate="2.8 MHz", streamId="")
    s = aff.signal_audio(e, "fr")
    assert s["format"] == "DSD64"
    assert s["resolution"] == "2,8 MHz"
    assert s["classe"] == "dsd"
    assert s["source"] is None


def test_signal_dsd_reconnu_a_la_frequence_seule():
    e = etat_avec(extension="", bits=0, sampleRateNumber=0, sampleRate="5.6 MHz")
    s = aff.signal_audio(e, "fr")
    assert (s["format"], s["resolution"]) == ("DSD128", "5,6 MHz")


def test_signal_avec_perte_montre_le_debit():
    e = etat_avec(extension="MP3", bits=0, sampleRateNumber=44100, bitrate="320 kbps", streamId="")
    s = aff.signal_audio(e, "fr")
    assert s["classe"] == "perte"
    assert s["debit"] == "320 kbps"
    assert s["resolution"] == "44,1 kHz"


def test_signal_appli_externe_lit_l_autre_bloc():
    e = copy.deepcopy(ETAT)
    e["playType"] = 6
    info = e["everSoloPlayInfo"]["everSoloPlayAudioInfo"]
    info.update(audioSampleRate=44100, audioBitsPerSample=16, audioBitrate=0)
    s = aff.signal_audio(e, "fr")
    assert s["resolution"] == "16 bit / 44,1 kHz"
    assert s["source"] is None  # le titre Tidal resté dans playingMusic ne compte plus


def test_signal_vide_sans_rien():
    s = aff.signal_audio({}, "fr")
    assert s == {"source": None, "format": None, "resolution": None,
                 "classe": None, "debit": None}


# --------------------------------------------------------------------- volume

def test_volume_reel_en_decibels():
    v = aff.lire_volume(ETAT)
    assert v == {"pct": 100, "texte": "0 dB", "muet": False}


def test_volume_negatif_avec_vrai_signe_moins():
    e = copy.deepcopy(ETAT)
    e["volumeData"].update(currenttVolume=120, display="-40 dB", isMute=True)
    v = aff.lire_volume(e)
    assert v == {"pct": 60, "texte": "−40 dB", "muet": True}


def test_volume_sans_affichage_donne_le_nombre():
    v = aff.lire_volume({"volumeData": {"currenttVolume": 35, "maxVolume": 100, "minVolume": 0}})
    assert v["texte"] == "35" and v["pct"] == 35


def test_volume_absent_ou_incoherent():
    assert aff.lire_volume({}) is None
    assert aff.lire_volume({"volumeData": {"currenttVolume": "x", "maxVolume": 100}}) is None
    assert aff.lire_volume({"volumeData": {"currenttVolume": 5, "maxVolume": 0}}) is None


# ------------------------------------------------------------ entrée et sortie

def test_sortie_et_entree_actives():
    assert aff.sortie_active(IO) == "Sortie OPT/COAX"
    assert aff.entree_active(IO) == "Lecteur interne"


def test_sortie_hors_bornes():
    assert aff.sortie_active({"outputData": [], "outputIndex": 3}) is None
    assert aff.sortie_active(None) is None
    assert aff.entree_active({"inputData": [{"name": "X"}], "inputIndex": "a"}) is None


# ---------------------------------------------------------- place de la plage

PISTES = [{"n": "1", "title": "Those Dancing Days Are Gone"},
          {"n": "2", "title": "Stand By Your Man"},
          {"n": "3", "title": "Enjoy the Silence"}]


def test_place_dans_l_album():
    assert aff.place_dans_album("Stand by your man", PISTES) == (2, 3)
    assert aff.place_dans_album("Stand By Your Man (Remastered)", PISTES) == (2, 3)
    assert aff.place_dans_album("Inconnue", PISTES) is None
    assert aff.place_dans_album("Stand By Your Man", []) is None


def test_suivant_dans_la_file():
    suiv = aff.suivant_dans_file(FILE, 0, "Captain Bacardi")
    assert suiv == {"title": "The Long Way Home", "artist": "Norah Jones"}


def test_suivant_refuse_si_la_file_ne_correspond_pas():
    assert aff.suivant_dans_file(FILE, 0, "Autre titre") is None
    assert aff.suivant_dans_file(FILE, 2, "Stuck on You") is None  # dernière chargée
    assert aff.suivant_dans_file(FILE, -1, "Captain Bacardi") is None
    assert aff.suivant_dans_file({}, 0, "x") is None


# ----------------------------------------------------------------- découvertes

ALBUM = {"title": "French Touch", "facts": ["2017", "Barclay", "Pop"],
         "tracks": PISTES, "credits": [{"role": "Production", "name": "David Foster"}]}
ARTISTE = {"name": "Carla Bruni", "facts": ["Turin", "1967"],
           "text": "Carla Bruni est une auteure-compositrice-interprète franco-italienne. "
                   "Elle a été mannequin."}


def test_decouvertes_completes():
    signal = aff.signal_audio(ETAT, "fr")
    d = aff.decouvertes("Stand By Your Man", ALBUM, ARTISTE, [], signal,
                        "Sortie OPT/COAX", "fr")
    cles = [x["k"] for x in d]
    assert cles[0] == "Album"
    assert d[0]["v"] == "2017, Barclay, Pop"
    assert {"k": "Plage", "v": "2 sur 3"} in d
    assert {"k": "Production", "v": "David Foster"} in d
    assert any(x["k"] == "Artiste" and x["v"].endswith("franco-italienne.") for x in d)
    chaine = next(x["v"] for x in d if x["k"] == "Signal")
    assert chaine == "Tidal → FLAC 24 bit / 48 kHz → Sortie OPT/COAX"


def test_decouvertes_traduites():
    d = aff.decouvertes("Stand By Your Man", ALBUM, None, [], None, None, "en")
    assert {"k": "Track", "v": "2 of 3"} in d


def test_decouvertes_credits_de_plage_en_premier():
    plage = [{"role": "Écriture", "name": "Tammy Wynette"}, {"role": "Écriture", "name": "Billy Sherrill"}]
    d = aff.decouvertes("Stand By Your Man", ALBUM, None, plage, None, None, "fr")
    assert {"k": "Écriture", "v": "Tammy Wynette, Billy Sherrill"} in d
    assert not any(x["k"] == "Production" for x in d)


def test_decouvertes_vides_sans_rien():
    assert aff.decouvertes("x", None, None, [], None, None, "fr") == []


def test_phrase_artiste_trop_longue_coupee_au_mot():
    texte = "Mot " * 200
    d = aff.decouvertes("x", None, {"name": "A", "facts": [], "text": texte}, [], None, None, "fr")
    v = d[0]["v"]
    assert len(v) <= 181 and v.endswith("…") and not v.endswith(" …")


# -------------------------------------------------------- réglages d'affichage

def test_reglages_par_defaut():
    r = aff.reglages_affichage({})
    assert r == {"theme": "pochette", "profil": "salon", "nuit": "auto", "nuit_debut": 22, "nuit_fin": 7,
                 "protection": True}


def test_reglages_valeurs_hostiles_ramenees_aux_defauts():
    r = aff.reglages_affichage({"ecran_theme": "x", "ecran_profil": "<script>", "ecran_nuit": "x",
                                "nuit_debut": 99, "nuit_fin": "7", "ecran_protection": "oui"})
    assert r["theme"] == "pochette" and r["profil"] == "salon" and r["nuit"] == "auto"
    assert r["nuit_debut"] == 22 and r["nuit_fin"] == 7 and r["protection"] is True


def test_reglages_depuis_le_formulaire():
    cfg = aff.reglages_depuis_formulaire({"ecran_theme": "console", "ecran_profil": "petit", "ecran_nuit": "jamais",
                                          "nuit_debut": "23", "nuit_fin": "6"})
    assert cfg == {"ecran_theme": "console", "ecran_profil": "petit", "ecran_nuit": "jamais", "nuit_debut": 23,
                   "nuit_fin": 6, "ecran_protection": False}


# ------------------------------------------------- cas limites (relecture)

def test_titres_de_ponctuation_ne_se_confondent_pas():
    file = {"start": 0, "array": [{"title": "(Intro)"}, {"title": "Suite", "artist": "X"}]}
    assert aff.suivant_dans_file(file, 0, "!!!") is None


def test_elements_de_file_et_listes_mal_formes():
    assert aff.suivant_dans_file({"array": ["x", {"title": "B"}]}, 0, "x") is None
    assert aff.sortie_active({"outputData": ["XLR"], "outputIndex": 0}) is None


def test_muet_inconnu_si_l_eversolo_ne_le_dit_pas():
    v = aff.lire_volume({"volumeData": {"currenttVolume": 10, "maxVolume": 100}})
    assert v["muet"] is None


def test_flac_sans_profondeur_reste_sans_perte():
    e = etat_avec(extension="FLAC", bits=0, sampleRateNumber=44100, bitrate="320 kbps")
    s = aff.signal_audio(e, "fr")
    assert s["classe"] != "perte" and s["debit"] is None


def test_debit_en_bits_par_seconde():
    e = etat_avec(extension="MP3", bits=0, sampleRateNumber=44100, bitrate=320000)
    assert aff.signal_audio(e, "fr")["debit"] == "320 kbps"


@pytest.mark.parametrize("code", [1, 2])
def test_etats_intermediaires_comptent_comme_arret(code):
    assert aff.etat_lecture({"state": code}) == "arret"
