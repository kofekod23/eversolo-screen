#!/usr/bin/env python3
"""Serveur eversolo-screen.

Interface "en lecture" pour streamers Eversolo (gamme DMP) avec page de configuration
protégée : mot de passe hache (scrypt), sessions signees, anti force brute,
jeton CSRF, proxy pochettes limite au streamer, en-tetes de sécurité.
"""

import glob
import ipaddress
import json
import re
import subprocess
import threading
import os
import secrets
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import unquote, urlparse

import requests
from flask import (Flask, Response, jsonify, redirect, render_template_string,
                   request, send_from_directory, session)
from markupsafe import Markup
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
AUTH_PATH = os.path.join(BASE_DIR, "auth.json")
SECRET_PATH = os.path.join(BASE_DIR, ".secret_key")

DEFAULTS = {
    "eversolo_ip": "",
    "eversolo_port": 9529,
    "listen_port": 8080,
    "language": "fr",
    "theaudiodb_key": "2",
    "lastfm_api_key": "",
}

LANGS = ("fr", "en", "es", "de")

# ---------------------------------------------------------------- traductions

T = {
    "fr": {
        "setup_title": "Première configuration",
        "setup_intro": "Choisissez un mot de passe administrateur et indiquez votre streamer.",
        "password": "Mot de passe administrateur",
        "password_confirm": "Confirmer le mot de passe",
        "password_short": "8 caractères minimum.",
        "password_mismatch": "Les deux mots de passe ne correspondent pas.",
        "device_ip": "Adresse IP du streamer",
        "detect": "Détecter sur le réseau",
        "detecting": "Recherche en cours...",
        "detect_none": "Aucun streamer trouvé. Saisissez l'IP manuellement.",
        "language": "Langue",
        "save": "Enregistrer",
        "login_title": "Connexion",
        "login": "Se connecter",
        "logout": "Se déconnecter",
        "bad_password": "Mot de passe incorrect.",
        "locked": "Trop de tentatives. Réessayez dans quelques minutes.",
        "config_title": "Configuration",
        "current_password": "Mot de passe actuel",
        "new_password": "Nouveau mot de passe (laisser vide pour conserver)",
        "saved": "Enregistré.",
        "back_display": "Retour a l'affichage",
        "invalid_ip": "Adresse IP invalide.",
        "blaster_title": "Émetteur infrarouge", "blaster_intro": "Enregistrez des touches de vos télécommandes, le Pi pourra les réémettre (TV, ampli...).", "new_name": "Nom de la commande (ex: tv_power)", "learn": "Apprendre", "send_cmd": "Envoyer", "delete_cmd": "Supprimer", "learn_hint": "Pressez maintenant la touche a apprendre, face àu capteur...", "learned": "Commande enregistrée.", "learn_failed": "Rien recu. Vérifiez le capteur et réessayez.", "no_tx": "Émetteur introuvable (option --ir-tx installee et redémarrage fait ?).", "bad_name": "Nom invalide: lettres, chiffres, tiret, 32 caractères max.", "blaster_link": "Émetteur infrarouge",
        "hw_title": "Matériel infrarouge", "hw_pin": "Broche du Raspberry", "hw_leg": "Patte du capteur", "hw_signal": "Signal (OUT / S)", "hw_gnd": "Masse (GND / -)", "hw_vcc": "Alimentation (VCC / +)", "hw_note": "Capteur VS1838B ou TSOP38238, face bombée vers vous, pattes en bas: OUT a gauche, GND au milieu, VCC a droite. Fiez-vous aux étiquettes si votre capteur est sur un module.", "hw_rx_ok": "Récepteur détecté", "hw_rx_ko": "Récepteur non détecté: vérifiez le câblage, puis ./install.sh --ir et un redémarrage.", "hw_tx_ok": "Émetteur détecté", "hw_tx_ko": "Émetteur non installe (optionnel).", "hw_test": "Tester le capteur", "hw_test_wait": "Pressez une touche...", "hw_test_ok": "Signal recu, capteur fonctionnel.", "hw_test_ko": "Aucun signal recu en 15 s.",
        "no_bio": "Aucune biographie trouvée pour cet artiste dans les sources consultées.",
        "tadb_key": "Clé TheAudioDB (repli biographies, clé d’essai par défaut)", "lastfm_key": "Clé API Last.fm (repli biographies, optionnelle)",
        "searching": "Recherche des informations sur l'artiste et le disque...",
        "remote_title": "Télécommande", "remote_intro": "Cliquez sur Associer puis pressez la touche voulue sur votre télécommande.", "pair": "Associer", "press_key": "Pressez une touche...", "clear": "Retirer", "not_paired": "Non associée", "act_play_pause": "Lecture / Pause", "act_next": "Suivant", "act_previous": "Précédent", "act_vol_up": "Volume +", "act_vol_down": "Volume -", "act_info": "Infos artiste", "act_mute": "Muet", "remote_link": "Télécommande infrarouge",
        "session_expired": "Session expirée, reconnectez-vous.",
    },
    "en": {
        "setup_title": "First-time setup",
        "setup_intro": "Choose an administrator password and point to your streamer.",
        "password": "Administrator password",
        "password_confirm": "Confirm password",
        "password_short": "8 characters minimum.",
        "password_mismatch": "Passwords do not match.",
        "device_ip": "Streamer IP address",
        "detect": "Detect on network",
        "detecting": "Scanning...",
        "detect_none": "No streamer found. Enter the IP manually.",
        "language": "Language",
        "save": "Save",
        "login_title": "Sign in",
        "login": "Sign in",
        "logout": "Sign out",
        "bad_password": "Incorrect password.",
        "locked": "Too many attempts. Try again in a few minutes.",
        "config_title": "Settings",
        "current_password": "Current password",
        "new_password": "New password (leave empty to keep)",
        "saved": "Saved.",
        "back_display": "Back to display",
        "invalid_ip": "Invalid IP address.",
        "blaster_title": "Infrared blaster", "blaster_intro": "Record buttons from your remotes, the Pi can replay them (TV, amp...).", "new_name": "Command name (e.g. tv_power)", "learn": "Learn", "send_cmd": "Send", "delete_cmd": "Delete", "learn_hint": "Now press the button to learn, facing the sensor...", "learned": "Command recorded.", "learn_failed": "Nothing received. Check the sensor and retry.", "no_tx": "Emitter not found (--ir-tx installed and rebooted?).", "bad_name": "Invalid name: letters, digits, dash, 32 chars max.", "blaster_link": "Infrared blaster",
        "hw_title": "Infrared hardware", "hw_pin": "Raspberry pin", "hw_leg": "Sensor leg", "hw_signal": "Signal (OUT / S)", "hw_gnd": "Ground (GND / -)", "hw_vcc": "Power (VCC / +)", "hw_note": "VS1838B or TSOP38238 sensor, dome facing you, legs down: OUT left, GND middle, VCC right. Trust the labels if your sensor is on a module.", "hw_rx_ok": "Receiver detected", "hw_rx_ko": "Receiver not detected: check wiring, then ./install.sh --ir and reboot.", "hw_tx_ok": "Emitter detected", "hw_tx_ko": "Emitter not installed (optional).", "hw_test": "Test the sensor", "hw_test_wait": "Press a button...", "hw_test_ok": "Signal received, sensor works.", "hw_test_ko": "No signal received within 15 s.",
        "no_bio": "No biography found for this artist in the available sources.",
        "tadb_key": "TheAudioDB key (biography fallback, test key by default)", "lastfm_key": "Last.fm API key (biography fallback, optional)",
        "searching": "Looking up artist and record information...",
        "remote_title": "Remote control", "remote_intro": "Click Pair then press the desired button on your remote.", "pair": "Pair", "press_key": "Press a button...", "clear": "Remove", "not_paired": "Not paired", "act_play_pause": "Play / Pause", "act_next": "Next", "act_previous": "Previous", "act_vol_up": "Volume +", "act_vol_down": "Volume -", "act_info": "Artist info", "act_mute": "Mute", "remote_link": "Infrared remote",
        "session_expired": "Session expired, sign in again.",
    },
    "es": {
        "setup_title": "Configuración inicial",
        "setup_intro": "Elija una contraseña de administrador e indique su streamer.",
        "password": "Contraseña de administrador",
        "password_confirm": "Confirmar contraseña",
        "password_short": "Minimo 8 caractères.",
        "password_mismatch": "Las contraseñas no coinciden.",
        "device_ip": "Dirección IP del streamer",
        "detect": "Detectar en la red",
        "detecting": "Buscando...",
        "detect_none": "No se encontro ningún streamer. Introduzca la IP manualmente.",
        "language": "Idioma",
        "save": "Guardar",
        "login_title": "Iniciar sesión",
        "login": "Iniciar sesión",
        "logout": "Cerrar sesión",
        "bad_password": "Contraseña incorrecta.",
        "locked": "Demasiados intentos. Vuelva a intentarlo en unos minutos.",
        "config_title": "Ajustes",
        "current_password": "Contraseña actual",
        "new_password": "Nueva contraseña (dejar vacio para conservar)",
        "saved": "Guardado.",
        "back_display": "Volver a la pantalla",
        "invalid_ip": "Dirección IP no valida.",
        "blaster_title": "Emisor infrarrojo", "blaster_intro": "Grabe teclas de sus mandos, la Pi podra reemitirlas (TV, ampli...).", "new_name": "Nombre del comando (ej: tv_power)", "learn": "Aprender", "send_cmd": "Enviar", "delete_cmd": "Eliminar", "learn_hint": "Pulse ahora la tecla a aprender, frente al sensor...", "learned": "Comando grabado.", "learn_failed": "No se recibió nada. Compruebe el sensor y reintente.", "no_tx": "Emisor no encontrado (opción --ir-tx instalada y reinicio hecho?).", "bad_name": "Nombre no valido: letras, cifras, guion, 32 caractères max.", "blaster_link": "Emisor infrarrojo",
        "hw_title": "Hardware infrarrojo", "hw_pin": "Pin de la Raspberry", "hw_leg": "Pata del sensor", "hw_signal": "Señal (OUT / S)", "hw_gnd": "Masa (GND / -)", "hw_vcc": "Alimentacion (VCC / +)", "hw_note": "Sensor VS1838B o TSOP38238, cupula hacia usted, patas abajo: OUT izquierda, GND centro, VCC derecha. Fiese de las etiquetas si el sensor esta en un modulo.", "hw_rx_ok": "Receptor detectado", "hw_rx_ko": "Receptor no detectado: revise el cableado, luego ./install.sh --ir y reinicie.", "hw_tx_ok": "Emisor detectado", "hw_tx_ko": "Emisor no instalado (opcional).", "hw_test": "Probar el sensor", "hw_test_wait": "Pulse una tecla...", "hw_test_ok": "Señal recibida, sensor operativo.", "hw_test_ko": "Ninguna señal en 15 s.",
        "no_bio": "No se encontró ninguna biografía de este artista en las fuentes consultadas.",
        "tadb_key": "Clave TheAudioDB (respaldo de biografías, clave de prueba por defecto)", "lastfm_key": "Clave API Last.fm (respaldo de biografías, opcional)",
        "searching": "Buscando información del artista y del disco...",
        "remote_title": "Mando a distancia", "remote_intro": "Pulse Asociar y luego la tecla deseada en su mando.", "pair": "Asociar", "press_key": "Pulse una tecla...", "clear": "Quitar", "not_paired": "Sin asociar", "act_play_pause": "Reproducir / Pausa", "act_next": "Siguiente", "act_previous": "Anterior", "act_vol_up": "Volumen +", "act_vol_down": "Volumen -", "act_info": "Info del artista", "act_mute": "Silencio", "remote_link": "Mando infrarrojo",
        "session_expired": "Sesión caducada, inicie sesión de nuevo.",
    },
    "de": {
        "setup_title": "Ersteinrichtung",
        "setup_intro": "Administrator-Passwort festlegen und Streamer angeben.",
        "password": "Administrator-Passwort",
        "password_confirm": "Passwort bestätigen",
        "password_short": "Mindestens 8 Zeichen.",
        "password_mismatch": "Die Passwörter stimmen nicht überein.",
        "device_ip": "IP-Adresse des Streamers",
        "detect": "Im Netzwerk suchen",
        "detecting": "Suche läuft...",
        "detect_none": "Kein Streamer gefunden. IP manuell eingeben.",
        "language": "Sprache",
        "save": "Speichern",
        "login_title": "Anmelden",
        "login": "Anmelden",
        "logout": "Abmelden",
        "bad_password": "Falsches Passwort.",
        "locked": "Zu viele Versuche. In einigen Minuten erneut versuchen.",
        "config_title": "Einstellungen",
        "current_password": "Aktuelles Passwort",
        "new_password": "Neues Passwort (leer lassen zum Beibehalten)",
        "saved": "Gespeichert.",
        "back_display": "Zurück zur Anzeige",
        "invalid_ip": "Ungültige IP-Adresse.",
        "blaster_title": "Infrarot-Sender", "blaster_intro": "Tasten Ihrer Fernbedienungen aufnehmen, der Pi kann sie wieder senden (TV, Verstärker...).", "new_name": "Name des Befehls (z.B. tv_power)", "learn": "Anlernen", "send_cmd": "Senden", "delete_cmd": "Löschen", "learn_hint": "Jetzt die Taste drücken, zum Sensor gerichtet...", "learned": "Befehl gespeichert.", "learn_failed": "Nichts empfangen. Sensor prüfen und erneut versuchen.", "no_tx": "Sender nicht gefunden (--ir-tx installiert und neu gestartet?).", "bad_name": "Ungültiger Name: Buchstaben, Ziffern, Bindestrich, max. 32 Zeichen.", "blaster_link": "Infrarot-Sender",
        "hw_title": "Infrarot-Hardware", "hw_pin": "Raspberry-Pin", "hw_leg": "Sensor-Bein", "hw_signal": "Signal (OUT / S)", "hw_gnd": "Masse (GND / -)", "hw_vcc": "Versorgung (VCC / +)", "hw_note": "Sensor VS1838B oder TSOP38238, Wölbung zu Ihnen, Beine nach unten: OUT links, GND Mitte, VCC rechts. Bei Modulen den Aufdrucken folgen.", "hw_rx_ok": "Empfänger erkannt", "hw_rx_ko": "Empfänger nicht erkannt: Verkabelung prüfen, dann ./install.sh --ir und Neustart.", "hw_tx_ok": "Sender erkannt", "hw_tx_ko": "Sender nicht installiert (optional).", "hw_test": "Sensor testen", "hw_test_wait": "Taste drücken...", "hw_test_ok": "Signal empfangen, Sensor funktioniert.", "hw_test_ko": "Kein Signal innerhalb von 15 s.",
        "no_bio": "Keine Biografie zu diesem Künstler in den verfügbaren Quellen gefunden.",
        "tadb_key": "TheAudioDB-Schlüssel (Biografie-Ausweichquelle, Testschlüssel als Standard)", "lastfm_key": "Last.fm-API-Schlüssel (Biografie-Ausweichquelle, optional)",
        "searching": "Informationen zu Künstler und Album werden gesucht...",
        "remote_title": "Fernbedienung", "remote_intro": "Auf Anlernen klicken und dann die gewünschte Taste drücken.", "pair": "Anlernen", "press_key": "Taste drücken...", "clear": "Entfernen", "not_paired": "Nicht angelernt", "act_play_pause": "Wiedergabe / Pause", "act_next": "Weiter", "act_previous": "Zurück", "act_vol_up": "Lauter", "act_vol_down": "Leiser", "act_info": "Künstler-Info", "act_mute": "Stumm", "remote_link": "Infrarot-Fernbedienung",
        "session_expired": "Sitzung abgelaufen, bitte erneut anmelden.",
    },
}

