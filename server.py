#!/usr/bin/env python3
"""Serveur eversolo-screen.

Interface "en lecture" pour Eversolo DMP-A6 avec page de configuration
protegee : mot de passe hache (scrypt), sessions signees, anti force brute,
jeton CSRF, proxy pochettes limite au streamer, en-tetes de securite.
"""

import ipaddress
import json
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
        "device_ip": "Adresse IP du DMP-A6",
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
        "session_expired": "Session expiree, reconnectez-vous.",
    },
    "en": {
        "setup_title": "First-time setup",
        "setup_intro": "Choose an administrator password and point to your streamer.",
        "password": "Administrator password",
        "password_confirm": "Confirm password",
        "password_short": "8 characters minimum.",
        "password_mismatch": "Passwords do not match.",
        "device_ip": "DMP-A6 IP address",
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
        "session_expired": "Session expired, sign in again.",
    },
    "es": {
        "setup_title": "Configuracion inicial",
        "setup_intro": "Elija una contrasena de administrador e indique su streamer.",
        "password": "Contrasena de administrador",
        "password_confirm": "Confirmar contrasena",
        "password_short": "Minimo 8 caracteres.",
        "password_mismatch": "Las contrasenas no coinciden.",
        "device_ip": "Direccion IP del DMP-A6",
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
        "session_expired": "Sesion caducada, inicie sesion de nuevo.",
    },
    "de": {
        "setup_title": "Ersteinrichtung",
        "setup_intro": "Administrator-Passwort festlegen und Streamer angeben.",
        "password": "Administrator-Passwort",
        "password_confirm": "Passwort bestaetigen",
        "password_short": "Mindestens 8 Zeichen.",
        "password_mismatch": "Die Passwoerter stimmen nicht ueberein.",
        "device_ip": "IP-Adresse des DMP-A6",
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

# ------------------------------------------------------------ anti force brute

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
            return ip
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
  <div class="brand"><span class="lamp"></span><span><b>Eversolo</b>&ensp;DMP-A6</span></div>
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
    if (d.found && d.found.length) document.getElementById('ip').value = d.found[0];
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
<div class="foot"><a href="/">{t['back_display']}</a></div>
<script>
document.getElementById('scan').onclick = async function() {{
  this.textContent = {json.dumps(t['detecting'])}; this.disabled = true;
  try {{
    const r = await fetch('/api/detect'); const d = await r.json();
    if (d.found && d.found.length) document.getElementById('ip').value = d.found[0];
    else alert({json.dumps(t['detect_none'])});
  }} catch (e) {{ alert({json.dumps(t['detect_none'])}); }}
  this.textContent = {json.dumps(t['detect'])}; this.disabled = false;
}};
</script>
"""
    return page(t["config_title"], body, lang)


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
    return found


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
        "server_time": time.time(),
    }

    if play_type in (4, 6):
        audio = state.get("everSoloPlayInfo", {}).get("everSoloPlayAudioInfo", {})
        info["title"] = audio.get("songName")
        info["artist"] = audio.get("artistName")
        info["album"] = audio.get("albumName")
        info["cover"] = absolute_url(state.get("everSoloPlayInfo", {}).get("icon"))
    else:
        music = state.get("playingMusic") or {}
        info["title"] = music.get("title")
        info["artist"] = music.get("artist")
        info["album"] = music.get("album")
        cover = music.get("albumArt")
        if cover:
            info["cover"] = absolute_url(cover)
        elif music.get("id") is not None:
            info["cover"] = (
                f"{eversolo_base()}/ZidooMusicControl/v2/getImage?id={music['id']}&target=16"
            )

    if info["cover"]:
        info["cover"] = "/api/cover?u=" + requests.utils.quote(info["cover"], safe="")
    return info


@app.route("/api/state")
def api_state():
    if not is_configured():
        return jsonify({"connected": False, "setup": True})
    try:
        r = http.get(f"{eversolo_base()}/ZidooMusicControl/v2/getState", timeout=3)
        r.raise_for_status()
        return jsonify(normalize(r.json()))
    except Exception:
        return jsonify({
            "connected": False,
            "lang": CONFIG.get("language", "fr"),
            "server_time": time.time(),
        })


@app.route("/api/cover")
def api_cover():
    url = unquote(request.args.get("u", ""))
    parsed = urlparse(url)
    allowed = {
        f"{CONFIG['eversolo_ip']}:{CONFIG['eversolo_port']}",
        CONFIG["eversolo_ip"],
    }
    # Le proxy ne sert que des images venant du streamer configure (anti SSRF).
    if parsed.scheme not in ("http", "https") or parsed.netloc not in allowed:
        return Response(status=403)
    try:
        r = http.get(url, timeout=5)
        r.raise_for_status()
        resp = Response(r.content, content_type=r.headers.get("Content-Type", "image/jpeg"))
        resp.headers["Cache-Control"] = "max-age=86400"
        return resp
    except Exception:
        return Response(status=502)


if __name__ == "__main__":
    from waitress import serve
    serve(app, host="0.0.0.0", port=CONFIG["listen_port"], threads=8)
