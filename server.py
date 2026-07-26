#!/usr/bin/env python3
"""Serveur eversolo-screen.

Interface "en lecture" pour streamers Eversolo (gamme DMP) avec page de configuration
protegee : mot de passe hache (scrypt), sessions signees, anti force brute,
jeton CSRF, proxy pochettes limite au streamer, en-tetes de securite.
"""

import glob
import ipaddress
import json
import re
import subprocess
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
}

LANGS = ("fr", "en", "es", "de")

# ---------------------------------------------------------------- traductions

T = {
    "fr": {
        "setup_title": "Premiere configuration",
        "setup_intro": "Choisissez un mot de passe administrateur et indiquez votre streamer.",
        "password": "Mot de passe administrateur",
        "password_confirm": "Confirmer le mot de passe",
        "password_short": "8 caracteres minimum.",
        "password_mismatch": "Les deux mots de passe ne correspondent pas.",
        "device_ip": "Adresse IP du streamer",
        "detect": "Detecter sur le reseau",
        "detecting": "Recherche en cours...",
        "detect_none": "Aucun streamer trouve. Saisissez l'IP manuellement.",
        "language": "Langue",
        "save": "Enregistrer",
        "login_title": "Connexion",
        "login": "Se connecter",
        "logout": "Se deconnecter",
        "bad_password": "Mot de passe incorrect.",
        "locked": "Trop de tentatives. Reessayez dans quelques minutes.",
        "config_title": "Configuration",
        "current_password": "Mot de passe actuel",
        "new_password": "Nouveau mot de passe (laisser vide pour conserver)",
        "saved": "Enregistre.",
        "back_display": "Retour a l'affichage",
        "invalid_ip": "Adresse IP invalide.",
        "blaster_title": "Emetteur infrarouge", "blaster_intro": "Enregistrez des touches de vos telecommandes, le Pi pourra les reemettre (TV, ampli...).", "new_name": "Nom de la commande (ex: tv_power)", "learn": "Apprendre", "send_cmd": "Envoyer", "delete_cmd": "Supprimer", "learn_hint": "Pressez maintenant la touche a apprendre, face au capteur...", "learned": "Commande enregistree.", "learn_failed": "Rien recu. Verifiez le capteur et reessayez.", "no_tx": "Emetteur introuvable (option --ir-tx installee et redemarrage fait ?).", "bad_name": "Nom invalide: lettres, chiffres, tiret, 32 caracteres max.", "blaster_link": "Emetteur infrarouge",
        "hw_title": "Materiel infrarouge", "hw_pin": "Broche du Raspberry", "hw_leg": "Patte du capteur", "hw_signal": "Signal (OUT / S)", "hw_gnd": "Masse (GND / -)", "hw_vcc": "Alimentation (VCC / +)", "hw_note": "Capteur VS1838B ou TSOP38238, face bombee vers vous, pattes en bas: OUT a gauche, GND au milieu, VCC a droite. Fiez-vous aux etiquettes si votre capteur est sur un module.", "hw_rx_ok": "Recepteur detecte", "hw_rx_ko": "Recepteur non detecte: verifiez le cablage, puis ./install.sh --ir et un redemarrage.", "hw_tx_ok": "Emetteur detecte", "hw_tx_ko": "Emetteur non installe (optionnel).", "hw_test": "Tester le capteur", "hw_test_wait": "Pressez une touche...", "hw_test_ok": "Signal recu, capteur fonctionnel.", "hw_test_ko": "Aucun signal recu en 15 s.",
        "remote_title": "Telecommande", "remote_intro": "Cliquez sur Associer puis pressez la touche voulue sur votre telecommande.", "pair": "Associer", "press_key": "Pressez une touche...", "clear": "Retirer", "not_paired": "Non associee", "act_play_pause": "Lecture / Pause", "act_next": "Suivant", "act_previous": "Precedent", "act_vol_up": "Volume +", "act_vol_down": "Volume -", "act_info": "Infos artiste", "act_mute": "Muet", "remote_link": "Telecommande infrarouge",
        "session_expired": "Session expiree, reconnectez-vous.",
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
        "remote_title": "Remote control", "remote_intro": "Click Pair then press the desired button on your remote.", "pair": "Pair", "press_key": "Press a button...", "clear": "Remove", "not_paired": "Not paired", "act_play_pause": "Play / Pause", "act_next": "Next", "act_previous": "Previous", "act_vol_up": "Volume +", "act_vol_down": "Volume -", "act_info": "Artist info", "act_mute": "Mute", "remote_link": "Infrared remote",
        "session_expired": "Session expired, sign in again.",
    },
    "es": {
        "setup_title": "Configuracion inicial",
        "setup_intro": "Elija una contrasena de administrador e indique su streamer.",
        "password": "Contrasena de administrador",
        "password_confirm": "Confirmar contrasena",
        "password_short": "Minimo 8 caracteres.",
        "password_mismatch": "Las contrasenas no coinciden.",
        "device_ip": "Direccion IP del streamer",
        "detect": "Detectar en la red",
        "detecting": "Buscando...",
        "detect_none": "No se encontro ningun streamer. Introduzca la IP manualmente.",
        "language": "Idioma",
        "save": "Guardar",
        "login_title": "Iniciar sesion",
        "login": "Iniciar sesion",
        "logout": "Cerrar sesion",
        "bad_password": "Contrasena incorrecta.",
        "locked": "Demasiados intentos. Vuelva a intentarlo en unos minutos.",
        "config_title": "Ajustes",
        "current_password": "Contrasena actual",
        "new_password": "Nueva contrasena (dejar vacio para conservar)",
        "saved": "Guardado.",
        "back_display": "Volver a la pantalla",
        "invalid_ip": "Direccion IP no valida.",
        "blaster_title": "Emisor infrarrojo", "blaster_intro": "Grabe teclas de sus mandos, la Pi podra reemitirlas (TV, ampli...).", "new_name": "Nombre del comando (ej: tv_power)", "learn": "Aprender", "send_cmd": "Enviar", "delete_cmd": "Eliminar", "learn_hint": "Pulse ahora la tecla a aprender, frente al sensor...", "learned": "Comando grabado.", "learn_failed": "No se recibio nada. Compruebe el sensor y reintente.", "no_tx": "Emisor no encontrado (opcion --ir-tx instalada y reinicio hecho?).", "bad_name": "Nombre no valido: letras, cifras, guion, 32 caracteres max.", "blaster_link": "Emisor infrarrojo",
        "hw_title": "Hardware infrarrojo", "hw_pin": "Pin de la Raspberry", "hw_leg": "Pata del sensor", "hw_signal": "Senal (OUT / S)", "hw_gnd": "Masa (GND / -)", "hw_vcc": "Alimentacion (VCC / +)", "hw_note": "Sensor VS1838B o TSOP38238, cupula hacia usted, patas abajo: OUT izquierda, GND centro, VCC derecha. Fiese de las etiquetas si el sensor esta en un modulo.", "hw_rx_ok": "Receptor detectado", "hw_rx_ko": "Receptor no detectado: revise el cableado, luego ./install.sh --ir y reinicie.", "hw_tx_ok": "Emisor detectado", "hw_tx_ko": "Emisor no instalado (opcional).", "hw_test": "Probar el sensor", "hw_test_wait": "Pulse una tecla...", "hw_test_ok": "Senal recibida, sensor operativo.", "hw_test_ko": "Ninguna senal en 15 s.",
        "remote_title": "Mando a distancia", "remote_intro": "Pulse Asociar y luego la tecla deseada en su mando.", "pair": "Asociar", "press_key": "Pulse una tecla...", "clear": "Quitar", "not_paired": "Sin asociar", "act_play_pause": "Reproducir / Pausa", "act_next": "Siguiente", "act_previous": "Anterior", "act_vol_up": "Volumen +", "act_vol_down": "Volumen -", "act_info": "Info del artista", "act_mute": "Silencio", "remote_link": "Mando infrarrojo",
        "session_expired": "Sesion caducada, inicie sesion de nuevo.",
    },
    "de": {
        "setup_title": "Ersteinrichtung",
        "setup_intro": "Administrator-Passwort festlegen und Streamer angeben.",
        "password": "Administrator-Passwort",
        "password_confirm": "Passwort bestaetigen",
        "password_short": "Mindestens 8 Zeichen.",
        "password_mismatch": "Die Passwoerter stimmen nicht ueberein.",
        "device_ip": "IP-Adresse des Streamers",
        "detect": "Im Netzwerk suchen",
        "detecting": "Suche laeuft...",
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
        "back_display": "Zurueck zur Anzeige",
        "invalid_ip": "Ungueltige IP-Adresse.",
        "blaster_title": "Infrarot-Sender", "blaster_intro": "Tasten Ihrer Fernbedienungen aufnehmen, der Pi kann sie wieder senden (TV, Verstaerker...).", "new_name": "Name des Befehls (z.B. tv_power)", "learn": "Anlernen", "send_cmd": "Senden", "delete_cmd": "Loeschen", "learn_hint": "Jetzt die Taste druecken, zum Sensor gerichtet...", "learned": "Befehl gespeichert.", "learn_failed": "Nichts empfangen. Sensor pruefen und erneut versuchen.", "no_tx": "Sender nicht gefunden (--ir-tx installiert und neu gestartet?).", "bad_name": "Ungueltiger Name: Buchstaben, Ziffern, Bindestrich, max. 32 Zeichen.", "blaster_link": "Infrarot-Sender",
        "hw_title": "Infrarot-Hardware", "hw_pin": "Raspberry-Pin", "hw_leg": "Sensor-Bein", "hw_signal": "Signal (OUT / S)", "hw_gnd": "Masse (GND / -)", "hw_vcc": "Versorgung (VCC / +)", "hw_note": "Sensor VS1838B oder TSOP38238, Woelbung zu Ihnen, Beine nach unten: OUT links, GND Mitte, VCC rechts. Bei Modulen den Aufdrucken folgen.", "hw_rx_ok": "Empfaenger erkannt", "hw_rx_ko": "Empfaenger nicht erkannt: Verkabelung pruefen, dann ./install.sh --ir und Neustart.", "hw_tx_ok": "Sender erkannt", "hw_tx_ko": "Sender nicht installiert (optional).", "hw_test": "Sensor testen", "hw_test_wait": "Taste druecken...", "hw_test_ok": "Signal empfangen, Sensor funktioniert.", "hw_test_ko": "Kein Signal innerhalb von 15 s.",
        "remote_title": "Fernbedienung", "remote_intro": "Auf Anlernen klicken und dann die gewuenschte Taste druecken.", "pair": "Anlernen", "press_key": "Taste druecken...", "clear": "Entfernen", "not_paired": "Nicht angelernt", "act_play_pause": "Wiedergabe / Pause", "act_next": "Weiter", "act_previous": "Zurueck", "act_vol_up": "Lauter", "act_vol_down": "Leiser", "act_info": "Kuenstler-Info", "act_mute": "Stumm", "remote_link": "Infrarot-Fernbedienung",
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

MODEL_CACHE = {"ip": None, "name": ""}


def device_model(ip=None, port=None):
    """Nom du modele (DMP-A6, A8, A10...), mis en cache par adresse."""
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
    """Detecte les peripheriques infrarouges: (recepteur, emetteur)."""
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
    """Rejoue un signal enregistre via la LED emettrice."""
    _, tx = lirc_devices()
    if not tx or not os.path.exists(path):
        return False
    try:
        subprocess.run(["ir-ctl", "-d", tx, "--send=" + path], timeout=8)
        return True
    except Exception:
        return False


ARTIST_CACHE = {}
ARTIST_PANEL = {"until": 0.0, "data": None}


def fetch_artist_info(artist, lang):
    """Bio et photo de l'artiste via Wikipedia, avec cache 24 h."""
    key = (artist.lower(), lang)
    cached = ARTIST_CACHE.get(key)
    if cached and time.time() - cached[0] < 86400:
        return cached[1]
    headers = {"User-Agent": "eversolo-screen/1.0 (affichage hifi local)"}
    data = None
    try:
        r = http.get(
            f"https://{lang}.wikipedia.org/w/rest.php/v1/search/page",
            params={"q": artist, "limit": 1}, headers=headers, timeout=4,
        )
        pages = r.json().get("pages") or []
        if pages:
            title = pages[0]["title"]
            r = http.get(
                f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/"
                + requests.utils.quote(title, safe=""),
                headers=headers, timeout=4,
            )
            j = r.json()
            extract = (j.get("extract") or "").strip()
            if extract:
                thumb = (j.get("thumbnail") or {}).get("source")
                data = {
                    "artist": artist,
                    "text": extract,
                    "image": "/api/cover?u=" + requests.utils.quote(thumb, safe="") if thumb else None,
                    "source": f"Wikipedia ({lang})",
                }
    except Exception:
        data = None
    if len(ARTIST_CACHE) > 50:
        ARTIST_CACHE.clear()
    ARTIST_CACHE[key] = (time.time(), data)
    return data


def toggle_artist_panel():
    """Affiche la bio de l'artiste en cours, ou la masque si deja visible."""
    if ARTIST_PANEL["until"] > time.time():
        ARTIST_PANEL.update({"until": 0.0, "data": None})
        return True
    try:
        r = http.get(f"{eversolo_base()}/ZidooMusicControl/v2/getState", timeout=3)
        artist = normalize(r.json()).get("artist")
    except Exception:
        return False
    if not artist:
        return False
    data = fetch_artist_info(artist, CONFIG.get("language", "fr"))
    if not data:
        return False
    ARTIST_PANEL.update({"until": time.time() + 45, "data": data})
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


# ------------------------------------------------------- detection du streamer


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
    <option value="fr" {'selected' if lang=='fr' else ''}>Francais</option>
    <option value="en" {'selected' if lang=='en' else ''}>English</option>
    <option value="es" {'selected' if lang=='es' else ''}>Espanol</option>
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
    <option value="fr" {'selected' if lang=='fr' else ''}>Francais</option>
    <option value="en" {'selected' if lang=='en' else ''}>English</option>
    <option value="es" {'selected' if lang=='es' else ''}>Espanol</option>
    <option value="de" {'selected' if lang=='de' else ''}>Deutsch</option>
  </select>
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
    # Le pilotage sur le reseau local n'ajoute aucune exposition: l'Eversolo
    # lui-meme accepte deja ces commandes sans mot de passe sur le port 9529.
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
    # c'est la seule preuve fiable que le recepteur est en place.
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
    # Autorise pendant la premiere configuration, puis reserve a l'admin.
    if load_auth() is not None and not logged_in():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify({"found": scan_network()})


# ----------------------------------------------------------- donnees lecture


def find_quality(state):
    found = {}
    wanted = {
        "samplerate": "sample_rate", "samplingrate": "sample_rate",
        "bitdepth": "bit_depth", "bitrate": "bitrate",
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
    # on extrait des valeurs numeriques propres, sinon on ecarte le champ.
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
            # valeur en kHz si petite, en Hz sinon; l'interface attend des Hz
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
    # Fusion avec repli croise pour rester robuste face aux playType inconnus.
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

    # Flux en direct (web radio): pas de duree exploitable
    info["live"] = bool(info["title"]) and info["duration"] <= 0

    if info["cover"]:
        info["cover"] = "/api/cover?u=" + requests.utils.quote(info["cover"], safe="")
    return info


STATE_CACHE = {"info": None, "failures": 0}


@app.route("/api/state")
def api_state():
    if not is_configured():
        return jsonify({"connected": False, "setup": True})
    try:
        r = http.get(f"{eversolo_base()}/ZidooMusicControl/v2/getState", timeout=3)
        r.raise_for_status()
        info = normalize(r.json())
        STATE_CACHE.update({"info": info, "failures": 0})
        if ARTIST_PANEL["until"] > time.time():
            info["panel"] = ARTIST_PANEL["data"]
        return jsonify(info)
    except Exception:
        # Un rate isole (Wi-Fi, streamer occupe) ne doit pas faire clignoter
        # "introuvable": on ressert le dernier etat connu quelques secondes.
        STATE_CACHE["failures"] += 1
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
    # doit etre public (les pochettes Tidal/Qobuz/Spotify/radios viennent de
    # CDN externes) et repondre avec une image. Le reseau prive reste interdit.
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
