#!/usr/bin/env python3
"""Serveur eversolo-screen.

Interroge l'API HTTP du DMP-A6 (port 9529), normalise les donnees de lecture
et sert l'interface web. Fait aussi office de proxy pour les pochettes afin
d'eviter les soucis de CORS dans le navigateur.
"""

import json
import os
import time
from urllib.parse import unquote

import requests
from flask import Flask, Response, jsonify, request, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

DEFAULTS = {
    "eversolo_ip": "192.168.1.50",
    "eversolo_port": 9529,
    "listen_port": 8080,
}


def load_config():
    config = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config.update(json.load(f))
    except FileNotFoundError:
        pass
    return config


CONFIG = load_config()
EVERSOLO_BASE = f"http://{CONFIG['eversolo_ip']}:{CONFIG['eversolo_port']}"

app = Flask(__name__, static_folder=os.path.join(BASE_DIR, "static"))
session = requests.Session()


def absolute_url(path):
    if not path:
        return None
    if path.startswith("http"):
        return path
    return f"{EVERSOLO_BASE}{path}"


def find_quality(state):
    """Cherche des infos de qualite de flux dans le JSON brut, si presentes."""
    found = {}
    wanted = {
        "samplerate": "sample_rate",
        "samplingrate": "sample_rate",
        "bitdepth": "bit_depth",
        "bitrate": "bitrate",
        "audioformat": "format",
        "format": "format",
        "codec": "format",
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


def normalize(state):
    play_type = state.get("playType")
    info = {
        "connected": True,
        "playing": int(state.get("state", -1)) == 3,
        "title": None,
        "artist": None,
        "album": None,
        "cover": None,
        "position": (state.get("position") or 0) / 1000,
        "duration": (state.get("duration") or 0) / 1000,
        "quality": find_quality(state),
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
                f"{EVERSOLO_BASE}/ZidooMusicControl/v2/getImage?id={music['id']}&target=16"
            )

    if info["cover"]:
        info["cover"] = "/api/cover?u=" + requests.utils.quote(info["cover"], safe="")

    return info


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/state")
def api_state():
    try:
        r = session.get(f"{EVERSOLO_BASE}/ZidooMusicControl/v2/getState", timeout=3)
        r.raise_for_status()
        return jsonify(normalize(r.json()))
    except Exception:
        return jsonify({"connected": False, "server_time": time.time()})


@app.route("/api/cover")
def api_cover():
    url = unquote(request.args.get("u", ""))
    if not url.startswith(("http://", "https://")):
        return Response(status=400)
    try:
        r = session.get(url, timeout=5)
        r.raise_for_status()
        content_type = r.headers.get("Content-Type", "image/jpeg")
        resp = Response(r.content, content_type=content_type)
        resp.headers["Cache-Control"] = "max-age=86400"
        return resp
    except Exception:
        return Response(status=502)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=CONFIG["listen_port"], threaded=True)