# ------------------------------------------------------------- configuration


def load_config():
    config = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config.update(json.load(f))
    except FileNotFoundError:
        pass
    return config


def save_config(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def load_auth():
    try:
        with open(AUTH_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def save_auth(password_hash):
    fd = os.open(AUTH_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"password_hash": password_hash}, f)


def get_secret_key():
    try:
        with open(SECRET_PATH, "rb") as f:
            key = f.read()
            if len(key) >= 32:
                return key
    except FileNotFoundError:
        pass
    key = secrets.token_bytes(32)
    fd = os.open(SECRET_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key)
    return key


CONFIG = load_config()

app = Flask(__name__, static_folder=os.path.join(BASE_DIR, "static"))
app.secret_key = get_secret_key()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    PERMANENT_SESSION_LIFETIME=12 * 3600,
    MAX_CONTENT_LENGTH=16 * 1024,
)

http = requests.Session()
http.headers.update({"User-Agent": "eversolo-screen/1.0 (Raspberry Pi; affichage hifi local)"})

MODEL_CACHE = {"ip": None, "name": ""}


def device_model(ip=None, port=None):
    """Nom du modèle (DMP-A6, A8, A10...), mis en cache par adresse."""
    ip = ip or CONFIG.get("eversolo_ip")
    port = port or CONFIG.get("eversolo_port", 9529)
    if not ip:
        return ""
    if MODEL_CACHE["ip"] == ip and MODEL_CACHE["name"]:
        return MODEL_CACHE["name"]
    try:
        r = http.get(f"http://{ip}:{port}/ControlCenter/getModel", timeout=2)
        name = r.json().get("model", "") if r.ok else ""
    except Exception:
        name = ""
    MODEL_CACHE.update({"ip": ip, "name": name})
    return name

# ------------------------------------------------------------ anti force brute

ACTIONS = {
    "play_pause": "/ZidooMusicControl/v2/playOrPause",
    "next": "/ZidooMusicControl/v2/playNext",
    "previous": "/ZidooMusicControl/v2/playLast",
    "vol_up": "/ZidooControlCenter/RemoteControl/sendkey?key=Key.VolumeUp",
    "vol_down": "/ZidooControlCenter/RemoteControl/sendkey?key=Key.VolumeDown",
}
MUTE_STATE = {"muted": False}
LAST_IR = {"code": None, "time": 0.0}


