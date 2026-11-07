"""Lecture de l'état de l'Eversolo pour l'écran : fonctions pures, sans réseau.

Champs relevés sur un DMP-A6 (micrologiciel 1.6.15) : `state` (0 arrêt,
3 lecture, 4 pause), `playingMusic` pour le lecteur interne (Tidal, Qobuz,
fichiers, radios), `everSoloPlayInfo` pour les applis externes (Spotify
Connect, Bluetooth, playType 4 et 6), `volumeData` pour le volume réel.
"""

import re

ETATS = {3: "lecture", 4: "pause"}

SOURCES = {
    "tidal": "Tidal", "qobuz": "Qobuz", "spotify": "Spotify", "deezer": "Deezer",
    "amazon": "Amazon Music", "amazonmusic": "Amazon Music", "apple": "Apple Music",
    "applemusic": "Apple Music", "highresaudio": "HighResAudio", "tunein": "TuneIn",
    "radioparadise": "Radio Paradise", "airable": "Airable", "soundcloud": "SoundCloud",
    "youtube": "YouTube Music", "neteasemusic": "NetEase", "netease": "NetEase",
}
FORMATS_AVEC_PERTE = {"MP3", "AAC", "OGG", "OPUS", "WMA", "M4A", "VORBIS"}
FORMATS_SANS_PERTE = {"FLAC", "ALAC", "WAV", "AIFF", "AIF", "APE", "WV", "PCM"}
FORMATS_DSD = {"DSF", "DFF", "DSD", "DST"}
# Multiples de 44,1 kHz : DSD64 = 2,8224 MHz.
DSD_BASE = 2_822_400
APPLIS_EXTERNES = (4, 6)

TEXTES = {
    "fr": {"album": "Album", "plage": "Plage", "sur": "sur", "artiste": "Artiste",
           "signal": "Signal", "ensuite": "Ensuite"},
    "en": {"album": "Album", "plage": "Track", "sur": "of", "artiste": "Artist",
           "signal": "Signal", "ensuite": "Up next"},
    "es": {"album": "Álbum", "plage": "Pista", "sur": "de", "artiste": "Artista",
           "signal": "Señal", "ensuite": "A continuación"},
    "de": {"album": "Album", "plage": "Titel", "sur": "von", "artiste": "Künstler",
           "signal": "Signal", "ensuite": "Als Nächstes"},
}

THEMES = ("pochette", "console", "affiche", "cadre")
PROFILS = ("salon", "bureau", "petit")
MODES_NUIT = ("auto", "jamais", "toujours")
REGLAGES_DEFAUT = {"theme": "pochette", "profil": "salon", "nuit": "auto", "nuit_debut": 22, "nuit_fin": 7,
                   "protection": True}
PHRASE_MAX = 180


def _textes(lang):
    return TEXTES.get(lang, TEXTES["fr"])


def _nombre(valeur):
    """Premier nombre d'un champ (« 1,44 Mbps », « 48 kHz », 24), ou None."""
    if isinstance(valeur, bool):
        return None
    if isinstance(valeur, (int, float)):
        return float(valeur)
    m = re.search(r"\d+(?:[.,]\d+)?", str(valeur or ""))
    return float(m.group(0).replace(",", ".")) if m else None


def _frequence_hz(nombre, texte):
    """Fréquence en Hz à partir du champ numérique, sinon du texte et de son unité."""
    n = _nombre(nombre)
    if n and n > 0:
        return n
    v = _nombre(texte)
    if not v:
        return None
    unite = str(texte).lower()
    if "mhz" in unite:
        return v * 1_000_000
    if "khz" in unite or v < 1000:
        return v * 1000
    return v


def _decimal(valeur, lang):
    texte = f"{valeur:.1f}".rstrip("0").rstrip(".")
    return texte if lang == "en" else texte.replace(".", ",")


def etat_lecture(etat):
    try:
        return ETATS.get(int(etat.get("state", -1)), "arret")
    except (TypeError, ValueError):
        return "arret"


def _bloc_lecture(etat):
    """Champs utiles du bloc qui décrit vraiment ce qui joue."""
    if etat.get("playType") in APPLIS_EXTERNES:
        info = ((etat.get("everSoloPlayInfo") or {}).get("everSoloPlayAudioInfo") or {})
        return {"source": None, "format": None,
                "hz": _nombre(info.get("audioSampleRate")), "hz_texte": None,
                "bits": _nombre(info.get("audioBitsPerSample")),
                "debit": _nombre(info.get("audioBitrate"))}
    m = etat.get("playingMusic") or {}
    debit = _nombre(m.get("bitrate"))
    if debit and "mb" in str(m.get("bitrate", "")).lower():
        debit *= 1000
    elif debit and debit > 10000:
        debit /= 1000  # exprimé en bit/s
    return {"source": m.get("streamId"), "format": m.get("extension"),
            "hz": _nombre(m.get("sampleRateNumber")), "hz_texte": m.get("sampleRate"),
            "bits": _nombre(m.get("bits")), "debit": debit}


