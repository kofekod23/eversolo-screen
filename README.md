# eversolo-screen

Affichage « now playing » pour streamers Eversolo (DMP-A6, A8, A10) sur Raspberry Pi + écran HDMI. Pochette, titre, qualité audio, biographies d'artistes et crédits de production, pilotés à la télécommande infrarouge.

[English](README.en.md) · [Español](README.es.md) · [Deutsch](README.de.md)

## Fonctionnalités

- Pochette, titre, artiste, album, progression, horloge, ambiance colorée tirée de la pochette
- Qualité audio en pastilles : fréquence, profondeur, débit (formats Eversolo réels gérés, virgule française comprise)
- Volet infos sur 3 pages : biographie de l'artiste, album (description, plages, durées), production (crédits, label, studios)
- Télécommande infrarouge par apprentissage : 7 actions appairables avec n'importe quelle télécommande
- Émetteur infrarouge optionnel : le Pi apprend et réémet des commandes vers TV ou ampli
- Kiosque automatique au démarrage, interface d'administration protégée par mot de passe
- 4 langues : français, anglais, espagnol, allemand
- Mise à jour en un clic depuis l'interface

## Matériel

| Élément | Minimum | Conseillé |
|---|---|---|
| Raspberry Pi | Pi 3 | Pi 4, 2 Go |
| Carte SD | 16 Go | Classe A1 |
| Alimentation | | Officielle Raspberry |
| Réseau | Wi-Fi | Ethernet |
| Capteur IR (optionnel) | VS1838B ou TSOP38238 | |
| LED IR (optionnel) | LED 940 nm + résistance 220 Ω | Module KY-005 |

L'Eversolo est piloté par le réseau (API port 9529) : aucun capteur requis sur le streamer.

## Installation

### Automatique (recommandée)

1. Raspberry Pi Imager : Raspberry Pi OS Lite 64 bits, SSH activé, authentification par mot de passe
2. Carte encore dans l'ordinateur :

```bash
curl -O https://raw.githubusercontent.com/kofekod23/eversolo-screen/main/tools/prepare-sd.sh
bash prepare-sd.sh
```

3. Démarrer le Pi. Après 10 à 15 minutes, ouvrir `http://IP_DU_PI:8080` : l'assistant détecte l'Eversolo et crée le mot de passe administrateur.

### Manuelle (SSH)

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/kofekod23/eversolo-screen.git
cd eversolo-screen && ./install.sh --kiosk --ir
sudo reboot
```

Options cumulables : `--kiosk` (affichage TV), `--ir` (récepteur télécommande), `--ir-tx` (émetteur).

## Télécommande

`http://IP_DU_PI:8080/remote` : schéma de câblage du capteur, voyant de détection, test en direct, appairage des 7 actions (lecture/pause, plages, volume, muet, infos). Volet infos ouvert : les touches volume défilent le texte, les touches de plage tournent les pages.

## Sources de données

| Donnée | Sources |
|---|---|
| Identité artiste et album | MusicBrainz (l'album en cours lève les homonymies) |
| Biographies | TheAudioDB, Last.fm, Wikipédia via Wikidata |
| Plages, crédits, studios | MusicBrainz, Discogs |

Sans aucune clé, tout fonctionne. Clés optionnelles sur `/config` pour élargir la couverture : Last.fm (gratuite), Discogs (jeton personnel gratuit, crédits des sorties récentes), TheAudioDB.

## Mise à jour

Bouton sur `/config` quand une nouvelle version est publiée, ou en SSH : `./update.sh`. Configuration et mot de passe préservés.

## Dépannage

Guide détaillé pas à pas : [INSTALL.md](INSTALL.md). Mot de passe oublié : `venv/bin/python tools/motdepasse.py`.