def do_action(action):
    """Envoie une commande de pilotage a l'Eversolo."""
    if not CONFIG.get("eversolo_ip"):
        return False
    if action in ("next", "previous") and ARTIST_PANEL["until"] > time.time():
        # volet ouvert: on tourne les pages au lieu de changer de plage
        ARTIST_PANEL["page"] = "album" if action == "next" else "artist"
        ARTIST_PANEL["scroll"] = 0
        ARTIST_PANEL["until"] = time.time() + 60
        return True
    if action in ("vol_up", "vol_down") and ARTIST_PANEL["until"] > time.time():
        # volet ouvert: les volumes defilent le texte au lieu d'agir sur le son
        delta = -1 if action == "vol_up" else 1
        ARTIST_PANEL["scroll"] = max(0, ARTIST_PANEL["scroll"] + delta)
        ARTIST_PANEL["until"] = time.time() + 60
        return True
    if action == "info":
        return toggle_artist_panel()
    if action == "mute":
        MUTE_STATE["muted"] = not MUTE_STATE["muted"]
        url = f"{eversolo_base()}/ZidooMusicControl/v2/setMuteVolume?isMute={1 if MUTE_STATE['muted'] else 0}"
    elif action in ACTIONS:
        url = f"{eversolo_base()}{ACTIONS[action]}"
    else:
        return False
    try:
        http.get(url, timeout=3)
        return True
    except Exception:
        return False


IR_CODES_DIR = os.path.join(BASE_DIR, "ir_codes")
NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def lirc_devices():
    """Detecte les peripheriques infrarouges: (récepteur, émetteur)."""
    rx = tx = None
    for dev in sorted(glob.glob("/dev/lirc*")):
        try:
            out = subprocess.run(
                ["ir-ctl", "-d", dev, "--features"],
                capture_output=True, text=True, timeout=5,
            ).stdout.lower()
        except Exception:
            continue
        if rx is None and "receive" in out:
            rx = dev
        if tx is None and "send" in out:
            tx = dev
    return rx, tx


def record_raw(path, timeout_s=15):
    """Enregistre une pression de touche en signal brut (tous protocoles)."""
    rx, _ = lirc_devices()
    if not rx:
        return False
    try:
        subprocess.run(
            ["ir-ctl", "-d", rx, "-1", "--receive=" + path],
            timeout=timeout_s, capture_output=True,
        )
    except subprocess.TimeoutExpired:
        pass
    return os.path.exists(path) and os.path.getsize(path) > 0


def send_raw(path):
    """Rejoue un signal enregistre via la LED émettrice."""
    _, tx = lirc_devices()
    if not tx or not os.path.exists(path):
        return False
    try:
        subprocess.run(["ir-ctl", "-d", tx, "--send=" + path], timeout=8)
        return True
    except Exception:
        return False


ARTIST_CACHE = {}
ARTIST_PANEL = {"until": 0.0, "data": None, "scroll": 0, "page": "artist"}


def _entetes_api():
    return {"User-Agent": "eversolo-screen/1.0 (affichage hifi local)"}


def _couper(texte, maxi=2600):
    texte = texte.strip()
    if len(texte) <= maxi:
        return texte
    coupe = texte[:maxi]
    point = coupe.rfind(". ")
    return coupe[:point + 1] if point > maxi // 2 else coupe


def musicbrainz_artist(artist, album=None):
    """Identité via MusicBrainz: faits (genre, période, pays), lien Wikidata,
    et nom canonique. Quand on connaît le disque, on identifie par le disque:
    c'est ce qui distingue deux artistes homonymes (Leon Thomas / Leon Thomas III).
    """
    try:
        a = None
        if album:
            try:
                r = http.get(
                    "https://musicbrainz.org/ws/2/release-group/",
                    params={"query": f'releasegroup:"{album}" AND artist:"{artist}"',
                            "fmt": "json", "limit": 1},
                    headers=_entetes_api(), timeout=4,
                )
                groups = r.json().get("release-groups") or []
                credit = (groups[0].get("artist-credit") or [{}])[0].get("artist") if groups else None
                if credit and credit.get("id"):
                    r2 = http.get(
                        f"https://musicbrainz.org/ws/2/artist/{credit['id']}",
                        params={"inc": "url-rels+tags", "fmt": "json"},
                        headers=_entetes_api(), timeout=4,
                    )
                    a = r2.json()
                    a.setdefault("id", credit["id"])
                    a["relations"] = a.get("relations") or []
                    a["_rels_incluses"] = True
            except Exception:
                a = None
        if a is None:
            r = http.get(
                "https://musicbrainz.org/ws/2/artist/",
                params={"query": f'artist:"{artist}"', "fmt": "json", "limit": 1},
                headers=_entetes_api(), timeout=4,
            )
            artists = r.json().get("artists") or []
            if not artists:
                return None
            a = artists[0]
        facts = []
        tags = sorted(a.get("tags") or [], key=lambda t: -t.get("count", 0))
        if tags:
            facts.append(tags[0]["name"].capitalize())
        span = a.get("life-span") or {}
        begin = (span.get("begin") or "")[:4]
        end_ = (span.get("end") or "")[:4]
        if begin:
            facts.append(f"{begin}–{end_}" if end_ else begin)
        area = (a.get("area") or {}).get("name") or a.get("country")
        if area:
            facts.append(area)
        qid = None
        try:
            rels = a.get("relations") if a.get("_rels_incluses") else None
            if rels is None:
                r2 = http.get(
                    f"https://musicbrainz.org/ws/2/artist/{a['id']}",
                    params={"inc": "url-rels", "fmt": "json"},
                    headers=_entetes_api(), timeout=4,
                )
                rels = r2.json().get("relations") or []
            for rel in rels:
                if rel.get("type") == "wikidata":
                    qid = rel.get("url", {}).get("resource", "").rstrip("/").rsplit("/", 1)[-1]
                    break
        except Exception:
            pass
        return {"facts": facts[:3], "qid": qid, "name": a.get("name")}
    except Exception:
        return None


def wikidata_titre(qid, lang):
    """Titre exact de l'article Wikipédia via Wikidata, repli anglais."""
    try:
        r = http.get(
            "https://www.wikidata.org/w/api.php",
            params={"action": "wbgetentities", "ids": qid, "props": "sitelinks",
                    "sitefilter": f"{lang}wiki|enwiki", "format": "json"},
            headers=_entetes_api(), timeout=4,
        )
        links = (r.json().get("entities", {}).get(qid) or {}).get("sitelinks", {})
        for site, wl in ((f"{lang}wiki", lang), ("enwiki", "en")):
            if site in links:
                return links[site]["title"], wl
    except Exception:
        pass
    return None, lang


def _wiki_resume(title, wl):
    r = http.get(
        f"https://{wl}.wikipedia.org/api/rest_v1/page/summary/"
        + requests.utils.quote(title, safe=""),
        headers=_entetes_api(), timeout=4,
    )
    return r.json()


def _wiki_intro(title, wl):
    r = http.get(
        f"https://{wl}.wikipedia.org/w/api.php",
        params={"action": "query", "prop": "extracts", "explaintext": 1,
                "exintro": 1, "redirects": 1, "format": "json", "titles": title},
        headers=_entetes_api(), timeout=5,
    )
    for p in (r.json().get("query", {}).get("pages", {}) or {}).values():
        return (p.get("extract") or "").strip()
    return ""


def _wiki_data(artist, title, wl, facts, via):
    j = _wiki_resume(title, wl)
    extract = (j.get("extract") or "").strip()
    try:
        longue = _wiki_intro(title, wl)
        if len(longue) > len(extract):
            extract = longue
    except Exception:
        pass
    extract = _couper(extract)
    if not extract:
        return None
    thumb = (j.get("thumbnail") or {}).get("source")
    return {
        "artist": artist, "text": extract,
        "image": "/api/cover?u=" + requests.utils.quote(thumb, safe="") if thumb else None,
        "facts": facts, "source": f"Wikipedia ({wl}){via}",
    }


MOTS_MUSIQUE = (
    "musi", "chant", "groupe", "band", "singer", "rapp", "composit", "composer",
    "dj", "produc", "guitar", "pian", "trompett", "saxo", "batteur", "drummer",
    "songwriter", "s\u00e4nger", "cantante", "grupo", "banda", "orchestr",
    "soprano", "tenor", "violon", "violin",
)


def _parle_de_musique(texte):
    texte = (texte or "").lower()
    return any(mot in texte for mot in MOTS_MUSIQUE)


def _wiki_recherche(artist, lang, facts):
    """Ancien chemin: recherche filtrée musique, quand Wikidata n'a pas aidé."""
    def chercher(query):
        r = http.get(
            f"https://{lang}.wikipedia.org/w/rest.php/v1/search/page",
            params={"q": query, "limit": 5}, headers=_entetes_api(), timeout=4,
        )
        return r.json().get("pages") or []

    try:
        title = None
        for tentative in (artist, f"{artist} musique groupe"):
            for page in chercher(tentative):
                if _parle_de_musique(page.get("description", "")):
                    title = page["title"]
                    break
            if title:
                break
        if not title:
            return None
        data = _wiki_data(artist, title, lang, facts, "")
        if data and not _parle_de_musique(data["text"]):
            return None
        return data
    except Exception:
        return None


def theaudiodb_bio(artist, lang, facts):
    key = (CONFIG.get("theaudiodb_key") or "2").strip()
    try:
        r = http.get(
            f"https://www.theaudiodb.com/api/v1/json/{key}/search.php",
            params={"s": artist}, headers=_entetes_api(), timeout=5,
        )
        artists = (r.json() or {}).get("artists") or []
        if not artists:
            return None
        a = artists[0]
        bio = (a.get(f"strBiography{lang.upper()}") or a.get("strBiographyEN") or "").strip()
        if len(bio) < 40:
            return None
        img = a.get("strArtistThumb") or a.get("strArtistFanart")
        return {
            "artist": artist, "text": _couper(bio),
            "image": "/api/cover?u=" + requests.utils.quote(img, safe="") if img else None,
            "facts": facts, "source": "TheAudioDB",
        }
    except Exception:
        return None


