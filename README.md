# eversolo-screen

Affichage plein ecran des informations de lecture (pochette, titre, artiste, album, barre de progression) d'un Eversolo DMP-A6 sur un Raspberry Pi relie a un ecran HDMI.

Le DMP-A6 expose une API HTTP non officielle sur le port 9529. Ce projet l'interroge en local, aucun compte ni cloud n'est necessaire.

## Materiel

- Raspberry Pi (3, 4, 5 ou Zero 2 W) sous Raspberry Pi OS, Lite suffit
- Ecran HDMI
- Le Pi et le DMP-A6 sur le meme reseau

## Installation sur le Raspberry Pi

```bash
git clone https://github.com/kofekod23/eversolo-screen.git
cd eversolo-screen
chmod +x install.sh
./install.sh 192.168.1.XX
```

Remplacer `192.168.1.XX` par l'adresse IP du DMP-A6 (visible dans Parametres > Reseau sur le streamer). Le script installe les dependances, cree un environnement virtuel Python et enregistre un service systemd qui demarre l'affichage automatiquement au boot.

## Utilisation

Le service tourne tout seul. Commandes utiles :

```bash
sudo systemctl status eversolo-screen@$(whoami)    # etat
journalctl -u eversolo-screen@$(whoami) -f         # logs en direct
sudo systemctl restart eversolo-screen@$(whoami)   # redemarrage
```

Pour changer l'IP du streamer ou l'intervalle de rafraichissement, editer `config.json` puis redemarrer le service.

## Mise a jour

```bash
cd ~/eversolo-screen && ./update.sh
```

## Test manuel de l'API

```bash
curl http://IP_DU_A6:9529/ZidooMusicControl/v2/getState
```

## Notes techniques

- Sources gerees : lecteur interne (fichiers locaux, Tidal, Qobuz integres) via `playingMusic`, et Bluetooth ou apps de streaming via `everSoloPlayInfo`
- La pochette est recuperee via `getImage?id=...` ou l'URL fournie par le streamer
- Sans environnement de bureau, pygame utilise le pilote KMS/DRM (`SDL_VIDEODRIVER=kmsdrm`), l'ecran est donc pilote directement sans serveur X
- Quitter en mode manuel : touche Echap ou Q
