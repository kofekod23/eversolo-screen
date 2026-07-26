# eversolo-screen

[Français] · [English](README.en.md) · [Español](README.es.md) · [Deutsch](README.de.md)

Affichage "en lecture" pour les streamers Eversolo (DMP-A6, A6 Master Edition, A8, A10), pense comme une facade d'ampli : pochette, titre, artiste, album, qualite du flux et progression, en plein écran sur un Raspberry Pi ou depuis n'importe quel navigateur du réseau local.

Ces appareils exposent une API HTTP locale sur le port 9529. Tout reste sur votre réseau, aucun compte ni cloud.

## Matériel

- Raspberry Pi (3, 4, 5 ou Zero 2 W), Raspberry Pi OS Lite suffit
- Écran HDMI (optionnel, l'interface est aussi accessible depuis un téléphone)
- Pi et streamer sur le même réseau

## Installation automatique

Raspberry tout neuf ? Suivez le guide pas à pas : [INSTALL.md](INSTALL.md)

```bash
git clone https://github.com/kofekod23/eversolo-screen.git
cd eversolo-screen
./install.sh --kiosk
```

Puis ouvrez `http://IP_DU_PI:8080` : l'assistant de première configuration se lance. Il vous demande une langue, un mot de passe administrateur, et détecte le streamer tout seul sur le réseau (bouton "Détecter"). Rien a editer a la main.

- Avec `--kiosk` : l'écran HDMI du Pi affiche l'interface en plein écran au démarrage (cage + Chromium, fonctionne sans bureau).
- Sans option : seul le serveur est installe, visible depuis tout appareil du réseau.

Les paramètres restent modifiables ensuite sur `http://IP_DU_PI:8080/config` (un clic sur le logo Eversolo de l'affichage y mene aussi).

## Sécurité

Aucun système n'est inviolable, mais cette application applique une defense serieuse et adaptee a un usage sur réseau local :

- Mot de passe administrateur hache avec scrypt, jamais stocke en clair
- Fichiers sensibles (`auth.json`, `.secret_key`) crees avec permissions 600
- Sessions signees, cookies HttpOnly et SameSite Strict, expiration 12 h
- Verrouillage anti force brute : 5 echecs, puis blocage 15 minutes
- Jeton CSRF sur tous les formulaires
- Proxy de pochettes limite strictement a l'adresse du streamer (anti SSRF)
- En-tetes de sécurité : CSP, X-Frame-Options, nosniff, Referrer-Policy
- Serveur WSGI de production (waitress), pas de mode debug
- Service systemd durci : NoNewPrivileges, ProtectSystem, PrivateTmp, etc.
- L'affichage seul est public en lecture ; toute modification exige le mot de passe

Recommandations : n'exposez pas le port 8080 sur Internet ; pour un accès distant, passez par un VPN (WireGuard, Tailscale). Mot de passe oublie : supprimez `auth.json` sur le Pi et rechargez la page, l'assistant se relance.

## Commandes utiles

```bash
journalctl -u eversolo-screen@$(whoami) -f          # logs du serveur
sudo systemctl restart eversolo-screen@$(whoami)    # redémarrer le serveur
sudo systemctl restart eversolo-kiosk@$(whoami)     # redémarrer le kiosque
cd ~/eversolo-screen && ./update.sh                 # mise à jour
```

## Architecture

- `server.py` : serveur Flask + waitress. Interroge `ZidooMusicControl/v2/getState`, normalise les metadonnees (lecteur interne, Bluetooth, apps de streaming), sert de proxy pour les pochettes, et fournit l'assistant de configuration protege.
- `static/index.html` : interface sans framework, typographie Fraunces / Archivo / IBM Plex Mono, ambiance coloree tiree de la pochette, progression interpolee côté client, interface traduite (fr, en, es, de).
- `install.sh` : venv Python, services systemd, kiosque optionnel, récepteur infrarouge optionnel (`--ir`).
- `ir_remote.py` : demon qui traduit n'importe quelle télécommande infrarouge en commandes Eversolo (lecture, pause, piste, volume, muet), avec appairage par apprentissage sur `/remote`. Avec une LED émettrice en plus (`--ir-tx`), le Pi apprend et réémet des commandes vers d'autres appareils (TV, ampli) depuis la page `/blaster`. Details dans [INSTALL.md](INSTALL.md).