def lastfm_bio(artist, lang, facts):
    key = (CONFIG.get("lastfm_api_key") or "").strip()
    if not key:
        return None
    try:
        r = http.get(
            "https://ws.audioscrobbler.com/2.0/",
            params={"method": "artist.getinfo", "artist": artist, "api_key": key,
                    "format": "json", "lang": lang, "autocorrect": 1},
            headers=_entetes_api(), timeout=5,
        )
        a = (r.json() or {}).get("artist") or {}
        bio = ((a.get("bio") or {}).get("content") or "")
        bio = re.sub(r"<a href=[^>]*>.*$", "", bio, flags=re.S)
        bio = re.sub(r"<[^>]+>", "", bio).strip()
        if len(bio) < 40:
            return None
        return {"artist": artist, "text": _couper(bio), "image": None,
                "facts": facts, "source": "Last.fm"}
    except Exception:
        return None


ALBUM_CACHE = {}


ROLES_CREDITS = {
    "producer": {"fr": "Production", "en": "Producer", "es": "Producción", "de": "Produktion"},
    "engineer": {"fr": "Ingénieur du son", "en": "Engineer", "es": "Ingeniero de sonido", "de": "Toningenieur"},
    "mix": {"fr": "Mixage", "en": "Mixing", "es": "Mezcla", "de": "Mischung"},
    "mastering": {"fr": "Mastering", "en": "Mastering", "es": "Masterización", "de": "Mastering"},
    "recording": {"fr": "Prise de son", "en": "Recording", "es": "Grabación", "de": "Aufnahme"},
}


def _mb_release_details(rgid, lang):
    """Plages (titres, durées) et crédits (production, ingénieurs) d'un disque."""
    tracks, credits = [], []
    try:
        r = http.get(
            "https://musicbrainz.org/ws/2/release/",
            params={"release-group": rgid, "fmt": "json", "limit": 1},
            headers=_entetes_api(), timeout=4,
        )
        releases = r.json().get("releases") or []
        if not releases:
            return tracks, credits
        r2 = http.get(
            f"https://musicbrainz.org/ws/2/release/{releases[0]['id']}",
            params={"inc": "recordings+artist-rels", "fmt": "json"},
            headers=_entetes_api(), timeout=5,
        )
        j = r2.json()
        n = 0
        for media in j.get("media") or []:
            for t in media.get("tracks") or []:
                n += 1
                ms = t.get("length") or (t.get("recording") or {}).get("length")
                duree = f"{ms // 60000}:{(ms // 1000) % 60:02d}" if ms else ""
                tracks.append({"n": n, "title": t.get("title") or "", "dur": duree})
        vus = set()
        for rel in j.get("relations") or []:
            typ = rel.get("type")
            nom = (rel.get("artist") or {}).get("name")
            if nom and typ in ROLES_CREDITS and (typ, nom) not in vus:
                vus.add((typ, nom))
                role = ROLES_CREDITS[typ].get(lang, ROLES_CREDITS[typ]["en"])
                credits.append({"role": role, "name": nom})
        credits = credits[:8]
    except Exception:
        pass
    return tracks, credits


def fetch_album_info(artist, album, lang):
    """Description et faits du disque: identité MusicBrainz d'abord (nom
    canonique + année), puis TheAudioDB et Last.fm pour la description."""
    if not album:
        return None
    key = (artist.lower(), album.lower(), lang)
    cached = ALBUM_CACHE.get(key)
    if cached and time.time() - cached[0] < 86400:
        return cached[1]

    nom, annee, rgid = artist, None, None
    try:
        r = http.get(
            "https://musicbrainz.org/ws/2/release-group/",
            params={"query": f'releasegroup:"{album}" AND artist:"{artist}"',
                    "fmt": "json", "limit": 1},
            headers=_entetes_api(), timeout=4,
        )
        groups = r.json().get("release-groups") or []
        if groups:
            credit = (groups[0].get("artist-credit") or [{}])[0].get("artist") or {}
            nom = credit.get("name") or artist
            annee = (groups[0].get("first-release-date") or "")[:4] or None
            rgid = groups[0].get("id")
    except Exception:
        pass
    tracks, credits = _mb_release_details(rgid, lang) if rgid else ([], [])

    data = None
    try:
        k = (CONFIG.get("theaudiodb_key") or "2").strip()
        r = http.get(
            f"https://www.theaudiodb.com/api/v1/json/{k}/searchalbum.php",
            params={"s": nom, "a": album}, headers=_entetes_api(), timeout=5,
        )
        albums = (r.json() or {}).get("album") or []
        if albums:
            al = albums[0]
            desc = (al.get(f"strDescription{lang.upper()}") or al.get("strDescriptionEN") or "").strip()
            facts = []
            if al.get("intYearReleased"):
                facts.append(str(al["intYearReleased"]))
            if al.get("strLabel"):
                facts.append(al["strLabel"])
            if al.get("strGenre"):
                facts.append(al["strGenre"])
            if desc or facts:
                data = {"title": album, "facts": facts[:3],
                        "text": _couper(desc, 1200), "source": "TheAudioDB"}
    except Exception:
        pass

    if not data:
        cle = (CONFIG.get("lastfm_api_key") or "").strip()
        if cle:
            try:
                r = http.get(
                    "https://ws.audioscrobbler.com/2.0/",
                    params={"method": "album.getinfo", "artist": nom, "album": album,
                            "api_key": cle, "format": "json", "lang": lang, "autocorrect": 1},
                    headers=_entetes_api(), timeout=5,
                )
                al = (r.json() or {}).get("album") or {}
                texte = ((al.get("wiki") or {}).get("content") or "")
                texte = re.sub(r"<a href=[^>]*>.*$", "", texte, flags=re.S)
                texte = re.sub(r"<[^>]+>", "", texte).strip()
                if len(texte) > 40:
                    data = {"title": album, "facts": [], "text": _couper(texte, 1200),
                            "source": "Last.fm"}
            except Exception:
                pass

    if data and annee and annee not in data["facts"]:
        data["facts"] = ([annee] + [f for f in data["facts"] if f != annee])[:3]
        if data["source"] != "MusicBrainz":
            data["source"] += " · MusicBrainz"
    if not data and (annee or tracks or credits):
        data = {"title": album, "facts": [annee] if annee else [], "text": "",
                "source": "MusicBrainz"}
    if data:
        data["tracks"] = tracks
        data["credits"] = credits

    if len(ALBUM_CACHE) > 50:
        ALBUM_CACHE.clear()
    ALBUM_CACHE[key] = (time.time(), data)
    return data


def fetch_artist_info(artist, lang, album=None):
    """Chaîne de sources, spécialisées musique d'abord, identité levée par le disque."""
    key = (artist.lower(), (album or "").lower(), lang)
    cached = ARTIST_CACHE.get(key)
    if cached and time.time() - cached[0] < 86400:
        return cached[1]

    mb = musicbrainz_artist(artist, album)
    facts = mb["facts"] if mb else []
    nom = (mb or {}).get("name") or artist
    data = None

    # Sources specialisees musique en premier, Wikipedia en repli
    data = theaudiodb_bio(nom, lang, facts)
    if not data:
        data = lastfm_bio(nom, lang, facts)
    if not data and mb and mb.get("qid"):
        title, wl = wikidata_titre(mb["qid"], lang)
        if title:
            try:
                data = _wiki_data(nom, title, wl, facts, " · MusicBrainz")
            except Exception:
                data = None
    if not data:
        data = _wiki_recherche(nom, lang, facts)

    if len(ARTIST_CACHE) > 50:
        ARTIST_CACHE.clear()
    ARTIST_CACHE[key] = (time.time(), data)
    return data