def _nom_source(identifiant):
    cle = re.sub(r"[^a-z]", "", str(identifiant or "").lower())
    if not cle:
        return None
    return SOURCES.get(cle, str(identifiant).strip().capitalize())


def signal_audio(etat, lang):
    """Source, format et résolution lisibles ; débit seulement avec perte."""
    b = _bloc_lecture(etat or {})
    fmt = str(b["format"] or "").strip().upper() or None
    hz = _frequence_hz(b["hz"], b["hz_texte"])
    bits = int(b["bits"]) if b["bits"] and b["bits"] > 0 else None
    resultat = {"source": _nom_source(b["source"]), "format": fmt, "resolution": None,
                "classe": None, "debit": None}

    if (fmt in FORMATS_DSD) or (hz and hz >= 2_000_000):
        resultat["format"] = "DSD"
        resultat["classe"] = "dsd"
        if hz:
            resultat["format"] = f"DSD{64 * max(1, round(hz / DSD_BASE))}"
            resultat["resolution"] = f"{_decimal(hz / 1e6, lang)} MHz"
        return resultat

    khz = f"{_decimal(hz / 1000, lang)} kHz" if hz else None
    avec_perte = fmt in FORMATS_AVEC_PERTE
    if avec_perte or (fmt not in FORMATS_SANS_PERTE and not bits and b["debit"] and b["debit"] < 500):
        resultat["classe"] = "perte"
        resultat["resolution"] = khz
        if b["debit"]:
            resultat["debit"] = f"{int(b['debit'])} kbps"
        return resultat

    parties = [f"{bits} bit"] if bits else []
    if khz:
        parties.append(khz)
    resultat["resolution"] = " / ".join(parties) or None
    if (bits and bits >= 24) or (hz and hz > 48000):
        resultat["classe"] = "hires"
    elif bits == 16:
        resultat["classe"] = "cd"
    return resultat


def lire_volume(etat):
    """Volume réel (`volumeData`) : position 0-100, texte affiché, muet."""
    vd = (etat or {}).get("volumeData")
    if not isinstance(vd, dict):
        return None
    cur = _nombre(vd.get("currenttVolume", vd.get("currentVolume")))
    maxi = _nombre(vd.get("maxVolume"))
    mini = _nombre(vd.get("minVolume")) or 0.0
    if cur is None or maxi is None or maxi <= mini:
        return None
    pct = round(100 * min(max(cur - mini, 0), maxi - mini) / (maxi - mini))
    texte = str(vd.get("display") or "").strip() or str(int(cur))
    texte = re.sub(r"^-", "−", texte)
    muet = bool(vd["isMute"]) if "isMute" in vd else None
    return {"pct": pct, "texte": texte, "muet": muet}


def _element_actif(io, liste, index):
    if not isinstance(io, dict):
        return None
    elements = io.get(liste)
    i = io.get(index)
    if not isinstance(elements, list) or not isinstance(i, int) or not 0 <= i < len(elements):
        return None
    if not isinstance(elements[i], dict):
        return None
    nom = elements[i].get("name")
    return nom.strip() if isinstance(nom, str) and nom.strip() else None


def sortie_active(io):
    return _element_actif(io, "outputData", "outputIndex")


def entree_active(io):
    return _element_actif(io, "inputData", "inputIndex")


def _cle_titre(titre):
    """Titre comparable : sans casse, accents de ponctuation ni mention entre parenthèses."""
    t = re.sub(r"\s*[\(\[].*?[\)\]]", "", str(titre or "")).lower()
    t = re.sub(r"\s+-\s+.*(remaster|version|live|mix).*$", "", t)
    return re.sub(r"[^\w]+", " ", t).strip()


def place_dans_album(titre, pistes):
    cle = _cle_titre(titre)
    if not cle or not pistes:
        return None
    for i, p in enumerate(pistes):
        if _cle_titre(p.get("title")) == cle:
            return (i + 1, len(pistes))
    return None


