# eversolo-screen

Affichage "en lecture" pour Eversolo DMP-A6, pense comme une facade d'ampli : pochette, titre, artiste, album, qualite du flux et progression, en plein ecran sur un Raspberry Pi ou depuis n'importe quel navigateur du reseau.

Le DMP-A6 expose une API HTTP locale sur le port 9529. Tout reste sur le reseau local, aucun compte ni cloud.

## Materiel

- Raspberry Pi (3, 4, 5 ou Zero 2 W), Raspberry Pi OS Lite suffit
- Ecran HDMI (optionnel : l'interface est aussi accessible depuis un telephone)
- Pi et DMP-A6 sur le meme reseau

## Installation

```bash
git clone https://github.com/kofekod23/eversolo-screen.git
cd eversolo-screen
./install.sh 192.168.1.XX --kiosk
```

Remplacer `192.168.1.XX` par l'IP du DMP-A6 (Parametres > Reseau sur le streamer).

- Avec `--kiosk` : l'ecran HDMI du Pi affiche l'interface en plein ecran automatiquement au demarrage (via cage + Chromium, fonctionne sans bureau).
- Sans `--kiosk` : seul le serveur est installe, l'interface est visible sur `http://IP_DU_PI:8080` depuis un telephone, une tablette ou un PC.

## Commandes utiles

```bash
journalctl -u eversolo-screen@$(whoami) -f          # logs du serveur
sudo systemctl restart eversolo-screen@$(whoami)    # redemarrer le serveur
sudo systemctl restart eversolo-kiosk@$(whoami)     # redemarrer le kiosque
```

IP du streamer et port modifiables dans `config.json`, puis redemarrer le serveur.

## Mise a jour

```bash
cd ~/eversolo-screen && ./update.sh
```

## Architecture

- `server.py` : petit serveur Flask qui interroge `ZidooMusicControl/v2/getState`, normalise les metadonnees (lecteur interne, Bluetooth, apps de streaming) et sert de proxy pour les pochettes
- `static/index.html` : interface, sans framework, typographie Fraunces / Archivo / IBM Plex Mono, ambiance coloree tiree de la pochette, progression interpolee cote client pour un defilement fluide
- `install.sh` : venv Python, service systemd du serveur, kiosque optionnel

## Test manuel de l'API

```bash
curl http://IP_DU_A6:9529/ZidooMusicControl/v2/getState
```