def toggle_artist_panel():
    """Affiche la bio de l'artiste en cours, ou la masque si déjà visible."""
    if ARTIST_PANEL["until"] > time.time():
        ARTIST_PANEL.update({"until": 0.0, "data": None, "scroll": 0, "page": "artist"})
        return True
    try:
        r = http.get(f"{eversolo_base()}/ZidooMusicControl/v2/getState", timeout=3)
        etat = normalize(r.json())
        artist = etat.get("artist")
        album_titre = etat.get("album")
    except Exception:
        return False
    if not artist:
        return False
    lang = CONFIG.get("language", "fr")

    def assembler(bio, album_info):
        art = ({"name": bio["artist"], "text": bio["text"], "image": bio["image"],
                "facts": bio["facts"], "source": bio["source"]}
               if bio else
               {"name": artist, "text": T.get(lang, T["fr"])["no_bio"],
                "image": None, "facts": [], "source": ""})
        return {"artist": art, "album": album_info}, (60 if (bio or album_info) else 8)

    cle_art = (artist.lower(), (album_titre or "").lower(), lang)
    art_pret = cle_art in ARTIST_CACHE and time.time() - ARTIST_CACHE[cle_art][0] < 86400
    cle_alb = (artist.lower(), (album_titre or "").lower(), lang)
    alb_pret = (not album_titre) or (
        cle_alb in ALBUM_CACHE and time.time() - ALBUM_CACHE[cle_alb][0] < 86400)

    if art_pret and alb_pret:
        # tout est en cache (cas normal grace au prechargement): reponse immediate
        data, duree = assembler(fetch_artist_info(artist, lang, album_titre),
                                fetch_album_info(artist, album_titre, lang))
        ARTIST_PANEL.update({"until": time.time() + duree, "data": data,
                             "scroll": 0, "page": "artist"})
        return True

    # cache froid: panneau "recherche" immediat, completion en arriere-plan.
    # La touche ne doit JAMAIS attendre les sources externes.
    jeton = ARTIST_PANEL.get("token", 0) + 1
    ARTIST_PANEL.update({
        "until": time.time() + 25, "scroll": 0, "page": "artist", "token": jeton,
        "data": {"artist": {"name": artist, "text": T.get(lang, T["fr"])["searching"],
                            "image": None, "facts": [], "source": ""},
                 "album": None},
    })

    def completer():
        try:
            bio = fetch_artist_info(artist, lang, album_titre)
            album_info = fetch_album_info(artist, album_titre, lang)
        except Exception:
            bio, album_info = None, None
        if ARTIST_PANEL.get("token") == jeton and ARTIST_PANEL["until"] > time.time():
            data, duree = assembler(bio, album_info)
            ARTIST_PANEL.update({"until": time.time() + duree, "data": data})

    threading.Thread(target=completer, daemon=True).start()
    return True


FAILED = {}
MAX_ATTEMPTS = 5
LOCK_WINDOW = 15 * 60


def is_locked(ip):
    now = time.time()
    attempts = [t for t in FAILED.get(ip, []) if now - t < LOCK_WINDOW]
    FAILED[ip] = attempts
    return len(attempts) >= MAX_ATTEMPTS


def record_failure(ip):
    FAILED.setdefault(ip, []).append(time.time())


# ------------------------------------------------------------------- helpers


def tr():
    lang = CONFIG.get("language", "fr")
    return T.get(lang, T["fr"])


def eversolo_base():
    return f"http://{CONFIG['eversolo_ip']}:{CONFIG['eversolo_port']}"


def is_configured():
    return load_auth() is not None and CONFIG.get("eversolo_ip")


def logged_in():
    return session.get("auth") is True


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


def csrf_ok():
    token = session.get("csrf")
    sent = request.form.get("csrf", "")
    return token and sent and secrets.compare_digest(token, sent)


def valid_ip(value):
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; frame-ancestors 'none'"
    )
    return resp


# ------------------------------------------------------- détection du streamer


def probe(ip, port, timeout=0.4):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            pass
        r = requests.get(
            f"http://{ip}:{port}/ZidooMusicControl/v2/getState", timeout=1.5
        )
        if r.ok and isinstance(r.json(), dict):
            return {"ip": ip, "model": device_model(ip, port)}
    except Exception:
        pass
    return None


def local_subnet():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    finally:
        s.close()
    return ipaddress.ip_network(f"{local_ip}/24", strict=False)


def scan_network():
    port = int(CONFIG.get("eversolo_port", 9529))
    hosts = [str(h) for h in local_subnet().hosts()]
    found = []
    with ThreadPoolExecutor(max_workers=64) as pool:
        for result in pool.map(lambda ip: probe(ip, port), hosts):
            if result:
                found.append(result)
    return found


# ------------------------------------------------------------------ templates

PAGE = """
<!DOCTYPE html><html lang="{{ lang }}"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="google" content="notranslate">
<title>Eversolo · {{ title }}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,340..640&family=Archivo:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--chassis:#0d0b08;--panel:#16130e;--line:#2a251c;--ivory:#ece6d8;--muted:#918a79;--tube:#e8a33d}
*{margin:0;padding:0;box-sizing:border-box}
body{min-height:100vh;background:var(--chassis);color:var(--ivory);font-family:"Archivo",system-ui,sans-serif;display:grid;place-items:center;padding:24px}
.card{width:min(440px,100%);background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:36px 32px;box-shadow:0 30px 80px -30px rgba(0,0,0,.9)}
.brand{font-size:11px;font-weight:600;letter-spacing:.42em;text-transform:uppercase;color:var(--muted);display:flex;align-items:center;gap:12px;margin-bottom:26px}
.brand b{color:var(--ivory)}
.lamp{width:7px;height:7px;border-radius:50%;background:var(--tube);box-shadow:0 0 10px 2px rgba(232,163,61,.55)}
h1{font-family:"Fraunces",Georgia,serif;font-weight:560;font-size:27px;margin-bottom:8px}
.intro{color:var(--muted);font-size:14px;line-height:1.5;margin-bottom:26px}
label{display:block;font-size:11px;font-weight:500;letter-spacing:.2em;text-transform:uppercase;color:var(--muted);margin:18px 0 8px}
input,select{width:100%;background:var(--chassis);border:1px solid var(--line);border-radius:4px;color:var(--ivory);font-family:"IBM Plex Mono",monospace;font-size:15px;padding:12px 14px;outline:none}
input:focus,select:focus{border-color:var(--tube)}
button{width:100%;margin-top:26px;background:var(--tube);border:none;border-radius:4px;color:#1a1206;font-family:"Archivo";font-weight:600;font-size:15px;letter-spacing:.04em;padding:14px;cursor:pointer}
button:hover{filter:brightness(1.08)}
.ghost{background:transparent;border:1px solid var(--line);color:var(--muted);margin-top:12px;font-weight:500}
.msg{border-left:2px solid var(--tube);padding:10px 14px;font-size:13px;color:var(--ivory);background:rgba(232,163,61,.07);margin-bottom:18px;border-radius:0 4px 4px 0}
.msg.err{border-color:#c65a4a;background:rgba(198,90,74,.09)}
.row{display:flex;gap:10px}.row input{flex:1}
.row button{width:auto;margin-top:0;padding:0 16px;font-size:13px}
.foot{margin-top:24px;text-align:center}
.foot a{color:var(--muted);font-size:12px;letter-spacing:.08em;text-decoration:none;border-bottom:1px solid var(--line);padding-bottom:2px}
.foot a:hover{color:var(--ivory)}
</style></head><body>
<div class="card">
  <div class="brand"><span class="lamp"></span><span><b>Eversolo</b></span></div>
  {{ body }}
</div>
</body></html>
"""


def page(title, body, lang):
    return render_template_string(PAGE, title=title, body=Markup(body), lang=lang)


# --------------------------------------------------------------------- routes


@app.route("/")
def index():
    if not is_configured():
        return redirect("/setup")
    return send_from_directory(app.static_folder, "index.html")


@app.route("/setup", methods=["GET", "POST"])
def setup():
    if load_auth() is not None:
        return redirect("/config")
    lang = request.values.get("lang", CONFIG.get("language", "fr"))
    if lang not in LANGS:
        lang = "fr"
    t = T[lang]
    error = None

    if request.method == "POST":
        if not csrf_ok():
            error = "CSRF"
        else:
            pw = request.form.get("password", "")
            pw2 = request.form.get("password2", "")
            ip = request.form.get("device_ip", "").strip()
            if len(pw) < 8:
                error = t["password_short"]
            elif pw != pw2:
                error = t["password_mismatch"]
            elif not valid_ip(ip):
                error = t["invalid_ip"]
            else:
                save_auth(generate_password_hash(pw, method="scrypt"))
                CONFIG.update({"eversolo_ip": ip, "language": lang})
                save_config(CONFIG)
                session.clear()
                session["auth"] = True
                session.permanent = True
                return redirect("/")

    body = f"""
<h1>{t['setup_title']}</h1>
<p class="intro">{t['setup_intro']}</p>
{f'<div class="msg err">{error}</div>' if error else ''}
<form method="post" action="/setup?lang={lang}">
  <input type="hidden" name="csrf" value="{csrf_token()}">
  <label>{t['language']}</label>
  <select onchange="location='/setup?lang='+this.value">
    <option value="fr" {'selected' if lang=='fr' else ''}>Français</option>
    <option value="en" {'selected' if lang=='en' else ''}>English</option>
    <option value="es" {'selected' if lang=='es' else ''}>Español</option>
    <option value="de" {'selected' if lang=='de' else ''}>Deutsch</option>
  </select>
  <label>{t['password']}</label>
  <input type="password" name="password" minlength="8" required autocomplete="new-password">
  <label>{t['password_confirm']}</label>
  <input type="password" name="password2" minlength="8" required autocomplete="new-password">
  <label>{t['device_ip']}</label>
  <div class="row">
    <input type="text" name="device_ip" id="ip" placeholder="192.168.1.50" required>
    <button type="button" id="scan">{t['detect']}</button>
  </div>
  <button type="submit">{t['save']}</button>
</form>
<script>
document.getElementById('scan').onclick = async function() {{
  this.textContent = {json.dumps(t['detecting'])}; this.disabled = true;
  try {{
    const r = await fetch('/api/detect'); const d = await r.json();
    if (d.found && d.found.length) document.getElementById('ip').value = d.found[0].ip;
    else alert({json.dumps(t['detect_none'])});
  }} catch (e) {{ alert({json.dumps(t['detect_none'])}); }}
  this.textContent = {json.dumps(t['detect'])}; this.disabled = false;
}};
</script>
"""
    return page(t["setup_title"], body, lang)


