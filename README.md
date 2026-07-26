# eversolo-screen

[Français] · [English](README.en.md) · [Español](README.es.md) · [Deutsch](README.de.md)

Affichage "en lecture" pour les streamers Eversolo (DMP-A6, A6 Master Edition, A8, A10), pense comme une facade d'ampli : pochette, titre, artiste, album, qualite du flux et progression, en plein ecran sur un Raspberry Pi ou depuis n'importe quel navigateur du reseau local.

Ces appareils exposent une API HTTP locale sur le port 9529. Tout reste sur votre reseau, aucun compte ni cloud.

## Materiel

- Raspberry Pi (3, 4, 5 ou Zero 2 W), Raspberry Pi OS Lite suffit
- Ecran HDMI (optionnel, l'interface est aussi accessible depuis un telephone)
- Pi et streamer sur le meme reseau

## Installation automatique

```bash
git clone https://github.com/kofekod23/eversolo-screen.git
cd eversolo-screen
./install.sh --kiosk
```

Puis ouvrez `http://IP_DU_PI:8080` : l'assistant de premiere configuration se lance. Il vous demande une langue, un mot de passe administrateur, et detecte le streamer tout seul sur le reseau (bouton "Detecter"). Rien a editer a la main.

- Avec `--kiosk` : l'ecran HDMI du Pi affiche l'interface en plein ecran au demarrage (cage + Chromium, fonctionne sans bureau).
- Sans option : seul le serveur est installe, visible depuis tout appareil du reseau.

Les parametres restent modifiables ensuite sur `http://IP_DU_PI:8080/config` (un clic sur le logo Eversolo de l'affichage y mene aussi).

## Securite

Aucun systeme n'est inviolable, mais cette application applique une defense serieuse et adaptee a un usage sur reseau local :

- Mot de passe administrateur hache avec scrypt, jamais stocke en clair
- Fichiers sensibles (`auth.json`, `.secret_key`) crees avec permissions 600
- Sessions signees, cookies HttpOnly et SameSite Strict, expiration 12 h
- Verrouillage anti force brute : 5 echecs, puis blocage 15 minutes
- Jeton CSRF sur tous les formulaires
- Proxy de pochettes limite strictement a l'adresse du streamer (anti SSRF)
- En-tetes de securite : CSP, X-Frame-Options, nosniff, Referrer-Policy
- Serveur WSGI de production (waitress), pas de mode debug
- Service systemd durci : NoNewPrivileges, ProtectSystem, PrivateTmp, etc.
- L'affichage seul est public en lecture ; toute modification exige le mot de passe

Recommandations : n'exposez pas le port 8080 sur Internet ; pour un acces distant, passez par un VPN (WireGuard, Tailscale). Mot de passe oublie : supprimez `auth.json` sur le Pi et rechargez la page, l'assistant se relance.

## Commandes utiles

```bash
journalctl -u eversolo-screen@$(whoami) -f          # logs du serveur
sudo systemctl restart eversolo-screen@$(whoami)    # redemarrer le serveur
sudo systemctl restart eversolo-kiosk@$(whoami)     # redemarrer le kiosque
cd ~/eversolo-screen && ./update.sh                 # mise a jour
```

## Architecture

- `server.py` : serveur Flask + waitress. Interroge `ZidooMusicControl/v2/getState`, normalise les metadonnees (lecteur interne, Bluetooth, apps de streaming), sert de proxy pour les pochettes, et fournit l'assistant de configuration protege.
- `static/index.html` : interface sans framework, typographie Fraunces / Archivo / IBM Plex Mono, ambiance coloree tiree de la pochette, progression interpolee cote client, interface traduite (fr, en, es, de).
- `install.sh` : venv Python, services systemd, kiosque optionnel.
