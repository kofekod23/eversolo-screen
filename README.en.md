# eversolo-screen

[Français](README.md) · [English] · [Español](README.es.md) · [Deutsch](README.de.md)

A "now playing" display for Eversolo streamers (DMP-A6, A6 Master Edition, A8, A10), designed like an amplifier faceplate: album art, title, artist, album, stream quality and progress, full screen on a Raspberry Pi or from any browser on your local network.

These devices expose a local HTTP API on port 9529. Everything stays on your network, no account, no cloud.

## Hardware

- Raspberry Pi (3, 4, 5 or Zero 2 W), Raspberry Pi OS Lite is enough
- HDMI screen (optional, the interface also works from a phone)
- Pi and streamer on the same network

## Automatic installation

```bash
git clone https://github.com/kofekod23/eversolo-screen.git
cd eversolo-screen
./install.sh --kiosk
```

Then open `http://PI_IP:8080`: the first-time setup wizard starts. It asks for a language and an administrator password, and finds the streamer on the network by itself ("Detect" button). Nothing to edit by hand.

- With `--kiosk`: the Pi's HDMI screen shows the interface full screen at boot (cage + Chromium, works without a desktop).
- Without it: only the server is installed, reachable from any device on the network.

Settings can be changed later at `http://PI_IP:8080/config` (clicking the Eversolo logo on the display also gets you there).

## Security

No system is unbreakable, but this application applies serious, LAN-appropriate defenses:

- Administrator password hashed with scrypt, never stored in clear text
- Sensitive files (`auth.json`, `.secret_key`) created with 600 permissions
- Signed sessions, HttpOnly and SameSite Strict cookies, 12 h expiry
- Brute-force lockout: 5 failures, then 15 minutes blocked
- CSRF token on every form
- Cover art proxy strictly limited to the streamer's address (anti SSRF)
- Security headers: CSP, X-Frame-Options, nosniff, Referrer-Policy
- Production WSGI server (waitress), no debug mode
- Hardened systemd service: NoNewPrivileges, ProtectSystem, PrivateTmp, etc.
- The display alone is publicly readable; any change requires the password

Recommendations: do not expose port 8080 to the Internet; for remote access use a VPN (WireGuard, Tailscale). Forgot the password: delete `auth.json` on the Pi and reload the page, the wizard starts again.

## Useful commands

```bash
journalctl -u eversolo-screen@$(whoami) -f          # server logs
sudo systemctl restart eversolo-screen@$(whoami)    # restart the server
sudo systemctl restart eversolo-kiosk@$(whoami)     # restart the kiosk
cd ~/eversolo-screen && ./update.sh                 # update
```

## Architecture

- `server.py`: Flask + waitress server. Polls `ZidooMusicControl/v2/getState`, normalizes metadata (internal player, Bluetooth, streaming apps), proxies album art, and provides the protected setup wizard.
- `static/index.html`: framework-free interface, Fraunces / Archivo / IBM Plex Mono typography, ambient color pulled from the album art, client-side interpolated progress, translated interface (fr, en, es, de).
- `install.sh`: Python venv, systemd services, optional kiosk.