@app.route("/login", methods=["GET", "POST"])
def login():
    if load_auth() is None:
        return redirect("/setup")
    t = tr()
    lang = CONFIG.get("language", "fr")
    ip = request.remote_addr or "?"
    error = None

    if request.method == "POST":
        if is_locked(ip):
            error = t["locked"]
        elif not csrf_ok():
            error = t["session_expired"]
        else:
            auth = load_auth()
            if check_password_hash(auth["password_hash"], request.form.get("password", "")):
                FAILED.pop(ip, None)
                session.clear()
                session["auth"] = True
                session.permanent = True
                return redirect("/config")
            record_failure(ip)
            error = t["locked"] if is_locked(ip) else t["bad_password"]

    body = f"""
<h1>{t['login_title']}</h1>
{f'<div class="msg err">{error}</div>' if error else ''}
<form method="post" action="/login">
  <input type="hidden" name="csrf" value="{csrf_token()}">
  <label>{t['password']}</label>
  <input type="password" name="password" required autofocus autocomplete="current-password">
  <button type="submit">{t['login']}</button>
</form>
<div class="foot"><a href="/">{t['back_display']}</a></div>
"""
    return page(t["login_title"], body, lang)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect("/")


@app.route("/config", methods=["GET", "POST"])
def config_page():
    if load_auth() is None:
        return redirect("/setup")
    if not logged_in():
        return redirect("/login")
    t = tr()
    lang = CONFIG.get("language", "fr")
    message = error = None

    if request.method == "POST":
        if not csrf_ok():
            error = t["session_expired"]
        else:
            ip = request.form.get("device_ip", "").strip()
            new_lang = request.form.get("language", lang)
            new_pw = request.form.get("new_password", "")
            cur_pw = request.form.get("current_password", "")
            if not valid_ip(ip):
                error = t["invalid_ip"]
            elif new_pw and len(new_pw) < 8:
                error = t["password_short"]
            elif new_pw and not check_password_hash(load_auth()["password_hash"], cur_pw):
                error = t["bad_password"]
            else:
                if new_pw:
                    save_auth(generate_password_hash(new_pw, method="scrypt"))
                CONFIG.update({
                    "eversolo_ip": ip,
                    "language": new_lang if new_lang in LANGS else lang,
                    "theaudiodb_key": request.form.get("tadb_key", "").strip() or "2",
                    "lastfm_api_key": request.form.get("lastfm_key", "").strip(),
                })
                save_config(CONFIG)
                t = tr()
                lang = CONFIG["language"]
                message = t["saved"]

    body = f"""
<h1>{t['config_title']}</h1>
{f'<div class="msg">{message}</div>' if message else ''}
{f'<div class="msg err">{error}</div>' if error else ''}
<form method="post" action="/config">
  <input type="hidden" name="csrf" value="{csrf_token()}">
  <label>{t['device_ip']}</label>
  <div class="row">
    <input type="text" name="device_ip" id="ip" value="{CONFIG['eversolo_ip']}" required>
    <button type="button" id="scan">{t['detect']}</button>
  </div>
  <label>{t['language']}</label>
  <select name="language">
    <option value="fr" {'selected' if lang=='fr' else ''}>Français</option>
    <option value="en" {'selected' if lang=='en' else ''}>English</option>
    <option value="es" {'selected' if lang=='es' else ''}>Español</option>
    <option value="de" {'selected' if lang=='de' else ''}>Deutsch</option>
  </select>
  <label>{t['tadb_key']}</label>
  <input type="text" name="tadb_key" value="{CONFIG.get('theaudiodb_key', '2')}" autocomplete="off">
  <label>{t['lastfm_key']}</label>
  <input type="text" name="lastfm_key" value="{CONFIG.get('lastfm_api_key', '')}" autocomplete="off">
  <label>{t['new_password']}</label>
  <input type="password" name="new_password" autocomplete="new-password">
  <label>{t['current_password']}</label>
  <input type="password" name="current_password" autocomplete="current-password">
  <button type="submit">{t['save']}</button>
</form>
<form method="post" action="/logout"><input type="hidden" name="csrf" value="{csrf_token()}"><button class="ghost">{t['logout']}</button></form>
<div class="foot"><a href="/remote">{t['remote_link']}</a> &nbsp;·&nbsp; <a href="/">{t['back_display']}</a></div>
<script>
document.getElementById('scan').onclick = async function() {{
  this.textContent = {json.dumps(t['detecting'])}; this.disabled = true;
  try {{
    const r = await fetch('/api/detect'); const d = await r.json();
    if (d.found && d.found.length) document.getElementById('ip').value = d.found[0].ip;
    else alert({json.dumps(t['detect_none'])});
  }} catch (e) {{ alert({json.dumps(t['detect_none'])}); }}
  this.textContent = {json.dumps(t['detect'])}; this.disabled = false;
}};
</script>
"""
    return page(t["config_title"], body, lang)


@app.route("/api/control/<action>", methods=["POST"])
def api_control(action):
    # Le pilotage sur le réseau local n'ajoute aucune exposition: l'Eversolo
    # lui-même accepte déjà ces commandes sans mot de passe sur le port 9529.
    # L'en-tete personnalise bloque les requetes forgees depuis un site web.
    if request.headers.get("X-Requested-With") != "eversolo":
        return jsonify({"error": "forbidden"}), 403
    if action not in ACTIONS and action not in ("mute", "info"):
        return jsonify({"error": "unknown action"}), 404
    return jsonify({"ok": do_action(action)})


@app.route("/internal/ir", methods=["POST"])
def internal_ir():
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return jsonify({"error": "forbidden"}), 403
    if request.headers.get("X-Requested-With") != "eversolo":
        return jsonify({"error": "forbidden"}), 403
    try:
        code = str(int(request.args.get("code", "")))
    except ValueError:
        return jsonify({"error": "bad code"}), 400
    LAST_IR.update({"code": code, "time": time.time()})
    action = (CONFIG.get("ir_map") or {}).get(code)
    if action:
        do_action(action)
    return jsonify({"ok": True, "action": action})


@app.route("/api/ir/last")
def api_ir_last():
    if not logged_in():
        return jsonify({"error": "unauthorized"}), 401
    if LAST_IR["code"] and time.time() - LAST_IR["time"] < 15:
        return jsonify({"code": LAST_IR["code"]})
    return jsonify({"code": None})


