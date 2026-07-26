# Installation sur un Raspberry Pi neuf, pas à pas

Ce guide part de zero : un Raspberry encore dans sa boîte, aucune connaissance requise. Comptez 30 minutes, dont 15 de téléchargement.

## 1. Le matériel nécessaire

- Un Raspberry Pi 3, 4, 5 ou Zero 2 W
- Une carte microSD de 8 Go minimum (16 Go conseillé)
- L'alimentation officielle du Pi (important, les chargeurs de téléphone causent des instabilites)
- Un câble HDMI adapte : HDMI standard pour le Pi 3, micro-HDMI pour les Pi 4 et 5, mini-HDMI pour le Zero 2 W
- Votre écran ou TV en 16/9
- Le réseau : câble Ethernet ou Wi-Fi (le même réseau que votre Eversolo)
- Un ordinateur avec un lecteur de carte SD pour la preparation

## 2. Preparer la carte SD

1. Sur votre ordinateur, téléchargez Raspberry Pi Imager depuis https://www.raspberrypi.com/software/ et installez-le.
2. Insérez la carte microSD dans l'ordinateur.
3. Ouvrez Raspberry Pi Imager :
   - Modèle : choisissez votre Raspberry.
   - Système d'exploitation : "Raspberry Pi OS (other)" puis "Raspberry Pi OS Lite (64-bit)". La version Lite suffit, notre kiosque n'a pas besoin de bureau.
   - Stockage : votre carte SD.
4. Cliquez sur "Suivant" puis "Modifier les réglages". C'est l'étape qui evite d'avoir besoin d'un clavier :
   - Nom d'hote : `eversolo`
   - Cochez "Activer SSH" avec authentification par mot de passe
   - Nom d'utilisateur et mot de passe : choisissez-les et notez-les
   - Wi-Fi : SSID et mot de passe de votre box, pays `FR` (inutile si vous utilisez un câble Ethernet)
   - Réglages locaux : fuseau `Europe/Paris`, clavier `fr`
5. Enregistrez puis lancez l'ecriture. Quelques minutes.

## 3. Premier démarrage

1. Insérez la carte dans le Pi, branchez le HDMI vers l'écran, puis l'alimentation en dernier.
2. Laissez-le tranquille 2 minutes : le premier démarrage redimensionne le système et redémarre tout seul. Un texte qui defile est normal.

## 4. Se connecter au Pi depuis votre ordinateur

Ouvrez un terminal (PowerShell sous Windows, Terminal sous macOS et Linux) :

```bash
ssh votre_utilisateur@eversolo.local
```

Repondez `yes` a la question de confiance, puis saisissez votre mot de passe.

Si `eversolo.local` ne répond pas, trouvez l'adresse IP du Pi dans l'interface de votre box (liste des appareils connectes) ou avec l'application mobile Fing, puis :

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

Important : lancez le `git clone` directement après la connexion, sans changer de dossier, pour que le projet s'installe dans votre dossier personnel (le service de démarrage l'attend a cet endroit).

L'installation prend 5 a 10 minutes selon le modèle. A la fin, le script affiche l'adresse a ouvrir.

## 6. Première configuration

1. Depuis votre téléphone ou votre ordinateur (sur le même réseau), ouvrez `http://eversolo.local:8080`.
2. L'assistant s'affiche : choisissez votre langue, definissez le mot de passe administrateur.
3. Bouton "Détecter sur le réseau" : votre Eversolo est trouve automatiquement, son adresse se remplit toute seule. Vérifiez qu'il est allume.
4. Enregistrez. C'est termine.

Lancez un morceau sur l'Eversolo : l'écran HDMI du Pi affiche la pochette, le titre et la progression. Le modèle exact de votre streamer (DMP-A6, A8, A10...) apparait dans le bandeau du haut.


## Variante : tout preparer depuis le Mac, sans jamais ouvrir de terminal SSH

Si vous préférez que le Pi s'installe entièrement tout seul au premier démarrage :

1. Flashez la carte avec Raspberry Pi Imager comme decrit a l'étape 2, réglages compris (utilisateur, Wi-Fi, SSH). Ne retirez pas la carte du Mac.
2. Si le Mac ne montre plus la carte après le flash, debranchez et rebranchez le lecteur : un volume `bootfs` apparait.
3. Dans le Terminal du Mac :

```bash
curl -O https://raw.githubusercontent.com/kofekod23/eversolo-screen/main/tools/prepare-sd.sh
bash prepare-sd.sh
```

4. Éjectez la carte, insérez-la dans le Raspberry, branchez l'écran puis l'alimentation.
5. Patientez 10 a 15 minutes : le Pi télécharge et installe tout, y compris le kiosque plein écran, puis l'affichage apparait sur la TV.
6. Dernière étape, depuis votre téléphone : `http://eversolo.local:8080` pour l'assistant (langue, mot de passe, détection du streamer).

Note importante selon la version du système : depuis fin 2025, Raspberry Pi OS (base Debian Trixie) et Raspberry Pi Imager 2.0 utilisent cloud-init pour la première configuration, a la place de l'ancien firstrun.sh. Le script prepare-sd.sh détecte automatiquement le mecanisme present sur la carte et s'adapte aux deux. Au démarrage d'une image recente, des messages mentionnant cloud-init sont normaux.

