#!/usr/bin/env python3
"""Affichage plein ecran des informations de lecture d'un Eversolo DMP-A6.

Interroge l'API HTTP du streamer (port 9529) et affiche pochette, titre,
artiste, album et barre de progression sur l'ecran HDMI du Raspberry Pi.
"""

import io
import json
import os
import sys
import time

import pygame
import requests

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULTS = {
    "eversolo_ip": "192.168.1.50",
    "eversolo_port": 9529,
    "poll_interval": 1.0,
    "fullscreen": True,
    "background": [10, 10, 14],
}


def load_config():
    config = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config.update(json.load(f))
    except FileNotFoundError:
        print(f"config.json introuvable, valeurs par defaut utilisees ({CONFIG_PATH})")
    return config


class EversoloClient:
    """Client minimal pour l'API non officielle du DMP-A6."""

    def __init__(self, host, port=9529, timeout=3):
        self.base = f"http://{host}:{port}"
        self.timeout = timeout
        self.session = requests.Session()

    def get_state(self):
        r = self.session.get(
            f"{self.base}/ZidooMusicControl/v2/getState", timeout=self.timeout
        )
        r.raise_for_status()
        return r.json()

    def image_url_by_song_id(self, song_id):
        return f"{self.base}/ZidooMusicControl/v2/getImage?id={song_id}&target=16"

    def absolute_url(self, path):
        if path.startswith("http"):
            return path
        return f"{self.base}{path}"

    def fetch_image(self, url):
        r = self.session.get(url, timeout=self.timeout)
        r.raise_for_status()
        return r.content


def parse_now_playing(state, client):
    """Normalise le JSON getState en un dict simple.

    playType 4 = Bluetooth, 6 = apps de streaming (Spotify Connect, etc.),
    5 = lecteur interne (fichiers locaux, Tidal/Qobuz integres).
    """
    play_type = state.get("playType")
    info = {
        "playing": int(state.get("state", -1)) == 3,
        "title": None,
        "artist": None,
        "album": None,
        "cover_url": None,
        "position": (state.get("position") or 0) / 1000,
        "duration": (state.get("duration") or 0) / 1000,
    }

    if play_type in (4, 6):
        audio = state.get("everSoloPlayInfo", {}).get("everSoloPlayAudioInfo", {})
        info["title"] = audio.get("songName")
        info["artist"] = audio.get("artistName")
        info["album"] = audio.get("albumName")
        icon = state.get("everSoloPlayInfo", {}).get("icon")
        if icon:
            info["cover_url"] = client.absolute_url(icon)
    else:
        music = state.get("playingMusic") or {}
        info["title"] = music.get("title")
        info["artist"] = music.get("artist")
        info["album"] = music.get("album")
        cover = music.get("albumArt")
        if cover:
            info["cover_url"] = client.absolute_url(cover)
        elif music.get("id") is not None:
            info["cover_url"] = client.image_url_by_song_id(music["id"])

    return info


class Display:
    def __init__(self, config):
        pygame.init()
        pygame.mouse.set_visible(False)
        flags = pygame.FULLSCREEN if config["fullscreen"] else 0
        self.screen = pygame.display.set_mode((0, 0) if config["fullscreen"] else (1024, 600), flags)
        pygame.display.set_caption("Eversolo Screen")
        self.w, self.h = self.screen.get_size()
        self.bg = tuple(config["background"])

        base = max(self.h // 18, 16)
        self.font_title = pygame.font.SysFont("dejavusans", int(base * 1.6), bold=True)
        self.font_artist = pygame.font.SysFont("dejavusans", int(base * 1.1))
        self.font_album = pygame.font.SysFont("dejavusans", base)
        self.font_time = pygame.font.SysFont("dejavusans", int(base * 0.8))

        self.cover_surface = None
        self.cover_key = None

    def update_cover(self, cover_url, client):
        if cover_url == self.cover_key:
            return
        self.cover_key = cover_url
        self.cover_surface = None
        if not cover_url:
            return
        try:
            data = client.fetch_image(cover_url)
            img = pygame.image.load(io.BytesIO(data))
            size = int(self.h * 0.7)
            self.cover_surface = pygame.transform.smoothscale(img, (size, size))
        except Exception as exc:
            print(f"Pochette non chargee: {exc}")

    def _truncate(self, font, text, max_width):
        if font.size(text)[0] <= max_width:
            return text
        while text and font.size(text + "...")[0] > max_width:
            text = text[:-1]
        return text + "..."

    def draw(self, info):
        self.screen.fill(self.bg)
        margin = int(self.h * 0.08)
        cover_size = int(self.h * 0.7)

        if self.cover_surface:
            self.screen.blit(self.cover_surface, (margin, margin))
        else:
            rect = pygame.Rect(margin, margin, cover_size, cover_size)
            pygame.draw.rect(self.screen, (30, 30, 38), rect, border_radius=12)

        text_x = margin + cover_size + margin
        text_w = self.w - text_x - margin
        y = margin + int(cover_size * 0.15)

        lines = [
            (self.font_title, info.get("title") or "Aucune lecture", (240, 240, 240)),
            (self.font_artist, info.get("artist") or "", (200, 200, 205)),
            (self.font_album, info.get("album") or "", (150, 150, 158)),
        ]
        for font, text, color in lines:
            if text:
                surf = font.render(self._truncate(font, text, text_w), True, color)
                self.screen.blit(surf, (text_x, y))
                y += int(surf.get_height() * 1.35)

        self._draw_progress(info, margin)
        pygame.display.flip()

    def _draw_progress(self, info, margin):
        duration = info.get("duration") or 0
        position = min(info.get("position") or 0, duration)
        bar_y = self.h - margin - int(self.h * 0.02)
        bar_h = max(int(self.h * 0.012), 6)
        bar_w = self.w - 2 * margin

        pygame.draw.rect(
            self.screen, (50, 50, 60), (margin, bar_y, bar_w, bar_h), border_radius=bar_h
        )
        if duration > 0:
            filled = int(bar_w * position / duration)
            pygame.draw.rect(
                self.screen, (90, 170, 255), (margin, bar_y, filled, bar_h), border_radius=bar_h
            )

        def fmt(seconds):
            seconds = int(seconds)
            return f"{seconds // 60}:{seconds % 60:02d}"

        time_text = f"{fmt(position)} / {fmt(duration)}" if duration else ""
        if time_text:
            surf = self.font_time.render(time_text, True, (150, 150, 158))
            self.screen.blit(surf, (margin, bar_y - surf.get_height() - 8))


def main():
    config = load_config()
    client = EversoloClient(config["eversolo_ip"], config["eversolo_port"])
    display = Display(config)
    clock = pygame.time.Clock()
    last_poll = 0.0
    info = {}

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q):
                return

        now = time.monotonic()
        if now - last_poll >= config["poll_interval"]:
            last_poll = now
            try:
                state = client.get_state()
                info = parse_now_playing(state, client)
                display.update_cover(info.get("cover_url"), client)
            except Exception as exc:
                print(f"Eversolo injoignable: {exc}")
                info = {"title": "Eversolo injoignable", "artist": "", "album": ""}
                display.update_cover(None, client)

        display.draw(info)
        clock.tick(30)


if __name__ == "__main__":
    try:
        main()
    finally:
        pygame.quit()
        sys.exit(0)