@app.route("/remote", methods=["GET", "POST"])
def remote_page():
    if load_auth() is None:
        return redirect("/setup")
    if not logged_in():
        return redirect("/login")
    t = tr()
    lang = CONFIG.get("language", "fr")
    message = error = None

    if request.method == "POST":
        if not csrf_ok():
            error = t["session_expired"]
        else:
            action = request.form.get("action", "")
            code = request.form.get("code", "").strip()
            ir_map = dict(CONFIG.get("ir_map") or {})
            if action == "__clear__":
                target = request.form.get("target", "")
                ir_map = {c: a for c, a in ir_map.items() if a != target}
                CONFIG["ir_map"] = ir_map
                save_config(CONFIG)
                message = t["saved"]
            elif code.isdigit() and (action in ACTIONS or action in ("mute", "info")):
                ir_map = {c: a for c, a in ir_map.items() if a != action}
                ir_map[code] = action
                CONFIG["ir_map"] = ir_map
                save_config(CONFIG)
                message = t["saved"]

    ir_map = CONFIG.get("ir_map") or {}
    by_action = {a: c for c, a in ir_map.items()}
    rows = []
    for act in ["play_pause", "next", "previous", "vol_up", "vol_down", "mute", "info"]:
        code = by_action.get(act)
        code_txt = f"code {code}" if code else t["not_paired"]
        rows.append(f"""
<div class="rrow">
  <div class="rname">{t['act_' + act]}<span class="rcode">{code_txt}</span></div>
  <div class="rbtns">
    <button type="button" class="pairbtn" data-action="{act}">{t['pair']}</button>
    <form method="post" style="margin:0">
      <input type="hidden" name="csrf" value="{csrf_token()}">
      <input type="hidden" name="action" value="__clear__">
      <input type="hidden" name="target" value="{act}">
      <button class="ghost" style="margin:0;width:auto;padding:10px 14px" {'disabled' if not code else ''}>{t['clear']}</button>
    </form>
  </div>
</div>""")

    body = f"""
<style>
.rrow{{display:flex;justify-content:space-between;align-items:center;gap:12px;border-bottom:1px solid var(--line);padding:14px 0}}
.rname{{font-size:15px}}
.rcode{{display:block;font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--muted);margin-top:4px}}
.rbtns{{display:flex;gap:8px;align-items:center}}
.pairbtn{{width:auto;margin:0;padding:10px 16px;font-size:13px}}
.hw{{margin-top:28px;padding-top:22px;border-top:1px solid var(--line)}}
.hwhead{{display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap}}
.hwtitle{{font-size:11px;font-weight:600;letter-spacing:.2em;text-transform:uppercase;color:var(--muted)}}
.dot{{width:7px;height:7px;border-radius:50%;background:var(--faint);flex:0 0 auto}}
.dot.ok{{background:var(--tube);box-shadow:0 0 8px 2px rgba(232,163,61,.5)}}
.dot.ko{{background:#c65a4a}}
.hwstat{{font-size:12px;color:var(--muted)}}
.hwtab{{width:100%;border-collapse:collapse;font-size:13px}}
.hwtab th{{text-align:left;font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--faint);font-weight:500;padding-bottom:8px}}
.hwtab td{{padding:7px 0;border-top:1px solid var(--line);font-family:"IBM Plex Mono",monospace;color:var(--ivory)}}
.hwtab td:last-child{{text-align:right;color:var(--tube)}}
.gp{{color:var(--muted);font-size:11px}}
.hwnote{{font-size:12px;line-height:1.5;color:var(--muted);margin-top:14px}}
.hwres{{margin-top:10px;font-family:"IBM Plex Mono",monospace;font-size:12px;color:var(--muted)}}
.hwres.ok{{color:var(--tube)}}
.hwres.ko{{color:#c65a4a}}
</style>
<h1>{t['remote_title']}</h1>
<p class="intro">{t['remote_intro']}</p>
{f'<div class="msg">{message}</div>' if message else ''}
{f'<div class="msg err">{error}</div>' if error else ''}
{''.join(rows)}
<form method="post" id="pairform" style="display:none">
  <input type="hidden" name="csrf" value="{csrf_token()}">
  <input type="hidden" name="action" id="pf_action">
  <input type="hidden" name="code" id="pf_code">
</form>
<div class="hw">
  <div class="hwhead">
    <span class="hwtitle">{t['hw_title']}</span>
    <span class="dot" id="rxdot"></span><span class="hwstat" id="rxstat">...</span>
  </div>
  <table class="hwtab">
    <tr><th>{t['hw_leg']}</th><th>{t['hw_pin']}</th></tr>
    <tr><td>{t['hw_signal']}</td><td>11 &nbsp;<span class="gp">GPIO17</span></td></tr>
    <tr><td>{t['hw_gnd']}</td><td>6</td></tr>
    <tr><td>{t['hw_vcc']}</td><td>1 &nbsp;<span class="gp">3,3 V</span></td></tr>
  </table>
  <p class="hwnote">{t['hw_note']}</p>
  <button type="button" class="ghost" id="testbtn" style="margin-top:14px">{t['hw_test']}</button>
  <div class="hwres" id="testres"></div>
</div>
<div class="foot"><a href="/blaster">{t['blaster_link']}</a> &nbsp;·&nbsp; <a href="/config">{t['config_title']}</a> &nbsp;·&nbsp; <a href="/">{t['back_display']}</a></div>
<script>
(async function() {{
  try {{
    const d = await (await fetch('/api/ir/status')).json();
    document.getElementById('rxdot').className = 'dot ' + (d.rx ? 'ok' : 'ko');
    document.getElementById('rxstat').textContent = d.rx
      ? {json.dumps(t['hw_rx_ok'])} : {json.dumps(t['hw_rx_ko'])};
  }} catch (e) {{}}
}})();
document.getElementById('testbtn').onclick = async function() {{
  const btn = this, res = document.getElementById('testres');
  const original = btn.textContent;
  btn.textContent = {json.dumps(t['hw_test_wait'])}; btn.disabled = true; res.textContent = '';
  let seen = null;
  try {{ seen = (await (await fetch('/api/ir/last')).json()).code; }} catch (e) {{}}
  const started = Date.now();
  while (Date.now() - started < 15000) {{
    await new Promise(r => setTimeout(r, 500));
    try {{
      const d = await (await fetch('/api/ir/last')).json();
      if (d.code && d.code !== seen) {{
        res.textContent = {json.dumps(t['hw_test_ok'])} + ' (code ' + d.code + ')';
        res.className = 'hwres ok';
        btn.textContent = original; btn.disabled = false;
        return;
      }}
    }} catch (e) {{}}
  }}
  res.textContent = {json.dumps(t['hw_test_ko'])}; res.className = 'hwres ko';
  btn.textContent = original; btn.disabled = false;
}};
document.querySelectorAll('.pairbtn').forEach(function(btn) {{
  btn.onclick = async function() {{
    const original = btn.textContent;
    btn.textContent = {json.dumps(t['press_key'])}; btn.disabled = true;
    const started = Date.now();
    let seen = null;
    try {{ const r0 = await fetch('/api/ir/last'); seen = (await r0.json()).code; }} catch (e) {{}}
    while (Date.now() - started < 20000) {{
      await new Promise(res => setTimeout(res, 500));
      try {{
        const r = await fetch('/api/ir/last');
        const d = await r.json();
        if (d.code && d.code !== seen) {{
          document.getElementById('pf_action').value = btn.dataset.action;
          document.getElementById('pf_code').value = d.code;
          document.getElementById('pairform').submit();
          return;
        }}
      }} catch (e) {{}}
    }}
    btn.textContent = original; btn.disabled = false;
  }};
}});
</script>
"""
    return page(t["remote_title"], body, lang)


@app.route("/api/blast/<name>", methods=["POST"])
def api_blast(name):
    if request.headers.get("X-Requested-With") != "eversolo":
        return jsonify({"error": "forbidden"}), 403
    if not NAME_RE.match(name):
        return jsonify({"error": "bad name"}), 400
    path = os.path.join(IR_CODES_DIR, name + ".ir")
    if not os.path.exists(path):
        return jsonify({"error": "unknown"}), 404
    return jsonify({"ok": send_raw(path)})


@app.route("/blaster", methods=["GET", "POST"])
def blaster_page():
    if load_auth() is None:
        return redirect("/setup")
    if not logged_in():
        return redirect("/login")
    t = tr()
    lang = CONFIG.get("language", "fr")
    message = error = None
    os.makedirs(IR_CODES_DIR, exist_ok=True)

    if request.method == "POST":
        if not csrf_ok():
            error = t["session_expired"]
        else:
            op = request.form.get("op", "")
            name = request.form.get("name", "").strip()
            if not NAME_RE.match(name):
                error = t["bad_name"]
            elif op == "learn":
                # capture synchrone: la page attend la pression de touche
                if record_raw(os.path.join(IR_CODES_DIR, name + ".ir")):
                    message = t["learned"]
                else:
                    error = t["learn_failed"]
            elif op == "delete":
                try:
                    os.remove(os.path.join(IR_CODES_DIR, name + ".ir"))
                    message = t["saved"]
                except FileNotFoundError:
                    pass

    _, tx = lirc_devices()
    warn = "" if tx else f'<div class="msg err">{t["no_tx"]}</div>'
    rows = []
    for f in sorted(glob.glob(os.path.join(IR_CODES_DIR, "*.ir"))):
        n = os.path.basename(f)[:-3]
        rows.append(f'''
<div class="rrow">
  <div class="rname">{n}</div>
  <div class="rbtns">
    <button type="button" class="pairbtn sendbtn" data-name="{n}">{t['send_cmd']}</button>
    <form method="post" style="margin:0">
      <input type="hidden" name="csrf" value="{csrf_token()}">
      <input type="hidden" name="op" value="delete">
      <input type="hidden" name="name" value="{n}">
      <button class="ghost" style="margin:0;width:auto;padding:10px 14px">{t['delete_cmd']}</button>
    </form>
  </div>
</div>''')

    body = f'''
<style>
.rrow{{display:flex;justify-content:space-between;align-items:center;gap:12px;border-bottom:1px solid var(--line);padding:14px 0}}
.rname{{font-family:"IBM Plex Mono",monospace;font-size:14px}}
.rbtns{{display:flex;gap:8px;align-items:center}}
.pairbtn{{width:auto;margin:0;padding:10px 16px;font-size:13px}}
</style>
<h1>{t['blaster_title']}</h1>
<p class="intro">{t['blaster_intro']}</p>
{warn}
{f'<div class="msg">{message}</div>' if message else ''}
{f'<div class="msg err">{error}</div>' if error else ''}
<form method="post" id="learnform">
  <input type="hidden" name="csrf" value="{csrf_token()}">
  <input type="hidden" name="op" value="learn">
  <label>{t['new_name']}</label>
  <div class="row">
    <input type="text" name="name" pattern="[A-Za-z0-9_-]{{1,32}}" required>
    <button type="submit" id="learnbtn">{t['learn']}</button>
  </div>
</form>
{''.join(rows)}
<div class="foot"><a href="/remote">{t['remote_title']}</a> &nbsp;·&nbsp; <a href="/config">{t['config_title']}</a></div>
<script>
document.getElementById('learnform').addEventListener('submit', function() {{
  const b = document.getElementById('learnbtn');
  b.textContent = {json.dumps(t['learn_hint'])}; b.disabled = false;
}});
document.querySelectorAll('.sendbtn').forEach(function(btn) {{
  btn.onclick = async function() {{
    btn.disabled = true;
    try {{
      await fetch('/api/blast/' + btn.dataset.name, {{
        method: 'POST', headers: {{'X-Requested-With': 'eversolo'}}
      }});
    }} catch (e) {{}}
    setTimeout(() => btn.disabled = false, 500);
  }};
}});
</script>
'''
    return page(t["blaster_title"], body, lang)