def suivant_dans_file(file, index, titre):
    """Plage suivante, seulement si la file confirme bien la plage en cours."""
    elements = (file or {}).get("array")
    if not isinstance(elements, list) or not isinstance(index, int) or index < 0:
        return None
    rel = index - int((file or {}).get("start") or 0)
    if not 0 <= rel < len(elements) - 1:
        return None
    courant, suiv = elements[rel], elements[rel + 1]
    if not isinstance(courant, dict) or not isinstance(suiv, dict):
        return None
    cle = _cle_titre(titre)
    if not cle or _cle_titre(courant.get("title")) != cle:
        return None
    t = str(suiv.get("title") or "").strip()
    return {"title": t, "artist": str(suiv.get("artist") or "").strip()} if t else None


def _grouper(credits, maxi):
    groupes = {}
    for c in credits or []:
        role, nom = (c.get("role") or "").strip(), (c.get("name") or "").strip()
        if role and nom:
            noms = groupes.setdefault(role, [])
            for n in nom.split(", "):
                if n not in noms:
                    noms.append(n)
    return [{"k": r, "v": ", ".join(n[:4])} for r, n in list(groupes.items())[:maxi]]


def _premiere_phrase(texte):
    texte = re.sub(r"\s+", " ", str(texte or "")).strip()
    if not texte:
        return None
    m = re.search(r"^(.{30,}?[.!?])\s", texte + " ")
    phrase = m.group(1) if m else texte
    if len(phrase) <= PHRASE_MAX:
        return phrase
    coupe = phrase[:PHRASE_MAX].rsplit(" ", 1)[0].rstrip(" ,;:")
    return coupe + "…"


def decouvertes(titre, album, artiste, credits_plage, signal, sortie, lang):
    """Fiches courtes qui défilent sous le titre, du plus concret au plus large."""
    t = _textes(lang)
    fiches = []
    if album and album.get("facts"):
        fiches.append({"k": t["album"], "v": ", ".join(album["facts"][:3])})
    place = place_dans_album(titre, (album or {}).get("tracks"))
    if place:
        fiches.append({"k": t["plage"], "v": f"{place[0]} {t['sur']} {place[1]}"})
    fiches += _grouper(credits_plage, 2) or _grouper((album or {}).get("credits"), 2)
    if artiste:
        phrase = _premiere_phrase(artiste.get("text"))
        if phrase:
            fiches.append({"k": t["artiste"], "v": phrase})
        if artiste.get("facts") and artiste.get("name"):
            fiches.append({"k": artiste["name"], "v": ", ".join(artiste["facts"][:3])})
    if signal and (signal.get("source") or signal.get("resolution")):
        maillons = [signal.get("source"),
                    " ".join(x for x in (signal.get("format"), signal.get("resolution")) if x),
                    sortie]
        fiches.append({"k": t["signal"], "v": " → ".join(m for m in maillons if m)})
    return fiches


def _heure(valeur, defaut):
    if isinstance(valeur, bool):
        return defaut
    try:
        h = int(str(valeur).strip())
    except (TypeError, ValueError):
        return defaut
    return h if 0 <= h <= 23 else defaut


def reglages_affichage(config):
    """Réglages d'écran validés, prêts pour la page (jamais de valeur libre)."""
    d = REGLAGES_DEFAUT
    theme = config.get("ecran_theme")
    profil = config.get("ecran_profil")
    nuit = config.get("ecran_nuit")
    protection = config.get("ecran_protection", d["protection"])
    return {
        "theme": theme if theme in THEMES else d["theme"],
        "profil": profil if profil in PROFILS else d["profil"],
        "nuit": nuit if nuit in MODES_NUIT else d["nuit"],
        "nuit_debut": _heure(config.get("nuit_debut"), d["nuit_debut"]),
        "nuit_fin": _heure(config.get("nuit_fin"), d["nuit_fin"]),
        "protection": protection if isinstance(protection, bool) else d["protection"],
    }


def reglages_depuis_formulaire(form):
    """Clés de config.json à partir du formulaire /config (case absente = non)."""
    r = reglages_affichage({
        "ecran_theme": form.get("ecran_theme"),
        "ecran_profil": form.get("ecran_profil"), "ecran_nuit": form.get("ecran_nuit"),
        "nuit_debut": form.get("nuit_debut"), "nuit_fin": form.get("nuit_fin"),
        "ecran_protection": form.get("ecran_protection") == "1",
    })
    return {"ecran_theme": r["theme"], "ecran_profil": r["profil"], "ecran_nuit": r["nuit"],
            "nuit_debut": r["nuit_debut"], "nuit_fin": r["nuit_fin"],
            "ecran_protection": r["protection"]}
