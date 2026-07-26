# eversolo-screen

[Français](README.md) · [English](README.en.md) · [Español](README.es.md) · [Deutsch]

Eine "Wiedergabe"-Anzeige für Eversolo-Streamer (DMP-A6, A6 Master Edition, A8, A10), gestaltet wie die Front eines Verstaerkers: Cover, Titel, Künstler, Album, Streamqualitaet und Fortschritt, im Vollbild auf einem Raspberry Pi oder in jedem Browser im lokalen Netzwerk.

Diese Geräte stellen eine lokale HTTP-API auf Port 9529 bereit. Alles bleibt im eigenen Netzwerk, kein Konto, keine Cloud.

## Hardware

- Raspberry Pi (3, 4, 5 oder Zero 2 W), Raspberry Pi OS Lite genügt
- HDMI-Bildschirm (optional, die Oberfläche läuft auch auf dem Handy)
- Pi und Streamer im selben Netzwerk

## Automatische Installation

```bash
git clone https://github.com/kofekod23/eversolo-screen.git
cd eversolo-screen
./install.sh --kiosk
```

Danach `http://IP_DES_PI:8080` oeffnen: der Einrichtungsassistent startet. Er fragt nach Sprache und Administrator-Passwort und findet den Streamer selbststaendig im Netzwerk (Schaltflaeche "Suchen"). Nichts muss von Hand editiert werden.

- Mit `--kiosk`: der HDMI-Bildschirm des Pi zeigt die Oberfläche beim Start im Vollbild (cage + Chromium, funktioniert ohne Desktop).
- Ohne Option: nur der Server wird installiert, erreichbar von jedem Gerät im Netzwerk.

Einstellungen lassen sich später unter `http://IP_DES_PI:8080/config` ändern (ein Klick auf das Eversolo-Logo der Anzeige fuehrt ebenfalls dorthin).

## Sicherheit

Kein System ist unangreifbar, aber diese Anwendung setzt ernsthafte, für ein Heimnetz angemessene Schutzmassnahmen um:

- Administrator-Passwort mit scrypt gehasht, nie im Klartext gespeichert
- Sensible Dateien (`auth.json`, `.secret_key`) mit Berechtigung 600 angelegt
- Signierte Sitzungen, HttpOnly- und SameSite-Strict-Cookies, Ablauf nach 12 h
- Brute-Force-Sperre: 5 Fehlversuche, dann 15 Minuten blockiert
- CSRF-Token in allen Formularen
- Cover-Proxy strikt auf die Adresse des Streamers begrenzt (Anti-SSRF)
- Sicherheits-Header: CSP, X-Frame-Options, nosniff, Referrer-Policy
- Produktions-WSGI-Server (waitress), kein Debug-Modus
- Gehärteter systemd-Dienst: NoNewPrivileges, ProtectSystem, PrivateTmp usw.
- Nur die Anzeige ist oeffentlich lesbar; jede Aenderung erfordert das Passwort

Empfehlungen: Port 8080 nicht ins Internet freigeben; für Fernzugriff ein VPN nutzen (WireGuard, Tailscale). Passwort vergessen: `auth.json` auf dem Pi löschen und die Seite neu laden, der Assistent startet erneut.

## Nuetzliche Befehle

```bash
journalctl -u eversolo-screen@$(whoami) -f          # Server-Logs
sudo systemctl restart eversolo-screen@$(whoami)    # Server neu starten
sudo systemctl restart eversolo-kiosk@$(whoami)     # Kiosk neu starten
cd ~/eversolo-screen && ./update.sh                 # Aktualisieren
```

## Architektur

- `server.py`: Flask + waitress. Fragt `ZidooMusicControl/v2/getState` ab, normalisiert die Metadaten (interner Player, Bluetooth, Streaming-Apps), dient als Proxy für Cover und stellt den geschuetzten Einrichtungsassistenten bereit.
- `static/index.html`: Oberfläche ohne Framework, Typografie Fraunces / Archivo / IBM Plex Mono, Farbstimmung aus dem Cover, clientseitig interpolierter Fortschritt, uebersetzte Oberfläche (fr, en, es, de).
- `install.sh`: Python-venv, systemd-Dienste, optionaler Kiosk.