@app.route("/api/ir/status")
def api_ir_status():
    if not logged_in():
        return jsonify({"error": "unauthorized"}), 401
    rx, tx = lirc_devices()
    # Un peripherique /dev/lirc* n'existe que si l'overlay gpio-ir est actif:
    # c'est la seule preuve fiable que le récepteur est en place.
    lirc_present = bool(glob.glob("/dev/lirc*"))
    overlay = False
    for cfg in ("/boot/firmware/config.txt", "/boot/config.txt"):
        try:
            with open(cfg, encoding="utf-8", errors="ignore") as f:
                if any(l.strip().startswith("dtoverlay=gpio-ir") for l in f):
                    overlay = True
                    break
        except OSError:
            continue
    return jsonify({
        "rx": bool(rx) or (lirc_present and overlay),
        "tx": bool(tx),
        "overlay": overlay,
    })


@app.route("/api/detect")
def api_detect():
    # Autorise pendant la première configuration, puis reserve a l'admin.
    if load_auth() is not None and not logged_in():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify({"found": scan_network()})


# ----------------------------------------------------------- données lecture


def find_quality(state):
    found = {}
    wanted = {
        "sampleratenumber": "sample_rate", "samplerate": "sample_rate",
        "samplingrate": "sample_rate",
        "bitdepth": "bit_depth", "bits": "bit_depth",
        "bitrate": "bitrate",
        "audioformat": "format", "format": "format", "codec": "format",
    }

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                target = wanted.get(key.lower())
                if target and isinstance(value, (str, int, float)) and value not in ("", 0):
                    found.setdefault(target, value)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(state)

    # Les appareils renvoient parfois du texte ("44.1kHz", "24bit", "320 kbps"):
    # on extrait des valeurs numériques propres, sinon on ecarte le champ.
    def num(value):
        m = re.search(r"\d+(?:[.,]\d+)*", str(value))
        if not m:
            return None
        token = m.group(0)
        # "1,411" ou "44.100" sont des separateurs de milliers, pas des decimales
        if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", token):
            token = re.sub(r"[.,]", "", token)
        else:
            token = token.replace(",", ".")
        try:
            return float(token)
        except ValueError:
            return None

    cleaned = {}
    if "sample_rate" in found:
        v = num(found["sample_rate"])
        if v and v > 0:
            # valeur en kHz si petite, en Hz sinon; l'interface àttend des Hz
            cleaned["sample_rate"] = v * 1000 if v < 1000 else v
    if "bit_depth" in found:
        v = num(found["bit_depth"])
        if v and 8 <= v <= 64:
            cleaned["bit_depth"] = int(v)
    if "bitrate" in found:
        raw = str(found["bitrate"]).lower()
        if "mb" in raw:
            # exprime en megabits ("1,4 Mbps"): virgule decimale, x1000
            m = re.search(r"\d+(?:[.,]\d+)?", raw)
            v = float(m.group(0).replace(",", ".")) * 1000 if m else None
        else:
            v = num(found["bitrate"])
            if v and v > 10000:
                v = v / 1000
        if v and int(v) >= 32:
            cleaned["bitrate"] = int(v)
    if "format" in found:
        tokens = re.findall(r"[A-Za-z]{2,}", str(found["format"]))
        word = next((t for t in tokens if t.lower() not in
                     ("khz", "hz", "bit", "bits", "kbps", "bps")), None)
        if word:
            cleaned["format"] = word
    return cleaned


def absolute_url(path):
    if not path:
        return None
    if path.startswith("http"):
        return path
    return f"{eversolo_base()}{path}"


def normalize(state):
    play_type = state.get("playType")
    info = {
        "connected": True,
        "playing": int(state.get("state", -1)) == 3,
        "title": None, "artist": None, "album": None, "cover": None,
        "position": (state.get("position") or 0) / 1000,
        "duration": (state.get("duration") or 0) / 1000,
        "quality": find_quality(state),
        "lang": CONFIG.get("language", "fr"),
        "model": device_model(),
        "server_time": time.time(),
    }

    # Deux emplacements possibles selon la source:
    # - apps de streaming (Spotify Connect, AirPlay) et Bluetooth -> everSoloPlayInfo
    # - lecteur interne (Tidal, Qobuz, fichiers, web radios) -> playingMusic
    # Fusion avec repli croise pour rester robuste face àux playType inconnus.
    audio = state.get("everSoloPlayInfo", {}).get("everSoloPlayAudioInfo", {}) or {}
    music = state.get("playingMusic") or {}

    def pick(*values):
        for v in values:
            if isinstance(v, str) and v.strip():
                return v.strip()
        return None

    app_first = play_type in (4, 6)
    a_title = pick(audio.get("songName"), audio.get("title"), audio.get("name"))
    m_title = pick(music.get("title"), music.get("name"), music.get("songName"))
    info["title"] = pick(a_title, m_title) if app_first else pick(m_title, a_title)
    a_artist = pick(audio.get("artistName"), audio.get("artist"))
    m_artist = pick(music.get("artist"), music.get("artistName"))
    info["artist"] = pick(a_artist, m_artist) if app_first else pick(m_artist, a_artist)
    a_album = pick(audio.get("albumName"), audio.get("album"))
    m_album = pick(music.get("album"), music.get("albumName"))
    info["album"] = pick(a_album, m_album) if app_first else pick(m_album, a_album)

    icon = absolute_url(pick(state.get("everSoloPlayInfo", {}).get("icon")))
    art = absolute_url(pick(music.get("albumArt"), music.get("albumArtUrl"), music.get("icon")))
    by_id = None
    if music.get("id") is not None:
        by_id = f"{eversolo_base()}/ZidooMusicControl/v2/getImage?id={music['id']}&target=16"
    info["cover"] = (icon or art or by_id) if app_first else (art or by_id or icon)

    # Flux en direct (web radio): pas de durée exploitable
    info["live"] = bool(info["title"]) and info["duration"] <= 0

    if info["cover"]:
        info["cover"] = "/api/cover?u=" + requests.utils.quote(info["cover"], safe="")
    return info


STATE_CACHE = {"info": None, "failures": 0, "down_since": None}
PREFETCH = {"artist": None}


@app.route("/api/state")
def api_state():
    if not is_configured():
        return jsonify({"connected": False, "setup": True})
    try:
        r = http.get(f"{eversolo_base()}/ZidooMusicControl/v2/getState", timeout=3)
        r.raise_for_status()
        info = normalize(r.json())
        artiste = info.get("artist")
        cle_pf = (artiste, info.get("album"))
        if artiste and cle_pf != PREFETCH["artist"]:
            PREFETCH["artist"] = cle_pf
            def _precharge(a=artiste, al=info.get("album")):
                lg = CONFIG.get("language", "fr")
                fetch_artist_info(a, lg, al)
                fetch_album_info(a, al, lg)
            threading.Thread(target=_precharge, daemon=True).start()
        if STATE_CACHE["down_since"]:
            durée = int(time.time() - STATE_CACHE["down_since"])
            print(f"[diagnostic] Eversolo de retour après {durée} s d'indisponibilite", flush=True)
        STATE_CACHE.update({"info": info, "failures": 0, "down_since": None})
        if ARTIST_PANEL["until"] > time.time():
            info["panel"] = dict(ARTIST_PANEL["data"])
            info["panel"]["scroll"] = ARTIST_PANEL["scroll"]
            info["panel"]["page"] = ARTIST_PANEL["page"]
        return jsonify(info)
    except Exception:
        # Un rate isole (Wi-Fi, streamer occupe) ne doit pas faire clignoter
        # "introuvable": on ressert le dernier etat connu quelques secondes.
        STATE_CACHE["failures"] += 1
        if STATE_CACHE["failures"] == 3 and not STATE_CACHE["down_since"]:
            STATE_CACHE["down_since"] = time.time()
            print(f"[diagnostic] Eversolo injoignable ({CONFIG.get('eversolo_ip')})", flush=True)
        if STATE_CACHE["info"] and STATE_CACHE["failures"] < 3:
            stale = dict(STATE_CACHE["info"])
            stale["server_time"] = time.time()
            return jsonify(stale)
        return jsonify({
            "connected": False,
            "lang": CONFIG.get("language", "fr"),
            "server_time": time.time(),
        })


def host_is_private(hostname):
    """Vrai si l'hote resout vers une adresse privee, locale ou reservee."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except Exception:
        return True
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except ValueError:
            return True
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            return True
    return False


@app.route("/api/cover")
def api_cover():
    url = unquote(request.args.get("u", ""))
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return Response(status=403)
    streamer = {
        f"{CONFIG['eversolo_ip']}:{CONFIG['eversolo_port']}",
        CONFIG["eversolo_ip"],
    }
    # Anti SSRF: le streamer configure est toujours autorise; tout autre hote
    # doit être public (les pochettes Tidal/Qobuz/Spotify/radios viennent de
    # CDN externes) et repondre avec une image. Le réseau prive reste interdit.
    if parsed.netloc not in streamer and host_is_private(parsed.hostname):
        return Response(status=403)
    try:
        r = http.get(url, timeout=5)
        r.raise_for_status()
        ctype = r.headers.get("Content-Type", "image/jpeg")
        if parsed.netloc not in streamer and not ctype.lower().startswith("image/"):
            return Response(status=403)
        resp = Response(r.content, content_type=ctype)
        resp.headers["Cache-Control"] = "max-age=86400"
        return resp
    except Exception:
        return Response(status=502)


if __name__ == "__main__":
    from waitress import serve
    serve(app, host="0.0.0.0", port=CONFIG["listen_port"], threads=8)
