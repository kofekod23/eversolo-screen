# Installation sur un Raspberry Pi neuf, pas à pas

Guide d'installation complet, du Raspberry neuf à l'écran fonctionnel. Pour l'essentiel en trois étapes, voir le [README](README.md).

## Sommaire

- [1. Le matériel nécessaire](#1-le-matériel-nécessaire)
- [2. Préparer la carte SD](#2-préparer-la-carte-sd)
- [3. Premier démarrage](#3-premier-démarrage)
- [4. Se connecter au Pi depuis votre ordinateur](#4-se-connecter-au-pi-depuis-votre-ordinateur)
- [5. Installer eversolo-screen](#5-installer-eversolo-screen)
- [6. Première configuration](#6-première-configuration)
- [Variante : tout préparer depuis le Mac, sans jamais ouvrir de terminal SSH](#variante--tout-préparer-depuis-le-mac-sans-jamais-ouvrir-de-terminal-ssh)
- [7. Vérifications et dépannage](#7-vérifications-et-dépannage)
- [8. Vie courante](#8-vie-courante)
- [9. Réglages d'écran utiles (optionnel)](#9-réglages-décran-utiles-optionnel)
- [10. Télécommande infrarouge (optionnel)](#10-télécommande-infrarouge-optionnel)
- [11. Émetteur infrarouge (optionnel)](#11-émetteur-infrarouge-optionnel)
- [Ménager la carte SD (option --ram)](#ménager-la-carte-sd-option---ram)

## 1. Le matériel nécessaire

- Un Raspberry Pi 3, 4, 5 ou Zero 2 W
- Une carte microSD de 8 Go minimum (16 Go conseillé)
- L'alimentation officielle du Pi (important, les chargeurs de téléphone causent des instabilités)
- Un câble HDMI adapté : HDMI standard pour le Pi 3, micro-HDMI pour les Pi 4 et 5, mini-HDMI pour le Zero 2 W
- Votre écran ou TV en 16/9
- Le réseau : câble Ethernet ou Wi-Fi (le même réseau que votre Eversolo)
- Un ordinateur avec un lecteur de carte SD pour la préparation

## 2. Préparer la carte SD

1. Sur votre ordinateur, téléchargez Raspberry Pi Imager depuis https://www.raspberrypi.com/software/ et installez-le.
2. Insérez la carte microSD dans l'ordinateur.
3. Ouvrez Raspberry Pi Imager :
   - Modèle : choisissez votre Raspberry.
   - Système d'exploitation : "Raspberry Pi OS (other)" puis "Raspberry Pi OS Lite (64-bit)". La version Lite suffit, notre kiosque n'a pas besoin de bureau.
   - Stockage : votre carte SD.
4. Cliquez sur "Suivant" puis "Modifier les réglages". C'est l'étape qui évite d'avoir besoin d'un clavier :
   - Nom d'hôte : `eversolo`
   - Cochez "Activer SSH" avec authentification par mot de passe
   - Nom d'utilisateur et mot de passe : choisissez-les et notez-les
   - Wi-Fi : SSID et mot de passe de votre box, pays `FR` (inutile si vous utilisez un câble Ethernet)
   - Réglages locaux : fuseau `Europe/Paris`, clavier `fr`
5. Enregistrez puis lancez l'écriture. Quelques minutes.

## 3. Premier démarrage

1. Insérez la carte dans le Pi, branchez le HDMI vers l'écran, puis l'alimentation en dernier.
2. Laissez-le tranquille 2 minutes : le premier démarrage redimensionne le système et redémarre tout seul. Un texte qui défile est normal.

## 4. Se connecter au Pi depuis votre ordinateur

Ouvrez un terminal (PowerShell sous Windows, Terminal sous macOS et Linux) :

```bash
ssh votre_utilisateur@eversolo.local
```

Répondez `yes` à la question de confiance, puis saisissez votre mot de passe.

Si `eversolo.local` ne répond pas, trouvez l'adresse IP du Pi dans l'interface de votre box (liste des appareils connectés) ou avec l'application mobile Fing, puis :

```bash
ssh votre_utilisateur@192.168.1.XX
```

## 5. Installer eversolo-screen

Toujours dans le terminal SSH, ces quatre lignes :

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/kofekod23/eversolo-screen.git
cd eversolo-screen
./install.sh --kiosk
```

Important : lancez le `git clone` directement après la connexion, sans changer de dossier, pour que le projet s'installe dans votre dossier personnel (le service de démarrage l'attend à cet endroit).

L'installation prend 5 à 10 minutes selon le modèle. À la fin, le script affiche l'adresse à ouvrir.

## 6. Première configuration

1. Depuis votre téléphone ou votre ordinateur (sur le même réseau), ouvrez `http://eversolo.local:8080`.
2. L'assistant s'affiche : saisissez le code à six chiffres affiché sur la TV, choisissez votre langue, définissez le mot de passe administrateur. Ce code empêche un autre appareil du réseau de prendre la main avant vous ; sans écran branché, il figure dans le journal : `journalctl -u eversolo-screen@$(whoami) | grep code`.
3. Bouton "Détecter sur le réseau" : votre Eversolo est trouvé automatiquement, son adresse se remplit toute seule. Vérifiez qu'il est allumé.
4. Enregistrez. C'est terminé.

**Clés optionnelles.** Tout fonctionne sans elles. Gratuites, elles ajoutent biographies et crédits ; collez-les dans `/config`, rubrique des sources, puis enregistrez :

- **Last.fm** (biographies, descriptions d'albums) : [créez un compte API](https://www.last.fm/api/account/create), avec un nom et une description au choix et l'URL de rappel vide. Copiez la valeur « API key ». Une clé déjà créée se retrouve sur [last.fm/api/accounts](https://www.last.fm/api/accounts).
- **Discogs** (crédits de production, mixage, studios) : [Settings > Developers](https://www.discogs.com/settings/developers), bouton « Generate new token ». Le jeton reste affiché sur cette page.
- **Genius** (crédits de la plage en cours) : sur [genius.com/api-clients](https://genius.com/api-clients), « New API Client » avec un nom et une adresse de site au choix, puis « Generate Access Token ». Copiez le « Client Access Token ».
- **TheAudioDB** (biographies, photos) : rien à faire, la clé gratuite `123` est utilisée par défaut. Seuls les abonnés Premium remplacent cette clé par la leur, visible sur leur profil.

Ces clés vivent seulement dans `config.json` sur le Pi : en cas de réinstallation, reprenez-les sur les pages ci-dessus.

Lancez un morceau sur l'Eversolo : l'écran HDMI du Pi affiche la pochette, le titre et la progression. Le modèle exact de votre streamer (DMP-A6, A8, A10...) apparaît dans le bandeau du haut.


## Variante : tout préparer depuis le Mac, sans jamais ouvrir de terminal SSH

Si vous préférez que le Pi s'installe entièrement tout seul au premier démarrage :

1. Flashez la carte avec Raspberry Pi Imager comme décrit à l'étape 2, réglages compris (utilisateur, Wi-Fi, SSH). Ne retirez pas la carte du Mac.
2. Si le Mac ne montre plus la carte après le flash, débranchez et rebranchez le lecteur : un volume `bootfs` apparaît.
3. Dans le Terminal du Mac :

```bash
curl -O https://raw.githubusercontent.com/kofekod23/eversolo-screen/main/tools/prepare-sd.sh
bash prepare-sd.sh
```

4. Éjectez la carte, insérez-la dans le Raspberry, branchez l'écran puis l'alimentation.
5. Patientez 10 à 15 minutes : le Pi télécharge et installe tout, y compris le kiosque plein écran, puis l'affichage apparaît sur la TV.
6. Dernière étape, depuis votre téléphone : `http://eversolo.local:8080` pour l'assistant (code affiché sur la TV, langue, mot de passe, détection du streamer).

Note importante selon la version du système : depuis fin 2025, Raspberry Pi OS (base Debian Trixie) et Raspberry Pi Imager 2.0 utilisent cloud-init pour la première configuration, à la place de l'ancien firstrun.sh. Le script prepare-sd.sh détecte automatiquement le mécanisme présent sur la carte et s'adapte aux deux. Au démarrage d'une image récente, des messages mentionnant cloud-init sont normaux.

Le Pi a besoin d'Internet à ce premier démarrage (le Wi-Fi configuré dans Imager suffit). En cas de souci, le journal d'installation est dans `/var/log/eversolo-provision.log` sur le Pi.

## 7. Vérifications et dépannage

L'écran reste noir après l'installation :

```bash
sudo systemctl status eversolo-kiosk@$(whoami)
sudo systemctl restart eversolo-kiosk@$(whoami)
```

L'interface dit "Streamer introuvable" : vérifiez que l'Eversolo est allumé et sur le même réseau, puis retournez sur `/config` et relancez la détection.

Consulter les journaux du serveur :

```bash
journalctl -u eversolo-screen@$(whoami) -f
```

Mot de passe administrateur oublié :

```bash
rm ~/eversolo-screen/auth.json
sudo systemctl restart eversolo-screen@$(whoami)
```

Puis rechargez la page, l'assistant se relance, avec un nouveau code affiché sur la TV.

La page affiche "Adresse non reconnue" : le Pi n'accepte que son adresse IP, `localhost` et son nom (`eversolo`, `eversolo.local`), pour se protéger des pages web piégées. Si votre box lui donne un autre nom (par exemple `eversolo.lan`), ajoutez-le dans `config.json` : `"hotes_autorises": ["eversolo.lan"]`, puis redémarrez le service.

Un comportement à signaler : sur `/config`, la section "Capture de l'état" enregistre ce que l'Eversolo renvoie pendant une lecture (sans adresse de flux ni identifiant). Joignez le fichier téléchargé à votre signalement.

## 8. Vie courante

- Le Pi démarre tout seul sur l'affichage à chaque mise sous tension, rien à faire.
- Changer un réglage (IP, langue, mot de passe) : `http://eversolo.local:8080/config`.
- Mettre à jour : bouton de `/config` quand une version signée est publiée, ou en SSH (une ancienne installation passe alors aux dossiers de versions) :

```bash
cd ~/eversolo-screen && ./update.sh
```

- Éteindre proprement le Pi avant de le débrancher :

```bash
sudo poweroff
```

## 9. Réglages d'écran utiles (optionnel)

Écran à l'envers ou pivoté : ajoutez à la fin de `/boot/firmware/cmdline.txt` (sur la même ligne) `video=HDMI-A-1:1920x1080@60,rotate=180` puis redémarrez.

Empêcher la TV de passer en veille : désactivez la mise en veille automatique dans les réglages de la TV, le Pi envoie une image en continu.

## 10. Télécommande infrarouge (optionnel)

N'importe quelle télécommande de salon peut piloter l'Eversolo (lecture, pause, suivant, précédent, volume, muet) via un petit capteur infrarouge branché sur le Pi.

Matériel : un récepteur TSOP38238 (ou équivalent 38 kHz) et trois câbles Dupont femelle-femelle.

Branchement, capteur face bombée vers vous, pattes vers le bas, de gauche à droite :

| Patte du capteur | Broche du Raspberry |
|---|---|
| 1 - OUT (signal) | Broche 11 (GPIO17) |
| 2 - GND | Broche 6 (masse) |
| 3 - VS (alimentation) | Broche 1 (3,3 V) |

Installation, Pi éteint pour le branchement, puis :

```bash
cd ~/eversolo-screen && git pull && ./install.sh --ir
sudo reboot
```

Le redémarrage active le récepteur. Ensuite, appairage depuis le navigateur : `http://IP_DU_PI:8080/remote` (connexion avec le mot de passe administrateur). Pour chaque action, cliquez sur Associer puis pressez la touche voulue de votre télécommande : le code est mémorisé instantanément. Chaque action est réassociable ou retirable à tout moment.
Une septième action est disponible à l'appairage : Infos artiste. Elle ouvre sur l'écran un volet en trois pages : biographie de l'artiste, album (plages et durées), production (crédits, label, studios). Les sources vont des plus spécialisées aux plus générales : TheAudioDB et Last.fm pour les biographies, Wikipédia en repli, MusicBrainz, Discogs et Genius pour les crédits. Tout fonctionne sans clé ; les clés optionnelles se renseignent dans `/config` (voir la section 6).

Volet ouvert, les touches changent de rôle :

- **Volume + / Volume −** font défiler le texte (le volume de l'Eversolo ne bouge pas) ;
- **Suivant / Précédent** changent de page (il faut donc les avoir associées aussi) ;
- **Infos artiste** referme le volet, qui se ferme aussi tout seul une minute après la dernière touche.

Si le texte bouge tout seul, un autre appareil émet peut-être le même code que votre touche de volume (télécommande coincée sous un objet, ampli de même marque). Le bouton « Tester le capteur » de la page `/remote` montre si un signal arrive alors que personne n'appuie.

## 11. Émetteur infrarouge (optionnel)

En plus du récepteur, une LED infrarouge permet au Pi de réémettre des commandes apprises vers d'autres appareils (TV, ampli, barre de son). Le récepteur sert de professeur : vous enregistrez une touche de n'importe quelle télécommande, le Pi la rejoue à l'identique, quel que soit le protocole.

Matériel, deux niveaux :

- Simple (portée 1 à 2 m, LED bien orientée) : une LED infrarouge 940 nm et une résistance de 220 ohms en série.
- Confortable (portée 5 m et plus) : ajouter un transistor NPN type 2N2222 pour amplifier, ou prendre un module émetteur tout fait (type KY-005), trois fils comme le récepteur.

Branchement de base : GPIO18 (broche 12) -> résistance 220 ohms -> patte longue de la LED, patte courte -> masse (broche 14). Pour un module KY-005 : S -> broche 12, moins -> masse, milieu -> 3,3 V.

Installation, Pi éteint pour le branchement :

```bash
cd ~/eversolo-screen && git pull && ./install.sh --ir-tx
sudo reboot
```

Utilisation : `http://IP_DU_PI:8080/blaster` (mot de passe administrateur). Donnez un nom à la commande (ex. : tv_power), cliquez Apprendre, pressez la touche face au capteur : c'est mémorisé. Chaque commande apprise a ensuite son bouton Envoyer, utilisable depuis le téléphone. Les options se combinent : `./install.sh --kiosk --ir --ir-tx` installe tout d'un coup.

### Mot de passe administrateur oublié ou refusé

Sur le Pi, dans le dossier du projet (`cd ~/eversolo-screen`) ; sur une installation d'avant les versions par dossier, remplacez `~/eversolo-versions/courante/venv` par `venv` :

```bash
~/eversolo-versions/courante/venv/bin/python tools/motdepasse.py etat                    # diagnostic
~/eversolo-versions/courante/venv/bin/python tools/motdepasse.py verifier MonMotDePasse  # tester un mot de passe
~/eversolo-versions/courante/venv/bin/python tools/motdepasse.py nouveau MonMotDePasse   # en définir un nouveau
sudo systemctl restart eversolo-screen@$(whoami)
```

Si l'interface affiche "Trop de tentatives", le verrouillage anti force brute est actif (5 échecs depuis un même appareil, ou 30 en tout, sur 15 minutes). Un redémarrage du serveur le lève immédiatement.

## Ménager la carte SD (option --ram)

Un Pi qui tourne en continu use sa carte SD par les écritures répétées (journaux, cache du navigateur, swap). L'option `--ram` élimine l'essentiel :

- journaux systemd en mémoire (volatils, perdus au redémarrage)
- profil et cache Chromium en RAM
- /tmp en RAM si ce n'est pas déjà le cas
- swap désactivé

```bash
cd ~/eversolo-screen && ./install.sh --ram
sudo reboot
```

La configuration, le mot de passe, les appairages de télécommande et les mises à jour restent persistants. Seul l'historique des journaux disparaît à chaque redémarrage : pour diagnostiquer un problème, faites-le avant de redébrancher.