Le Pi a besoin d'Internet a ce premier démarrage (le Wi-Fi configure dans Imager suffit). En cas de souci, le journal d'installation est dans `/var/log/eversolo-provision.log` sur le Pi.

## 7. Vérifications et dépannage

L'écran reste noir après l'installation :

```bash
sudo systemctl status eversolo-kiosk@$(whoami)
sudo systemctl restart eversolo-kiosk@$(whoami)
```

L'interface dit "Streamer introuvable" : vérifiez que l'Eversolo est allume et sur le même réseau, puis retournez sur `/config` et relancez la détection.

Consulter les journaux du serveur :

```bash
journalctl -u eversolo-screen@$(whoami) -f
```

Mot de passe administrateur oublie :

```bash
rm ~/eversolo-screen/auth.json
sudo systemctl restart eversolo-screen@$(whoami)
```

Puis rechargez la page, l'assistant se relance.

## 8. Vie courante

- Le Pi démarre tout seul sur l'affichage a chaque mise sous tension, rien a faire.
- Changer un réglage (IP, langue, mot de passe) : `http://eversolo.local:8080/config`.
- Mettre à jour le projet :

```bash
cd ~/eversolo-screen && ./update.sh
```

- Eteindre proprement le Pi avant de le debrancher :

```bash
sudo poweroff
```

## 9. Réglages d'écran utiles (optionnel)

Écran a l'envers ou pivote : ajoutez a la fin de `/boot/firmware/cmdline.txt` (sur la même ligne) `video=HDMI-A-1:1920x1080@60,rotate=180` puis redémarrez.

Empecher la TV de passer en veille : désactivez la mise en veille automatique dans les réglages de la TV, le Pi envoie une image en continu.

## 10. Télécommande infrarouge (optionnel)

N'importe quelle télécommande de salon peut piloter l'Eversolo (lecture, pause, suivant, précédent, volume, muet) via un petit capteur infrarouge branche sur le Pi.

Matériel : un récepteur TSOP38238 (ou équivalent 38 kHz) et trois câbles Dupont femelle-femelle.

Branchement, capteur face bombée vers vous, pattes vers le bas, de gauche a droite :

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

Le redémarrage active le récepteur. Ensuite, appairage depuis le navigateur : `http://IP_DU_PI:8080/remote` (connexion avec le mot de passe administrateur). Pour chaque action, cliquez sur Associer puis pressez la touche voulue de votre télécommande : le code est mémorisé instantanément. Chaque action est réassociable ou retirable a tout moment.
Une septieme action est disponible a l'appairage : Infos artiste. Une pression sur la touche associée affiche sur l'écran un panneau avec la biographie et la photo de l'artiste en cours (source Wikipedia, dans la langue configurée, aucune clé d'API requise). Le panneau disparait tout seul après 45 secondes, ou immédiatement en pressant a nouveau la touche.

## 11. Émetteur infrarouge (optionnel)

En plus du récepteur, une LED infrarouge permet au Pi de réémettre des commandes apprises vers d'autres appareils (TV, ampli, barre de son). Le récepteur sert de professeur: vous enregistrez une touche de n'importe quelle télécommande, le Pi la rejoue a l'identique, quel que soit le protocole.

Matériel, deux niveaux :

- Simple (portée 1 a 2 m, LED bien orientee) : une LED infrarouge 940 nm et une résistance de 220 ohms en série.
- Confortable (portée 5 m et plus) : ajouter un transistor NPN type 2N2222 pour amplifier, ou prendre un module émetteur tout fait (type KY-005), trois fils comme le récepteur.

Branchement de base : GPIO18 (broche 12) -> résistance 220 ohms -> patte longue de la LED, patte courte -> masse (broche 14). Pour un module KY-005 : S -> broche 12, moins -> masse, milieu -> 3,3 V.

Installation, Pi éteint pour le branchement :

```bash
cd ~/eversolo-screen && git pull && ./install.sh --ir-tx
sudo reboot
```

Utilisation : `http://IP_DU_PI:8080/blaster` (mot de passe administrateur). Donnez un nom a la commande (ex: tv_power), cliquez Apprendre, pressez la touche face àu capteur : c'est mémorisé. Chaque commande apprise a ensuite son bouton Envoyer, utilisable depuis le téléphone. Les options se combinent : `./install.sh --kiosk --ir --ir-tx` installe tout d'un coup.

### Mot de passe administrateur oublié ou refusé

Sur le Pi, dans le dossier du projet :

```bash
venv/bin/python tools/motdepasse.py etat                    # diagnostic
venv/bin/python tools/motdepasse.py verifier MonMotDePasse  # tester un mot de passe
venv/bin/python tools/motdepasse.py nouveau MonMotDePasse   # en définir un nouveau
sudo systemctl restart eversolo-screen@$(whoami)
```

Si l'interface àffiche "Trop de tentatives", le verrouillage anti force brute est actif (5 echecs, 15 minutes). Un redémarrage du serveur le leve immédiatement.
