#!/usr/bin/env python3
"""Serveur eversolo-screen.

Interface "en lecture" pour streamers Eversolo (gamme DMP) avec page de configuration
protégée : mot de passe hache (scrypt), sessions signees, anti force brute,
jeton CSRF, proxy pochettes limite au streamer, en-tetes de sécurité.
"""

import glob
import hashlib
import ipaddress
import json
import re
import subprocess
import threading
import os
import secrets
import socket
import time
import traceback
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlparse

import requests
from flask import (Flask, Response, jsonify, redirect, render_template_string,
                   request, send_from_directory, session)
from markupsafe import Markup, escape
from werkzeug.security import check_password_hash, generate_password_hash

import affichage
import versions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Installé par versions (un dossier par version) : les données vivent dans le
# dépôt de référence, jamais dans le dossier d'une version.
DISPO = versions.disposition_de(BASE_DIR)
# Fichiers modifiables (réglages, mot de passe, caches, captures) : à côté du
# code par défaut, ailleurs si EVERSOLO_SCREEN_DATA le demande (service, tests).
DATA_DIR = os.path.abspath(os.environ.get("EVERSOLO_SCREEN_DATA")
                           or (DISPO.depot if DISPO else BASE_DIR))
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
AUTH_PATH = os.path.join(DATA_DIR, "auth.json")
SECRET_PATH = os.path.join(DATA_DIR, ".secret_key")

DEFAULTS = {
    "eversolo_ip": "",
    "eversolo_port": 9529,
    "listen_port": 8080,
    "language": "fr",
    "theaudiodb_key": "123",
    "lastfm_api_key": "",
    "discogs_token": "",
    "genius_token": "",
}

LANGS = ("fr", "en", "es", "de")

# ---------------------------------------------------------------- traductions

T = {
    "fr": {
        "setup_title": "Première configuration",
        "setup_intro": "Choisissez un mot de passe administrateur et indiquez votre streamer.",
        "password": "Mot de passe administrateur",
        "password_confirm": "Confirmer le mot de passe",
        "password_short": "8 caractères minimum.",
        "password_mismatch": "Les deux mots de passe ne correspondent pas.",
        "device_ip": "Adresse IP du streamer",
        "detect": "Détecter sur le réseau",
        "detecting": "Recherche en cours...",
        "detect_none": "Aucun streamer trouvé. Saisissez l'IP manuellement.",
        "language": "Langue",
        "save": "Enregistrer", "maj_deja": "Une mise à jour est déjà en cours.",
        "maj_installee": "Version en service", "maj_disponible": "Nouvelle version", "maj_installer": "Installer cette version", "maj_revenir": "Revenir à la version précédente", "maj_pendant_lecture": "Mettez la lecture en pause avant de mettre à jour.", "maj_rien": "Aucune nouvelle version à installer.", "maj_lancee": "Installation lancée : téléchargement, vérification de la signature, puis redémarrage. L'écran se rechargera tout seul.", "maj_retour_lance": "Retour à la version précédente : le serveur redémarre.", "maj_etape_telechargement": "Téléchargement en cours", "maj_etape_verification": "Vérification de la signature", "maj_etape_installation": "Installation en cours", "maj_tv": "Mise à jour",
        "disp_title": "Affichage", "disp_intro": "Réglez l'écran selon la distance de lecture.", "disp_theme": "Interface", "theme_pochette": "Pochette : l'écran prend la couleur du disque", "theme_console": "Console : façade d'appareil, afficheur fluorescent", "theme_affiche": "Affiche : grande typographie, papier et encre", "theme_cadre": "Plein cadre : la pochette occupe tout un côté de l'écran", "disp_profil": "Type d'écran", "profil_salon": "Salon : TV lue à 3-4 m", "profil_bureau": "Bureau : écran proche", "profil_petit": "Petit écran 7 à 10 pouces", "disp_nuit": "Mode nuit (luminosité réduite)", "nuit_auto": "Selon l'heure", "nuit_jamais": "Jamais", "nuit_toujours": "Toujours", "nuit_de": "Nuit de", "nuit_a": "heures à", "nuit_h": "heures", "disp_protection": "Protéger l'écran : léger décalage, atténuation après 10 min de pause, noir après 30 min", "disp_save": "Enregistrer l'affichage",
        "login_title": "Connexion",
        "login": "Se connecter",
        "logout": "Se déconnecter",
        "bad_password": "Mot de passe incorrect.",
        "locked": "Trop de tentatives. Réessayez dans quelques minutes.",
        "config_title": "Configuration",
        "current_password": "Mot de passe actuel",
        "new_password": "Nouveau mot de passe (laisser vide pour conserver)",
        "saved": "Enregistré.",
        "back_display": "Retour à l'affichage",
        "invalid_ip": "Adresse IP invalide.",
        "blaster_title": "Émetteur infrarouge", "blaster_intro": "Enregistrez des touches de vos télécommandes, le Pi pourra les réémettre (TV, ampli...).", "new_name": "Nom de la commande (ex: tv_power)", "learn": "Apprendre", "send_cmd": "Envoyer", "delete_cmd": "Supprimer", "learn_hint": "Pressez maintenant la touche à apprendre, face au capteur...", "learned": "Commande enregistrée.", "learn_failed": "Rien reçu. Vérifiez le capteur et réessayez.", "no_tx": "Émetteur introuvable (option --ir-tx installée et redémarrage fait ?).", "bad_name": "Nom invalide: lettres, chiffres, tiret, 32 caractères max.", "blaster_link": "Émetteur infrarouge",
        "hw_title": "Matériel infrarouge", "hw_pin": "Broche du Raspberry", "hw_leg": "Patte du capteur", "hw_signal": "Signal (OUT / S)", "hw_gnd": "Masse (GND / -)", "hw_vcc": "Alimentation (VCC / +)", "hw_note": "Capteur VS1838B ou TSOP38238, face bombée vers vous, pattes en bas : OUT à gauche, GND au milieu, VCC à droite. Fiez-vous aux étiquettes si votre capteur est sur un module.", "hw_rx_ok": "Récepteur détecté", "hw_rx_ko": "Récepteur non détecté: vérifiez le câblage, puis ./install.sh --ir et un redémarrage.", "hw_tx_ok": "Émetteur détecté", "hw_tx_ko": "Émetteur non installé (optionnel).", "hw_test": "Tester le capteur", "hw_test_wait": "Pressez une touche...", "hw_test_ok": "Signal reçu, capteur fonctionnel.", "hw_test_ko": "Aucun signal reçu en 15 s.",
        "no_bio": "Aucune biographie trouvée pour cet artiste dans les sources consultées.",
        "tadb_key": "Clé TheAudioDB (repli biographies, clé d’essai par défaut)", "lastfm_key": "Clé API Last.fm (repli biographies, optionnelle)",
        "searching": "Recherche des informations sur l'artiste et le disque...",
        "discogs_token": "Jeton Discogs (crédits de production détaillés, optionnel)",
        "maj_ancienne": "Mises à jour : lancez ./update.sh une fois sur le Pi pour passer aux versions signées", "up_to_date": "Application à jour",
        "genius_token_lbl": "Jeton Genius (crédits de la plage en cours, optionnel)",
        "remote_title": "Télécommande", "remote_intro": "Cliquez sur Associer puis pressez la touche voulue sur votre télécommande.", "pair": "Associer", "press_key": "Pressez une touche...", "clear": "Retirer", "not_paired": "Non associée", "act_play_pause": "Lecture / Pause", "act_next": "Suivant", "act_previous": "Précédent", "act_vol_up": "Volume +", "act_vol_down": "Volume -", "act_info": "Infos artiste", "act_mute": "Muet", "remote_link": "Télécommande infrarouge",
        "session_expired": "Session expirée, reconnectez-vous.",
        "code_label": "Code affiché sur la TV", "code_bad": "Code incorrect. Recopiez le code affiché sur la TV.", "code_first": "Saisissez d'abord le code affiché sur la TV.",
        "tv_setup_intro": "Sur votre téléphone ou votre ordinateur, ouvrez", "tv_setup_code": "puis saisissez ce code", "tv_setup_here": "Configurer depuis cet écran",
        "host_refused": "Adresse non reconnue. Ouvrez la page par l'adresse IP du Pi (par exemple http://{ip}:{port}), ou ajoutez ce nom à la liste hotes_autorises de config.json.",
        "capture_title": "Capture de l'état", "capture_intro": "Lancez une lecture sur l'Eversolo, choisissez la situation puis capturez. Ce que l'Eversolo renvoie est enregistré sur le Pi, sans adresse de flux ni identifiant.", "capture_situation": "Situation", "capture_btn": "Capturer l'état", "capture_done": "Capture enregistrée", "capture_failed": "Eversolo injoignable : capture impossible.", "capture_busy": "Une capture est déjà en cours.", "captures_list": "Captures enregistrées",
        "sit_fichier": "Fichier local", "sit_pause": "Pause", "sit_muet": "Son coupé", "sit_autre": "Autre",
    },
    "en": {
        "setup_title": "First-time setup",
        "setup_intro": "Choose an administrator password and point to your streamer.",
        "password": "Administrator password",
        "password_confirm": "Confirm password",
        "password_short": "8 characters minimum.",
        "password_mismatch": "Passwords do not match.",
        "device_ip": "Streamer IP address",
        "detect": "Detect on network",
        "detecting": "Scanning...",
        "detect_none": "No streamer found. Enter the IP manually.",
        "language": "Language",
        "save": "Save", "maj_deja": "An update is already running.",
        "maj_installee": "Running version", "maj_disponible": "New version", "maj_installer": "Install this version", "maj_revenir": "Go back to the previous version", "maj_pendant_lecture": "Pause playback before updating.", "maj_rien": "No new version to install.", "maj_lancee": "Installation started: download, signature check, then restart. The screen will reload by itself.", "maj_retour_lance": "Going back to the previous version: the server restarts.", "maj_etape_telechargement": "Downloading", "maj_etape_verification": "Checking the signature", "maj_etape_installation": "Installing", "maj_tv": "Update",
        "disp_title": "Display", "disp_intro": "Adjust the screen to your viewing distance.", "disp_theme": "Interface", "theme_pochette": "Cover: the screen takes the colour of the record", "theme_console": "Console: device front panel, fluorescent display", "theme_affiche": "Poster: large type, paper and ink", "theme_cadre": "Full frame: the cover fills one side of the screen", "disp_profil": "Screen type", "profil_salon": "Living room: TV read from 3-4 m", "profil_bureau": "Desk: close screen", "profil_petit": "Small 7 to 10 inch screen", "disp_nuit": "Night mode (reduced brightness)", "nuit_auto": "By time of day", "nuit_jamais": "Never", "nuit_toujours": "Always", "nuit_de": "Night from", "nuit_a": "h to", "nuit_h": "h", "disp_protection": "Protect the screen: slight shift, dimming after 10 min of pause, black after 30 min", "disp_save": "Save display",
        "login_title": "Sign in",
        "login": "Sign in",
        "logout": "Sign out",
        "bad_password": "Incorrect password.",
        "locked": "Too many attempts. Try again in a few minutes.",
        "config_title": "Settings",
        "current_password": "Current password",
        "new_password": "New password (leave empty to keep)",
        "saved": "Saved.",
        "back_display": "Back to display",
        "invalid_ip": "Invalid IP address.",
        "blaster_title": "Infrared blaster", "blaster_intro": "Record buttons from your remotes, the Pi can replay them (TV, amp...).", "new_name": "Command name (e.g. tv_power)", "learn": "Learn", "send_cmd": "Send", "delete_cmd": "Delete", "learn_hint": "Now press the button to learn, facing the sensor...", "learned": "Command recorded.", "learn_failed": "Nothing received. Check the sensor and retry.", "no_tx": "Emitter not found (--ir-tx installed and rebooted?).", "bad_name": "Invalid name: letters, digits, dash, 32 chars max.", "blaster_link": "Infrared blaster",
        "hw_title": "Infrared hardware", "hw_pin": "Raspberry pin", "hw_leg": "Sensor leg", "hw_signal": "Signal (OUT / S)", "hw_gnd": "Ground (GND / -)", "hw_vcc": "Power (VCC / +)", "hw_note": "VS1838B or TSOP38238 sensor, dome facing you, legs down: OUT left, GND middle, VCC right. Trust the labels if your sensor is on a module.", "hw_rx_ok": "Receiver detected", "hw_rx_ko": "Receiver not detected: check wiring, then ./install.sh --ir and reboot.", "hw_tx_ok": "Emitter detected", "hw_tx_ko": "Emitter not installed (optional).", "hw_test": "Test the sensor", "hw_test_wait": "Press a button...", "hw_test_ok": "Signal received, sensor works.", "hw_test_ko": "No signal received within 15 s.",
        "no_bio": "No biography found for this artist in the available sources.",
        "tadb_key": "TheAudioDB key (biography fallback, test key by default)", "lastfm_key": "Last.fm API key (biography fallback, optional)",
        "searching": "Looking up artist and record information...",
        "discogs_token": "Discogs token (detailed production credits, optional)",
        "maj_ancienne": "Updates: run ./update.sh once on the Pi to switch to signed versions", "up_to_date": "Application up to date",
        "genius_token_lbl": "Genius token (credits of the current track, optional)",
        "remote_title": "Remote control", "remote_intro": "Click Pair then press the desired button on your remote.", "pair": "Pair", "press_key": "Press a button...", "clear": "Remove", "not_paired": "Not paired", "act_play_pause": "Play / Pause", "act_next": "Next", "act_previous": "Previous", "act_vol_up": "Volume +", "act_vol_down": "Volume -", "act_info": "Artist info", "act_mute": "Mute", "remote_link": "Infrared remote",
        "session_expired": "Session expired, sign in again.",
        "code_label": "Code shown on the TV", "code_bad": "Wrong code. Copy the code shown on the TV.", "code_first": "Enter the code shown on the TV first.",
        "tv_setup_intro": "On your phone or computer, open", "tv_setup_code": "then enter this code", "tv_setup_here": "Set up from this screen",
        "host_refused": "Unrecognised address. Open the page through the Pi's IP address (for example http://{ip}:{port}), or add this name to the hotes_autorises list in config.json.",
        "capture_title": "State capture", "capture_intro": "Start playback on the Eversolo, pick the situation, then capture. What the Eversolo reports is saved on the Pi, without stream addresses or identifiers.", "capture_situation": "Situation", "capture_btn": "Capture state", "capture_done": "Capture saved", "capture_failed": "Eversolo unreachable: capture impossible.", "capture_busy": "A capture is already running.", "captures_list": "Saved captures",
        "sit_fichier": "Local file", "sit_pause": "Paused", "sit_muet": "Muted", "sit_autre": "Other",
    },
    "es": {
        "setup_title": "Configuración inicial",
        "setup_intro": "Elija una contraseña de administrador e indique su streamer.",
        "password": "Contraseña de administrador",
        "password_confirm": "Confirmar contraseña",
        "password_short": "Minimo 8 caractères.",
        "password_mismatch": "Las contraseñas no coinciden.",
        "device_ip": "Dirección IP del streamer",
        "detect": "Detectar en la red",
        "detecting": "Buscando...",
        "detect_none": "No se encontro ningún streamer. Introduzca la IP manualmente.",
        "language": "Idioma",
        "save": "Guardar", "maj_deja": "Ya hay una actualización en curso.",
        "maj_installee": "Versión en servicio", "maj_disponible": "Nueva versión", "maj_installer": "Instalar esta versión", "maj_revenir": "Volver a la versión anterior", "maj_pendant_lecture": "Pause la reproducción antes de actualizar.", "maj_rien": "No hay ninguna versión nueva.", "maj_lancee": "Instalación iniciada: descarga, verificación de la firma y reinicio. La pantalla se recargará sola.", "maj_retour_lance": "Volviendo a la versión anterior: el servidor se reinicia.", "maj_etape_telechargement": "Descargando", "maj_etape_verification": "Verificando la firma", "maj_etape_installation": "Instalando", "maj_tv": "Actualización",
        "disp_title": "Pantalla", "disp_intro": "Ajuste la pantalla a la distancia de lectura.", "disp_theme": "Interfaz", "theme_pochette": "Portada: la pantalla toma el color del disco", "theme_console": "Consola: frontal de aparato, pantalla fluorescente", "theme_affiche": "Cartel: tipografía grande, papel y tinta", "theme_cadre": "Pantalla completa: la portada ocupa un lado entero", "disp_profil": "Tipo de pantalla", "profil_salon": "Salón: TV leída a 3-4 m", "profil_bureau": "Escritorio: pantalla cercana", "profil_petit": "Pantalla pequeña de 7 a 10 pulgadas", "disp_nuit": "Modo noche (brillo reducido)", "nuit_auto": "Según la hora", "nuit_jamais": "Nunca", "nuit_toujours": "Siempre", "nuit_de": "Noche de las", "nuit_a": "h a las", "nuit_h": "h", "disp_protection": "Proteger la pantalla: ligero desplazamiento, atenuación tras 10 min de pausa, negro tras 30 min", "disp_save": "Guardar la pantalla",
        "login_title": "Iniciar sesión",
        "login": "Iniciar sesión",
        "logout": "Cerrar sesión",
        "bad_password": "Contraseña incorrecta.",
        "locked": "Demasiados intentos. Vuelva a intentarlo en unos minutos.",
        "config_title": "Ajustes",
        "current_password": "Contraseña actual",
        "new_password": "Nueva contraseña (dejar vacio para conservar)",
        "saved": "Guardado.",
        "back_display": "Volver a la pantalla",
        "invalid_ip": "Dirección IP no valida.",
        "blaster_title": "Emisor infrarrojo", "blaster_intro": "Grabe teclas de sus mandos, la Pi podra reemitirlas (TV, ampli...).", "new_name": "Nombre del comando (ej: tv_power)", "learn": "Aprender", "send_cmd": "Enviar", "delete_cmd": "Eliminar", "learn_hint": "Pulse ahora la tecla a aprender, frente al sensor...", "learned": "Comando grabado.", "learn_failed": "No se recibió nada. Compruebe el sensor y reintente.", "no_tx": "Emisor no encontrado (opción --ir-tx instalada y reinicio hecho?).", "bad_name": "Nombre no valido: letras, cifras, guion, 32 caractères max.", "blaster_link": "Emisor infrarrojo",
        "hw_title": "Hardware infrarrojo", "hw_pin": "Pin de la Raspberry", "hw_leg": "Pata del sensor", "hw_signal": "Señal (OUT / S)", "hw_gnd": "Masa (GND / -)", "hw_vcc": "Alimentacion (VCC / +)", "hw_note": "Sensor VS1838B o TSOP38238, cupula hacia usted, patas abajo: OUT izquierda, GND centro, VCC derecha. Fiese de las etiquetas si el sensor esta en un modulo.", "hw_rx_ok": "Receptor detectado", "hw_rx_ko": "Receptor no detectado: revise el cableado, luego ./install.sh --ir y reinicie.", "hw_tx_ok": "Emisor detectado", "hw_tx_ko": "Emisor no instalado (opcional).", "hw_test": "Probar el sensor", "hw_test_wait": "Pulse una tecla...", "hw_test_ok": "Señal recibida, sensor operativo.", "hw_test_ko": "Ninguna señal en 15 s.",
        "no_bio": "No se encontró ninguna biografía de este artista en las fuentes consultadas.",
        "tadb_key": "Clave TheAudioDB (respaldo de biografías, clave de prueba por defecto)", "lastfm_key": "Clave API Last.fm (respaldo de biografías, opcional)",
        "searching": "Buscando información del artista y del disco...",
        "discogs_token": "Token de Discogs (créditos de producción detallados, opcional)",
        "maj_ancienne": "Actualizaciones: ejecute ./update.sh una vez en la Pi para pasar a las versiones firmadas", "up_to_date": "Aplicación al día",
        "genius_token_lbl": "Token Genius (créditos de la pista en curso, opcional)",
        "remote_title": "Mando a distancia", "remote_intro": "Pulse Asociar y luego la tecla deseada en su mando.", "pair": "Asociar", "press_key": "Pulse una tecla...", "clear": "Quitar", "not_paired": "Sin asociar", "act_play_pause": "Reproducir / Pausa", "act_next": "Siguiente", "act_previous": "Anterior", "act_vol_up": "Volumen +", "act_vol_down": "Volumen -", "act_info": "Info del artista", "act_mute": "Silencio", "remote_link": "Mando infrarrojo",
        "session_expired": "Sesión caducada, inicie sesión de nuevo.",
        "code_label": "Código mostrado en la TV", "code_bad": "Código incorrecto. Copie el código mostrado en la TV.", "code_first": "Introduzca primero el código mostrado en la TV.",
        "tv_setup_intro": "En su teléfono u ordenador, abra", "tv_setup_code": "e introduzca este código", "tv_setup_here": "Configurar desde esta pantalla",
        "host_refused": "Dirección no reconocida. Abra la página con la dirección IP de la Pi (por ejemplo http://{ip}:{port}) o añada este nombre a la lista hotes_autorises de config.json.",
        "capture_title": "Captura del estado", "capture_intro": "Inicie una reproducción en el Eversolo, elija la situación y capture. Lo que devuelve el Eversolo se guarda en la Pi, sin direcciones de flujo ni identificadores.", "capture_situation": "Situación", "capture_btn": "Capturar el estado", "capture_done": "Captura guardada", "capture_failed": "Eversolo inaccesible: captura imposible.", "capture_busy": "Ya hay una captura en curso.", "captures_list": "Capturas guardadas",
        "sit_fichier": "Archivo local", "sit_pause": "Pausa", "sit_muet": "Silencio", "sit_autre": "Otra",
    },
    "de": {
        "setup_title": "Ersteinrichtung",
        "setup_intro": "Administrator-Passwort festlegen und Streamer angeben.",
        "password": "Administrator-Passwort",
        "password_confirm": "Passwort bestätigen",
        "password_short": "Mindestens 8 Zeichen.",
        "password_mismatch": "Die Passwörter stimmen nicht überein.",
        "device_ip": "IP-Adresse des Streamers",
        "detect": "Im Netzwerk suchen",
        "detecting": "Suche läuft...",
        "detect_none": "Kein Streamer gefunden. IP manuell eingeben.",
        "language": "Sprache",
        "save": "Speichern", "maj_deja": "Ein Update läuft bereits.",
        "maj_installee": "Laufende Version", "maj_disponible": "Neue Version", "maj_installer": "Diese Version installieren", "maj_revenir": "Zur vorherigen Version zurück", "maj_pendant_lecture": "Pausieren Sie die Wiedergabe vor dem Update.", "maj_rien": "Keine neue Version verfügbar.", "maj_lancee": "Installation gestartet: Download, Signaturprüfung, dann Neustart. Der Bildschirm lädt sich selbst neu.", "maj_retour_lance": "Zurück zur vorherigen Version: der Server startet neu.", "maj_etape_telechargement": "Wird heruntergeladen", "maj_etape_verification": "Signatur wird geprüft", "maj_etape_installation": "Wird installiert", "maj_tv": "Update",
        "disp_title": "Anzeige", "disp_intro": "Passen Sie den Bildschirm an den Betrachtungsabstand an.", "disp_theme": "Oberfläche", "theme_pochette": "Cover: der Bildschirm nimmt die Farbe des Albums an", "theme_console": "Konsole: Gerätefront, Fluoreszenzanzeige", "theme_affiche": "Plakat: große Typografie, Papier und Tinte", "theme_cadre": "Vollbild: das Cover füllt eine Bildschirmseite", "disp_profil": "Bildschirmtyp", "profil_salon": "Wohnzimmer: TV aus 3-4 m", "profil_bureau": "Schreibtisch: naher Bildschirm", "profil_petit": "Kleiner Bildschirm 7 bis 10 Zoll", "disp_nuit": "Nachtmodus (reduzierte Helligkeit)", "nuit_auto": "Nach Uhrzeit", "nuit_jamais": "Nie", "nuit_toujours": "Immer", "nuit_de": "Nacht von", "nuit_a": "Uhr bis", "nuit_h": "Uhr", "disp_protection": "Bildschirm schonen: leichte Verschiebung, Abdunkeln nach 10 Min. Pause, schwarz nach 30 Min.", "disp_save": "Anzeige speichern",
        "login_title": "Anmelden",
        "login": "Anmelden",
        "logout": "Abmelden",
        "bad_password": "Falsches Passwort.",
        "locked": "Zu viele Versuche. In einigen Minuten erneut versuchen.",
        "config_title": "Einstellungen",
        "current_password": "Aktuelles Passwort",
        "new_password": "Neues Passwort (leer lassen zum Beibehalten)",
        "saved": "Gespeichert.",
        "back_display": "Zurück zur Anzeige",
        "invalid_ip": "Ungültige IP-Adresse.",
        "blaster_title": "Infrarot-Sender", "blaster_intro": "Tasten Ihrer Fernbedienungen aufnehmen, der Pi kann sie wieder senden (TV, Verstärker...).", "new_name": "Name des Befehls (z.B. tv_power)", "learn": "Anlernen", "send_cmd": "Senden", "delete_cmd": "Löschen", "learn_hint": "Jetzt die Taste drücken, zum Sensor gerichtet...", "learned": "Befehl gespeichert.", "learn_failed": "Nichts empfangen. Sensor prüfen und erneut versuchen.", "no_tx": "Sender nicht gefunden (--ir-tx installiert und neu gestartet?).", "bad_name": "Ungültiger Name: Buchstaben, Ziffern, Bindestrich, max. 32 Zeichen.", "blaster_link": "Infrarot-Sender",
        "hw_title": "Infrarot-Hardware", "hw_pin": "Raspberry-Pin", "hw_leg": "Sensor-Bein", "hw_signal": "Signal (OUT / S)", "hw_gnd": "Masse (GND / -)", "hw_vcc": "Versorgung (VCC / +)", "hw_note": "Sensor VS1838B oder TSOP38238, Wölbung zu Ihnen, Beine nach unten: OUT links, GND Mitte, VCC rechts. Bei Modulen den Aufdrucken folgen.", "hw_rx_ok": "Empfänger erkannt", "hw_rx_ko": "Empfänger nicht erkannt: Verkabelung prüfen, dann ./install.sh --ir und Neustart.", "hw_tx_ok": "Sender erkannt", "hw_tx_ko": "Sender nicht installiert (optional).", "hw_test": "Sensor testen", "hw_test_wait": "Taste drücken...", "hw_test_ok": "Signal empfangen, Sensor funktioniert.", "hw_test_ko": "Kein Signal innerhalb von 15 s.",
        "no_bio": "Keine Biografie zu diesem Künstler in den verfügbaren Quellen gefunden.",
        "tadb_key": "TheAudioDB-Schlüssel (Biografie-Ausweichquelle, Testschlüssel als Standard)", "lastfm_key": "Last.fm-API-Schlüssel (Biografie-Ausweichquelle, optional)",
        "searching": "Informationen zu Künstler und Album werden gesucht...",
        "discogs_token": "Discogs-Token (detaillierte Produktions-Credits, optional)",
        "maj_ancienne": "Aktualisierungen: führen Sie einmal ./update.sh auf dem Pi aus, um auf signierte Versionen umzustellen", "up_to_date": "Anwendung aktuell",
        "genius_token_lbl": "Genius-Token (Credits des laufenden Titels, optional)",
        "remote_title": "Fernbedienung", "remote_intro": "Auf Anlernen klicken und dann die gewünschte Taste drücken.", "pair": "Anlernen", "press_key": "Taste drücken...", "clear": "Entfernen", "not_paired": "Nicht angelernt", "act_play_pause": "Wiedergabe / Pause", "act_next": "Weiter", "act_previous": "Zurück", "act_vol_up": "Lauter", "act_vol_down": "Leiser", "act_info": "Künstler-Info", "act_mute": "Stumm", "remote_link": "Infrarot-Fernbedienung",
        "session_expired": "Sitzung abgelaufen, bitte erneut anmelden.",
        "code_label": "Am Fernseher angezeigter Code", "code_bad": "Falscher Code. Übernehmen Sie den am Fernseher angezeigten Code.", "code_first": "Geben Sie zuerst den am Fernseher angezeigten Code ein.",
        "tv_setup_intro": "Öffnen Sie auf Ihrem Telefon oder Computer", "tv_setup_code": "und geben Sie diesen Code ein", "tv_setup_here": "Auf diesem Bildschirm einrichten",
        "host_refused": "Unbekannte Adresse. Öffnen Sie die Seite über die IP-Adresse des Pi (zum Beispiel http://{ip}:{port}) oder tragen Sie diesen Namen in die Liste hotes_autorises von config.json ein.",
        "capture_title": "Zustandserfassung", "capture_intro": "Starten Sie die Wiedergabe am Eversolo, wählen Sie die Situation und erfassen Sie. Die Antwort des Eversolo wird auf dem Pi gespeichert, ohne Stream-Adressen oder Kennungen.", "capture_situation": "Situation", "capture_btn": "Zustand erfassen", "capture_done": "Erfassung gespeichert", "capture_failed": "Eversolo nicht erreichbar: Erfassung unmöglich.", "capture_busy": "Eine Erfassung läuft bereits.", "captures_list": "Gespeicherte Erfassungen",
        "sit_fichier": "Lokale Datei", "sit_pause": "Pause", "sit_muet": "Stumm", "sit_autre": "Andere",
    },
}

TEXTES_REGLAGES = {
    "fr": {"sec_streamer": "Streamer", "sec_streamer_intro": "Adresse de l'Eversolo sur le réseau local et langue des textes.",
           "sec_sources": "Sources d'informations", "sec_sources_intro": "Biographies, crédits et studios. Tout fonctionne sans clé ; ces clés gratuites ajoutent des fiches.",
           "sec_compte": "Mot de passe", "sec_compte_intro": "Laissez vide pour garder le mot de passe actuel. Le changer déconnecte les autres appareils.",
           "sec_maj": "Mise à jour", "get_key": "Obtenir une clé"},
    "en": {"sec_streamer": "Streamer", "sec_streamer_intro": "Address of the Eversolo on the local network and language of the texts.",
           "sec_sources": "Information sources", "sec_sources_intro": "Biographies, credits and studios. Everything works without keys; these free keys add more.",
           "sec_compte": "Password", "sec_compte_intro": "Leave empty to keep the current password. Changing it signs out other devices.",
           "sec_maj": "Update", "get_key": "Get a key"},
    "es": {"sec_streamer": "Streamer", "sec_streamer_intro": "Dirección del Eversolo en la red local e idioma de los textos.",
           "sec_sources": "Fuentes de información", "sec_sources_intro": "Biografías, créditos y estudios. Todo funciona sin claves; estas claves gratuitas añaden fichas.",
           "sec_compte": "Contraseña", "sec_compte_intro": "Déjelo vacío para conservar la contraseña actual. Cambiarla cierra la sesión en los demás aparatos.",
           "sec_maj": "Actualización", "get_key": "Obtener una clave"},
    "de": {"sec_streamer": "Streamer", "sec_streamer_intro": "Adresse des Eversolo im lokalen Netz und Sprache der Texte.",
           "sec_sources": "Informationsquellen", "sec_sources_intro": "Biografien, Credits und Studios. Alles funktioniert ohne Schlüssel; diese kostenlosen Schlüssel ergänzen Einträge.",
           "sec_compte": "Passwort", "sec_compte_intro": "Leer lassen, um das aktuelle Passwort zu behalten. Eine Änderung meldet andere Geräte ab.",
           "sec_maj": "Aktualisierung", "get_key": "Schlüssel erhalten"},
}
for _langue, _textes in TEXTES_REGLAGES.items():
    T[_langue].update(_textes)


# ------------------------------------------------------------- configuration


def ecrire_json(path, data, mode=0o600):
    """Écriture atomique: fichier temporaire, fsync puis renommage. Une coupure
    de courant laisse l'ancien fichier intact au lieu d'un fichier vide."""
    temporaire = path + ".tmp"
    fd = os.open(temporaire, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(temporaire, mode)
    os.replace(temporaire, path)


def load_config():
    config = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            lu = json.load(f)
        if isinstance(lu, dict):
            config.update(lu)
    except FileNotFoundError:
        pass
    except (OSError, ValueError):
        # Fichier illisible (coupure de courant): on démarre sur les valeurs
        # par défaut plutôt que de planter en boucle; /config permet de refaire
        # le réglage.
        print("[config] config.json illisible, valeurs par défaut utilisées", flush=True)
    return config


def save_config(config):
    ecrire_json(CONFIG_PATH, config)


def load_auth():
    """None seulement si aucun mot de passe n'a jamais été créé. Un fichier
    illisible renvoie {}: /setup reste fermé (sinon le premier venu sur le
    réseau reprendrait la main) et le mot de passe se redéfinit avec
    tools/motdepasse.py."""
    try:
        with open(AUTH_PATH, "r", encoding="utf-8") as f:
            lu = json.load(f)
        return lu if isinstance(lu, dict) else {}
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        print("[auth] auth.json illisible: tools/motdepasse.py nouveau ...", flush=True)
        return {}


def save_auth(password_hash):
    ecrire_json(AUTH_PATH, {"password_hash": password_hash})


def password_ok(password):
    stored = (load_auth() or {}).get("password_hash", "")
    if not stored:
        return False
    try:
        return check_password_hash(stored, password)
    except ValueError:
        return False


def get_secret_key():
    try:
        with open(SECRET_PATH, "rb") as f:
            key = f.read()
            if len(key) >= 32:
                return key
    except FileNotFoundError:
        pass
    key = secrets.token_bytes(32)
    fd = os.open(SECRET_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key)
    return key


CONFIG = load_config()

app = Flask(__name__, static_folder=os.path.join(BASE_DIR, "static"))
app.secret_key = get_secret_key()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    PERMANENT_SESSION_LIFETIME=12 * 3600,
    MAX_CONTENT_LENGTH=16 * 1024,
)

http = requests.Session()
http.headers.update({"User-Agent": "eversolo-screen/1.0 (Raspberry Pi; affichage hifi local)"})

MODEL_CACHE = {"ip": None, "name": "", "quand": 0.0}
MODELE_NOUVEL_ESSAI = 60  # secondes avant de redemander un modèle resté sans réponse


def device_model(ip=None, port=None):
    """Nom du modèle (DMP-A6, A8, A10...), mis en cache par adresse.
    Un échec est gardé une minute : sans cela chaque relevé de l'écran
    referait la demande et attendrait son délai."""
    ip = ip or CONFIG.get("eversolo_ip")
    port = port or CONFIG.get("eversolo_port", 9529)
    if not ip:
        return ""
    if MODEL_CACHE["ip"] == ip:
        if MODEL_CACHE["name"]:
            return MODEL_CACHE["name"]
        if time.time() - MODEL_CACHE["quand"] < MODELE_NOUVEL_ESSAI:
            return ""
    try:
        r = http.get(f"http://{ip}:{port}/ControlCenter/getModel", timeout=2)
        name = r.json().get("model", "") if r.ok else ""
    except Exception:
        name = ""
    MODEL_CACHE.update({"ip": ip, "name": name, "quand": time.time()})
    return name

# ------------------------------------------------------------ anti force brute

ACTIONS = {
    "play_pause": "/ZidooMusicControl/v2/playOrPause",
    "next": "/ZidooMusicControl/v2/playNext",
    "previous": "/ZidooMusicControl/v2/playLast",
    "vol_up": "/ZidooControlCenter/RemoteControl/sendkey?key=Key.VolumeUp",
    "vol_down": "/ZidooControlCenter/RemoteControl/sendkey?key=Key.VolumeDown",
}
MUTE_STATE = {"muted": False}
LAST_IR = {"code": None, "time": 0.0}


def do_action(action):
    """Envoie une commande de pilotage à l'Eversolo."""
    if not CONFIG.get("eversolo_ip"):
        return False
    if action in ("next", "previous") and ARTIST_PANEL["until"] > time.time():
        # volet ouvert: on tourne les pages au lieu de changer de plage
        ordre = ["artist", "album", "prod"]
        i = ordre.index(ARTIST_PANEL.get("page", "artist"))
        i = min(len(ordre) - 1, i + 1) if action == "next" else max(0, i - 1)
        ARTIST_PANEL["page"] = ordre[i]
        ARTIST_PANEL["scroll"] = 0
        ARTIST_PANEL["scroll_max"] = None  # nouvelle page : l'écran redira sa longueur
        ARTIST_PANEL["until"] = time.time() + 60
        return True
    if action in ("vol_up", "vol_down") and ARTIST_PANEL["until"] > time.time():
        # volet ouvert: les volumes defilent le texte au lieu d'agir sur le son
        delta = -1 if action == "vol_up" else 1
        plafond = ARTIST_PANEL.get("scroll_max")
        nouveau = max(0, ARTIST_PANEL["scroll"] + delta)
        ARTIST_PANEL["scroll"] = min(nouveau, plafond) if plafond is not None else nouveau
        ARTIST_PANEL["until"] = time.time() + 60
        return True
    if action == "info":
        return toggle_artist_panel()
    if action == "mute":
        # L'état réel prime : on a pu couper le son depuis l'appli Eversolo.
        info = STATE_CACHE.get("info") or {}
        volume = info.get("volume")
        reel = volume.get("muet") if volume else None
        actuel = MUTE_STATE["muted"] if reel is None else reel
        MUTE_STATE["muted"] = not actuel
        if volume:
            # Deux appuis rapprochés : le second part de l'état visé, pas
            # d'un relevé vieux d'une seconde.
            STATE_CACHE["info"] = {**info, "volume": {**volume, "muet": MUTE_STATE["muted"]}}
        url = f"{eversolo_base()}/ZidooMusicControl/v2/setMuteVolume?isMute={1 if MUTE_STATE['muted'] else 0}"
    elif action in ACTIONS:
        url = f"{eversolo_base()}{ACTIONS[action]}"
    else:
        return False
    try:
        http.get(url, timeout=3)
        return True
    except Exception:
        return False


IR_CODES_DIR = os.path.join(DATA_DIR, "ir_codes")
NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,32}")


def lirc_devices():
    """Detecte les peripheriques infrarouges: (récepteur, émetteur)."""
    rx = tx = None
    for dev in sorted(glob.glob("/dev/lirc*")):
        try:
            out = subprocess.run(
                ["ir-ctl", "-d", dev, "--features"],
                capture_output=True, text=True, timeout=5,
            ).stdout.lower()
        except Exception:
            continue
        if rx is None and "receive" in out:
            rx = dev
        if tx is None and "send" in out:
            tx = dev
    return rx, tx


def record_raw(path, timeout_s=15):
    """Enregistre une pression de touche en signal brut (tous protocoles)."""
    rx, _ = lirc_devices()
    if not rx:
        return False
    try:
        subprocess.run(
            ["ir-ctl", "-d", rx, "-1", "--receive=" + path],
            timeout=timeout_s, capture_output=True,
        )
    except subprocess.TimeoutExpired:
        pass
    return os.path.exists(path) and os.path.getsize(path) > 0


def send_raw(path):
    """Rejoue un signal enregistre via la LED émettrice."""
    _, tx = lirc_devices()
    if not tx or not os.path.exists(path):
        return False
    try:
        subprocess.run(["ir-ctl", "-d", tx, "--send=" + path], timeout=8)
        return True
    except Exception:
        return False


ARTIST_CACHE = {}
ARTIST_PANEL = {"until": 0.0, "data": None, "scroll": 0, "page": "artist"}


TADB_CLE_GRATUITE = "123"
TADB_CLES_PERIMEES = {"", "1", "2"}  # anciennes clés d'essai, refusées par le service


def cle_theaudiodb():
    cle = (CONFIG.get("theaudiodb_key") or "").strip()
    return TADB_CLE_GRATUITE if cle in TADB_CLES_PERIMEES else cle


def _entetes_api():
    return {"User-Agent": "eversolo-screen/1.0 (affichage hifi local)"}


def _cache_valide(entree):
    """Succès gardés 24 h; échecs retentés après 2 minutes seulement."""
    if not entree:
        return False
    ts, valeur = entree
    return time.time() - ts < (259200 if valeur else 120)


_MB_DERNIER = {"t": 0.0}
_MB_VERROU = threading.Lock()


def _mb_get(url, **kwargs):
    """Appel MusicBrainz espacé (1 requête/s, sa limite), sérialisé entre les
    fils paralleles, et réessayé sur 503."""
    r = None
    for tentative in range(2):
        with _MB_VERROU:
            pause = _MB_DERNIER["t"] + 1.0 - time.time()
            if pause > 0:
                time.sleep(min(pause, 1.0))
            _MB_DERNIER["t"] = time.time()
            r = http.get(url, **kwargs)
        if getattr(r, "status_code", 200) == 503 and tentative == 0:
            time.sleep(1.2)
            continue
        return r
    return r


def _couper(texte, maxi=2600):
    texte = texte.strip()
    if len(texte) <= maxi:
        return texte
    coupe = texte[:maxi]
    point = coupe.rfind(". ")
    return coupe[:point + 1] if point > maxi // 2 else coupe


def musicbrainz_artist(artist, album=None):
    """Identité via MusicBrainz: faits (genre, période, pays), lien Wikidata,
    et nom canonique. Quand on connaît le disque, on identifie par le disque:
    c'est ce qui distingue deux artistes homonymes (Leon Thomas / Leon Thomas III).
    """
    try:
        a = None
        if album:
            try:
                groupe = _mb_release_group(artist, album)
                credit = (groupe.get("artist-credit") or [{}])[0].get("artist") if groupe else None
                if credit and credit.get("id"):
                    r2 = _mb_get(
                        f"https://musicbrainz.org/ws/2/artist/{credit['id']}",
                        params={"inc": "url-rels+tags", "fmt": "json"},
                        headers=_entetes_api(), timeout=4,
                    )
                    a = r2.json()
                    a.setdefault("id", credit["id"])
                    a["relations"] = a.get("relations") or []
                    a["_rels_incluses"] = True
            except Exception:
                a = None
        if a is None:
            r = _mb_get(
                "https://musicbrainz.org/ws/2/artist/",
                params={"query": f'artist:"{artist}"', "fmt": "json", "limit": 1},
                headers=_entetes_api(), timeout=4,
            )
            artists = r.json().get("artists") or []
            if not artists:
                return None
            a = artists[0]
        facts = []
        tags = sorted(a.get("tags") or [], key=lambda t: -t.get("count", 0))
        if tags:
            facts.append(tags[0]["name"].capitalize())
        span = a.get("life-span") or {}
        begin = (span.get("begin") or "")[:4]
        end_ = (span.get("end") or "")[:4]
        if begin:
            facts.append(f"{begin}–{end_}" if end_ else begin)
        area = (a.get("area") or {}).get("name") or a.get("country")
        if area:
            facts.append(area)
        qid = None
        try:
            rels = a.get("relations") if a.get("_rels_incluses") else None
            if rels is None:
                r2 = _mb_get(
                    f"https://musicbrainz.org/ws/2/artist/{a['id']}",
                    params={"inc": "url-rels", "fmt": "json"},
                    headers=_entetes_api(), timeout=4,
                )
                rels = r2.json().get("relations") or []
            for rel in rels:
                if rel.get("type") == "wikidata":
                    qid = rel.get("url", {}).get("resource", "").rstrip("/").rsplit("/", 1)[-1]
                    break
        except Exception:
            pass
        return {"facts": facts[:3], "qid": qid, "name": a.get("name")}
    except Exception:
        return None


def wikidata_titre(qid, lang):
    """Titre exact de l'article Wikipédia via Wikidata, repli anglais."""
    try:
        r = http.get(
            "https://www.wikidata.org/w/api.php",
            params={"action": "wbgetentities", "ids": qid, "props": "sitelinks",
                    "sitefilter": f"{lang}wiki|enwiki", "format": "json"},
            headers=_entetes_api(), timeout=4,
        )
        links = (r.json().get("entities", {}).get(qid) or {}).get("sitelinks", {})
        for site, wl in ((f"{lang}wiki", lang), ("enwiki", "en")):
            if site in links:
                return links[site]["title"], wl
    except Exception:
        pass
    return None, lang


def _wiki_resume(title, wl):
    r = http.get(
        f"https://{wl}.wikipedia.org/api/rest_v1/page/summary/"
        + requests.utils.quote(title, safe=""),
        headers=_entetes_api(), timeout=4,
    )
    return r.json()


def _wiki_intro(title, wl):
    r = http.get(
        f"https://{wl}.wikipedia.org/w/api.php",
        params={"action": "query", "prop": "extracts", "explaintext": 1,
                "exintro": 1, "redirects": 1, "format": "json", "titles": title},
        headers=_entetes_api(), timeout=5,
    )
    for p in (r.json().get("query", {}).get("pages", {}) or {}).values():
        return (p.get("extract") or "").strip()
    return ""


def _wiki_data(artist, title, wl, facts, via):
    j = _wiki_resume(title, wl)
    extract = (j.get("extract") or "").strip()
    try:
        longue = _wiki_intro(title, wl)
        if len(longue) > len(extract):
            extract = longue
    except Exception:
        pass
    extract = _couper(extract)
    if not extract:
        return None
    thumb = (j.get("thumbnail") or {}).get("source")
    return {
        "artist": artist, "text": extract,
        "image": thumb or None,
        "facts": facts, "source": f"Wikipedia ({wl}){via}",
    }


MOTS_MUSIQUE = (
    "musi", "chant", "groupe", "band", "singer", "rapp", "composit", "composer",
    "dj", "produc", "guitar", "pian", "trompett", "saxo", "batteur", "drummer",
    "songwriter", "s\u00e4nger", "cantante", "grupo", "banda", "orchestr",
    "soprano", "tenor", "violon", "violin",
)


def _parle_de_musique(texte):
    texte = (texte or "").lower()
    return any(mot in texte for mot in MOTS_MUSIQUE)


def _wiki_recherche(artist, lang, facts):
    """Ancien chemin: recherche filtrée musique, quand Wikidata n'a pas aidé."""
    def chercher(query):
        r = http.get(
            f"https://{lang}.wikipedia.org/w/rest.php/v1/search/page",
            params={"q": query, "limit": 5}, headers=_entetes_api(), timeout=4,
        )
        return r.json().get("pages") or []

    try:
        title = None
        for tentative in (artist, f"{artist} musique groupe"):
            for page in chercher(tentative):
                if _parle_de_musique(page.get("description", "")):
                    title = page["title"]
                    break
            if title:
                break
        if not title:
            return None
        data = _wiki_data(artist, title, lang, facts, "")
        if data and not _parle_de_musique(data["text"]):
            return None
        return data
    except Exception:
        return None


def theaudiodb_bio(artist, lang, facts):
    key = cle_theaudiodb()
    try:
        r = http.get(
            f"https://www.theaudiodb.com/api/v1/json/{key}/search.php",
            params={"s": artist}, headers=_entetes_api(), timeout=5,
        )
        artists = (r.json() or {}).get("artists") or []
        if not artists:
            return None
        a = artists[0]
        bio = (a.get(f"strBiography{lang.upper()}") or a.get("strBiographyEN") or "").strip()
        if len(bio) < 40:
            return None
        img = a.get("strArtistThumb") or a.get("strArtistFanart")
        return {
            "artist": artist, "text": _couper(bio),
            "image": img or None,
            "facts": facts, "source": "TheAudioDB",
        }
    except Exception:
        return None


def lastfm_bio(artist, lang, facts):
    key = (CONFIG.get("lastfm_api_key") or "").strip()
    if not key:
        return None
    try:
        r = http.get(
            "https://ws.audioscrobbler.com/2.0/",
            params={"method": "artist.getinfo", "artist": artist, "api_key": key,
                    "format": "json", "lang": lang, "autocorrect": 1},
            headers=_entetes_api(), timeout=5,
        )
        a = (r.json() or {}).get("artist") or {}
        bio = ((a.get("bio") or {}).get("content") or "")
        bio = re.sub(r"<a href=[^>]*>.*$", "", bio, flags=re.S)
        bio = re.sub(r"<[^>]+>", "", bio).strip()
        if len(bio) < 40:
            return None
        return {"artist": artist, "text": _couper(bio), "image": None,
                "facts": facts, "source": "Last.fm"}
    except Exception:
        return None


ALBUM_CACHE = {}


ROLES_CREDITS = {
    "producer": {"fr": "Production", "en": "Producer", "es": "Producción", "de": "Produktion"},
    "engineer": {"fr": "Ingénieur du son", "en": "Engineer", "es": "Ingeniero de sonido", "de": "Toningenieur"},
    "mix": {"fr": "Mixage", "en": "Mixing", "es": "Mezcla", "de": "Mischung"},
    "mastering": {"fr": "Mastering", "en": "Mastering", "es": "Masterización", "de": "Mastering"},
    "recording": {"fr": "Prise de son", "en": "Recording", "es": "Grabación", "de": "Aufnahme"},
    "performer": {"fr": "Interprète", "en": "Performer", "es": "Intérprete", "de": "Interpret"},
    "vocal": {"fr": "Chant", "en": "Vocals", "es": "Voz", "de": "Gesang"},
    "writing": {"fr": "Écriture", "en": "Writing", "es": "Escritura", "de": "Komposition"},
}


def _mb_release_details(rgid, lang):
    """Plages, crédits (deux niveaux: disque et enregistrements) et faits de
    production (label, date, studios) d'un disque."""
    tracks, credits, prod_facts = [], [], []
    try:
        r = _mb_get(
            "https://musicbrainz.org/ws/2/release/",
            params={"release-group": rgid, "fmt": "json", "limit": 1, "inc": "labels"},
            headers=_entetes_api(), timeout=4,
        )
        releases = r.json().get("releases") or []
        if not releases:
            return tracks, credits, prod_facts
        rel0 = releases[0]
        date = rel0.get("date") or ""
        labels = [li["label"]["name"] for li in rel0.get("label-info") or []
                  if li.get("label", {}).get("name")]

        r2 = _mb_get(
            f"https://musicbrainz.org/ws/2/release/{rel0['id']}",
            params={"inc": "recordings+artist-rels+recording-level-rels+place-rels",
                    "fmt": "json"},
            headers=_entetes_api(), timeout=6,
        )
        j = r2.json()

        vus, studios = set(), []

        def ajouter(rel):
            typ = rel.get("type")
            lieu = (rel.get("place") or {}).get("name")
            if lieu and typ and typ.endswith(" at") and lieu not in studios:
                studios.append(lieu)
                return
            nom = (rel.get("artist") or {}).get("name")
            if not nom:
                return
            if typ == "instrument":
                attrs = rel.get("attributes") or []
                role = attrs[0].capitalize() if attrs else "Instrument"
            elif typ in ROLES_CREDITS:
                role = ROLES_CREDITS[typ].get(lang, ROLES_CREDITS[typ]["en"])
            else:
                return
            if (role, nom) not in vus:
                vus.add((role, nom))
                credits.append({"role": role, "name": nom})

        for rel in j.get("relations") or []:
            ajouter(rel)
        n = 0
        for media in j.get("media") or []:
            for t in media.get("tracks") or []:
                n += 1
                ms = t.get("length") or (t.get("recording") or {}).get("length")
                duree = f"{ms // 60000}:{(ms // 1000) % 60:02d}" if ms else ""
                tracks.append({"n": n, "title": t.get("title") or "", "dur": duree})
                for rel in (t.get("recording") or {}).get("relations") or []:
                    ajouter(rel)

        pass
        for lab in labels[:1]:
            prod_facts.append(lab)
        if date:
            prod_facts.append(date)
        for st in studios[:2]:
            prod_facts.append(st)
    except Exception:
        pass
    return tracks, credits, prod_facts


def _grouper_credits(bruts):
    """Une ligne par métier: Production - A, B, C."""
    groupes, ordre = {}, []
    for c in bruts:
        if c["role"] not in groupes:
            groupes[c["role"]] = []
            ordre.append(c["role"])
        if c["name"] not in groupes[c["role"]]:
            groupes[c["role"]].append(c["name"])
    return [{"role": r, "name": ", ".join(groupes[r][:8])} for r in ordre][:10]


def discogs_credits(artist, album, lang):
    """Crédits de production via Discogs, la référence des livrets, jeton requis."""
    token = (CONFIG.get("discogs_token") or "").strip()
    if not token:
        return []
    try:
        r = http.get(
            "https://api.discogs.com/database/search",
            params={"artist": artist, "release_title": album, "type": "release",
                    "per_page": 1, "token": token},
            headers=_entetes_api(), timeout=5,
        )
        resultats = (r.json() or {}).get("results") or []
        if not resultats:
            return []
        r2 = http.get(
            f"https://api.discogs.com/releases/{resultats[0]['id']}",
            params={"token": token}, headers=_entetes_api(), timeout=6,
        )
        j = r2.json() or {}
        CORRESPONDANCES = {
            "producer": "producer", "co-producer": "producer",
            "executive-producer": "producer", "executive producer": "producer",
            "mixed by": "mix", "mastered by": "mastering",
            "recorded by": "recording", "engineer": "engineer",
        }
        bruts = []
        sources = list(j.get("extraartists") or [])
        for piste in j.get("tracklist") or []:
            sources.extend(piste.get("extraartists") or [])
        for ea in sources:
            nom = re.sub(r" \(\d+\)$", "", (ea.get("name") or "").strip())
            if not nom:
                continue
            # Discogs cumule les metiers ("Recorded By, Mixed By"): un par un
            for role_brut in (ea.get("role") or "").split(","):
                role_brut = role_brut.strip()
                if not role_brut:
                    continue
                cle = role_brut.lower()
                correspondance = None
                for motif, typ in CORRESPONDANCES.items():
                    if motif in cle:
                        correspondance = typ
                        break
                if correspondance:
                    role = ROLES_CREDITS[correspondance].get(lang, ROLES_CREDITS[correspondance]["en"])
                elif "written" in cle or "management" in cle or "art" in cle or "photo" in cle:
                    continue
                else:
                    role = role_brut
                bruts.append({"role": role, "name": nom})
        return bruts
    except Exception:
        return []


def fetch_album_info(artist, album, lang):
    """Description et faits du disque: identité MusicBrainz d'abord (nom
    canonique + année), puis TheAudioDB et Last.fm pour la description."""
    if not album:
        return None
    key = (artist.lower(), album.lower(), lang)
    cached = ALBUM_CACHE.get(key)
    if _cache_valide(cached):
        return cached[1]

    nom, annee, rgid = artist, None, None
    try:
        groupe = _mb_release_group(artist, album)
        if groupe:
            credit = (groupe.get("artist-credit") or [{}])[0].get("artist") or {}
            nom = credit.get("name") or artist
            annee = (groupe.get("first-release-date") or "")[:4] or None
            rgid = groupe.get("id")
    except Exception:
        pass
    tracks, credits, prod_facts = _mb_release_details(rgid, lang) if rgid else ([], [], [])

    data = None
    try:
        k = cle_theaudiodb()
        r = http.get(
            f"https://www.theaudiodb.com/api/v1/json/{k}/searchalbum.php",
            params={"s": nom, "a": album}, headers=_entetes_api(), timeout=5,
        )
        albums = (r.json() or {}).get("album") or []
        if albums:
            al = albums[0]
            desc = (al.get(f"strDescription{lang.upper()}") or al.get("strDescriptionEN") or "").strip()
            facts = []
            if al.get("intYearReleased"):
                facts.append(str(al["intYearReleased"]))
            if al.get("strLabel"):
                facts.append(al["strLabel"])
            if al.get("strGenre"):
                facts.append(al["strGenre"])
            if desc or facts:
                data = {"title": album, "facts": facts[:3],
                        "text": _couper(desc, 1200), "source": "TheAudioDB"}
    except Exception:
        pass

    if not data:
        cle = (CONFIG.get("lastfm_api_key") or "").strip()
        if cle:
            try:
                r = http.get(
                    "https://ws.audioscrobbler.com/2.0/",
                    params={"method": "album.getinfo", "artist": nom, "album": album,
                            "api_key": cle, "format": "json", "lang": lang, "autocorrect": 1},
                    headers=_entetes_api(), timeout=5,
                )
                al = (r.json() or {}).get("album") or {}
                texte = ((al.get("wiki") or {}).get("content") or "")
                texte = re.sub(r"<a href=[^>]*>.*$", "", texte, flags=re.S)
                texte = re.sub(r"<[^>]+>", "", texte).strip()
                if len(texte) > 40:
                    data = {"title": album, "facts": [], "text": _couper(texte, 1200),
                            "source": "Last.fm"}
            except Exception:
                pass

    if data and annee and annee not in data["facts"]:
        data["facts"] = ([annee] + [f for f in data["facts"] if f != annee])[:3]
        if data["source"] != "MusicBrainz":
            data["source"] += " · MusicBrainz"
    if not data and (annee or tracks or credits):
        data = {"title": album, "facts": [annee] if annee else [], "text": "",
                "source": "MusicBrainz"}
    if data:
        if len(credits) < 2:
            supplement = discogs_credits(nom, album, lang)
            if supplement:
                credits = credits + supplement
                data["source"] += " · Discogs"
        data["tracks"] = tracks
        data["credits"] = _grouper_credits(credits)
        data["prod_facts"] = prod_facts

    if data is None:
        print(f"[diagnostic] aucune fiche album pour {artist} - {album}", flush=True)
    _elaguer(ALBUM_CACHE)
    ALBUM_CACHE[key] = (time.time(), data)
    if data:
        planifier_sauvegarde()
    return data


def fetch_artist_info(artist, lang, album=None):
    """Chaîne de sources, spécialisées musique d'abord, identité levée par le disque."""
    key = (artist.lower(), (album or "").lower(), lang)
    cached = ARTIST_CACHE.get(key)
    if _cache_valide(cached):
        return cached[1]

    mb = musicbrainz_artist(artist, album)
    facts = mb["facts"] if mb else []
    nom = (mb or {}).get("name") or artist
    data = None

    # Sources specialisees musique en premier, Wikipedia en repli
    data = theaudiodb_bio(nom, lang, facts)
    if not data:
        data = lastfm_bio(nom, lang, facts)
    if not data and mb and mb.get("qid"):
        title, wl = wikidata_titre(mb["qid"], lang)
        if title:
            try:
                data = _wiki_data(nom, title, wl, facts, " · MusicBrainz")
            except Exception:
                data = None
    if not data:
        data = _wiki_recherche(nom, lang, facts)

    _elaguer(ARTIST_CACHE)
    ARTIST_CACHE[key] = (time.time(), data)
    if data:
        planifier_sauvegarde()
    return data


TRACK_CACHE = {}
GENIUS_ROLES = {
    "mixing engineer": "mix", "mastering engineer": "mastering",
    "recording engineer": "recording", "engineer": "engineer",
    "executive producer": "producer",
}


def fetch_track_credits(artist, titre, lang):
    """Crédits de la plage en cours via Genius: la seule base structurée qui
    couvre les sorties du jour, plage par plage."""
    token = (CONFIG.get("genius_token") or "").strip()
    if not token or not artist or not titre:
        return []
    key = (artist.lower(), titre.lower(), lang)
    cached = TRACK_CACHE.get(key)
    if _cache_valide(cached):
        return cached[1]
    credits = []
    try:
        entetes = dict(_entetes_api())
        entetes["Authorization"] = f"Bearer {token}"
        r = http.get(
            "https://api.genius.com/search",
            params={"q": f"{artist} {titre}"}, headers=entetes, timeout=5,
        )
        chanson = None
        for hit in ((r.json() or {}).get("response") or {}).get("hits") or []:
            res = hit.get("result") or {}
            interprete = ((res.get("primary_artist") or {}).get("name") or "").lower()
            if artist.lower() in interprete or interprete in artist.lower():
                chanson = res
                break
        if chanson:
            r2 = http.get(
                f"https://api.genius.com/songs/{chanson['id']}",
                params={"text_format": "plain"}, headers=entetes, timeout=5,
            )
            song = ((r2.json() or {}).get("response") or {}).get("song") or {}
            for p in song.get("producer_artists") or []:
                credits.append({"role": ROLES_CREDITS["producer"].get(lang, "Producer"),
                                "name": p.get("name", "")})
            for w in song.get("writer_artists") or []:
                credits.append({"role": ROLES_CREDITS["writing"].get(lang, "Writing"),
                                "name": w.get("name", "")})
            for perf in song.get("custom_performances") or []:
                etiquette = (perf.get("label") or "").strip()
                cle = GENIUS_ROLES.get(etiquette.lower())
                role = ROLES_CREDITS[cle].get(lang, etiquette) if cle else etiquette
                for a in perf.get("artists") or []:
                    credits.append({"role": role, "name": a.get("name", "")})
            credits = [c for c in credits if c["name"]][:40]
    except Exception:
        credits = []
    _elaguer(TRACK_CACHE)
    TRACK_CACHE[key] = (time.time(), credits)
    if credits:
        planifier_sauvegarde()
    return credits


def enrichir_album(album_info, artist, titre, lang):
    """Si le disque n'a pas de crédits, ceux de la plage en cours (Genius)."""
    if album_info is None or album_info.get("credits") or not titre:
        return album_info
    return avec_credits_de_plage(album_info, titre, fetch_track_credits(artist, titre, lang))


def avec_credits_de_plage(album_info, titre, plage):
    """Copie du disque complétée par les crédits déjà obtenus d'une plage.
    Aucun appel réseau : utilisable pendant une retouche du volet."""
    if album_info is None or album_info.get("credits") or not titre or not plage:
        return album_info
    album_info = dict(album_info)
    album_info["credits"] = _grouper_credits(plage)
    faits = [f"« {titre} »"] + list(album_info.get("prod_facts") or [])
    album_info["prod_facts"] = faits[:4]
    album_info["source"] = ((album_info.get("source") or "").strip() + " · Genius").strip(" ·")
    return album_info


FICHIER_FICHES = os.path.join(DATA_DIR, "cache_fiches.json")
_SAUVEGARDE = {"minuteur": None, "verrou": threading.Lock(), "empreinte": None}
DELAI_SAUVEGARDE = 60.0  # secondes : artiste, disque et plage partent dans la même écriture
VERROU_ELAGAGE = threading.Lock()
RG_CACHE = {}


def _elaguer(cache, maxi=500):
    """Garde le cache borné en retirant la moitié la plus ancienne.
    Travaille sur une copie : un autre fil peut retirer une clé entre-temps."""
    if len(cache) <= maxi:
        return
    with VERROU_ELAGAGE:
        entrees = sorted(list(cache.items()), key=lambda e: e[1][0])
        for cle, _ in entrees[:len(entrees) // 2]:
            cache.pop(cle, None)


def sauver_fiches():
    """Écrit les fiches réussies sur disque: le savoir survit aux redémarrages.
    Écriture atomique, et seulement si le contenu a changé : la carte SD
    n'est pas réécrite pour rien."""
    try:
        contenu = {}
        for nom, cache in (("artistes", ARTIST_CACHE), ("albums", ALBUM_CACHE),
                           ("plages", TRACK_CACHE)):
            contenu[nom] = [[list(k), ts, v] for k, (ts, v) in list(cache.items()) if v]
        texte = json.dumps(contenu, ensure_ascii=False)
        empreinte = hashlib.sha256(texte.encode("utf-8")).hexdigest()
        if empreinte == _SAUVEGARDE["empreinte"]:
            return
        temporaire = FICHIER_FICHES + ".tmp"
        with open(temporaire, "w", encoding="utf-8") as f:
            f.write(texte)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporaire, FICHIER_FICHES)
        _SAUVEGARDE["empreinte"] = empreinte
    except Exception as exc:
        print(f"[diagnostic] fiches non enregistrées : {type(exc).__name__}", flush=True)


def planifier_sauvegarde():
    """Sauvegarde au plus une fois par minute, en arrière-plan."""
    with _SAUVEGARDE["verrou"]:
        if _SAUVEGARDE["minuteur"] is None:
            def _faire():
                with _SAUVEGARDE["verrou"]:
                    _SAUVEGARDE["minuteur"] = None
                sauver_fiches()
            _SAUVEGARDE["minuteur"] = threading.Timer(DELAI_SAUVEGARDE, _faire)
            _SAUVEGARDE["minuteur"].daemon = True
            _SAUVEGARDE["minuteur"].start()


def charger_fiches():
    try:
        with open(FICHIER_FICHES, encoding="utf-8") as f:
            contenu = json.load(f)
        for nom, cache in (("artistes", ARTIST_CACHE), ("albums", ALBUM_CACHE),
                           ("plages", TRACK_CACHE)):
            for k, ts, v in contenu.get(nom, []):
                if time.time() - ts < 259200 and v:
                    cache[tuple(k)] = (ts, v)
    except FileNotFoundError:
        pass
    except Exception as exc:
        # fichier abîmé : on repart sans, les fiches se referont à l'écoute
        print(f"[diagnostic] fiches illisibles, ignorées : {type(exc).__name__}", flush=True)


charger_fiches()


def _mb_release_group(artist, album):
    """Le groupe de parution MusicBrainz du disque, demandé une seule fois
    puis partagé entre l'identification de l'artiste et la fiche album."""
    if not album:
        return None
    k = (artist.lower(), album.lower())
    entree = RG_CACHE.get(k)
    if entree and time.time() - entree[0] < (259200 if entree[1] else 120):
        return entree[1]
    groupe = None
    try:
        r = _mb_get(
            "https://musicbrainz.org/ws/2/release-group/",
            params={"query": f'releasegroup:"{album}" AND artist:"{artist}"',
                    "fmt": "json", "limit": 1},
            headers=_entetes_api(), timeout=4,
        )
        groupes = r.json().get("release-groups") or []
        groupe = groupes[0] if groupes else None
    except Exception:
        groupe = None
    _elaguer(RG_CACHE)
    RG_CACHE[k] = (time.time(), groupe)
    return groupe


def fiche_artiste(bio, artist, lang):
    """Page artiste du volet ; la photo passe par le proxy de pochettes."""
    if not bio:
        return {"name": artist, "text": T.get(lang, T["fr"])["no_bio"],
                "image": None, "facts": [], "source": ""}
    return {"name": bio["artist"], "text": bio["text"], "image": cover_ref(bio.get("image")),
            "facts": bio["facts"], "source": bio["source"]}


def noter_longueur_volet(valeur):
    """L'écran indique combien de crans de défilement le texte permet."""
    if not valeur.isdigit() or int(valeur) > 500:
        return
    ARTIST_PANEL["scroll_max"] = int(valeur)
    ARTIST_PANEL["scroll"] = min(ARTIST_PANEL["scroll"], int(valeur))


VERROU_VOLET = threading.Lock()


def ouvrir_volet(donnees, duree):
    """Publie un nouveau volet et rend son jeton : les recherches lancées pour
    lui ne retoucheront que lui."""
    with VERROU_VOLET:
        jeton = ARTIST_PANEL.get("token", 0) + 1
        ARTIST_PANEL.update({"until": time.time() + duree, "data": donnees, "scroll": 0,
                             "scroll_max": None, "page": "artist", "token": jeton})
    return jeton


def publier_volet(jeton, mutateur, prolonger=True):
    """Retouche le volet s'il est encore ouvert et que c'est bien le même.
    Le mutateur reçoit une copie et ne fait aucun appel réseau : deux fils qui
    publient en même temps ne s'écrasent pas, et une fermeture n'est pas défaite."""
    with VERROU_VOLET:
        donnees = ARTIST_PANEL["data"]
        if (not donnees or ARTIST_PANEL.get("token") != jeton
                or ARTIST_PANEL["until"] <= time.time()):
            return False
        retouche = dict(donnees)
        mutateur(retouche)
        ARTIST_PANEL["data"] = retouche
        if prolonger:
            ARTIST_PANEL["until"] = time.time() + 60
        return True


def toggle_artist_panel():
    """Affiche la bio de l'artiste en cours, ou la masque si déjà visible."""
    with VERROU_VOLET:
        if ARTIST_PANEL["until"] > time.time():
            ARTIST_PANEL.update({"until": 0.0, "data": None, "scroll": 0,
                                 "scroll_max": None, "page": "artist"})
            return True
    try:
        r = http.get(f"{eversolo_base()}/ZidooMusicControl/v2/getState", timeout=3)
        etat = normalize(r.json())
        artist = etat.get("artist")
        album_titre = etat.get("album")
        titre_courant = etat.get("title")
    except Exception:
        return False
    if not artist:
        return False
    lang = CONFIG.get("language", "fr")

    def assembler(bio, album_info):
        art = fiche_artiste(bio, artist, lang)
        return {"artist": art, "album": album_info}, (60 if (bio or album_info) else 8)

    cle_art = (artist.lower(), (album_titre or "").lower(), lang)
    art_pret = _cache_valide(ARTIST_CACHE.get(cle_art))
    cle_alb = (artist.lower(), (album_titre or "").lower(), lang)
    alb_pret = (not album_titre) or _cache_valide(ALBUM_CACHE.get(cle_alb))

    if art_pret and alb_pret:
        # tout est en cache (cas normal grace au prechargement): reponse immediate.
        # Les credits de plage (Genius) arrivent en arriere-plan, jamais en bloquant.
        alb = fetch_album_info(artist, album_titre, lang)
        data, duree = assembler(fetch_artist_info(artist, lang, album_titre), alb)
        jeton = ouvrir_volet(data, duree)
        if alb is not None and not alb.get("credits"):
            def _enrichir_fond():
                enrichi = enrichir_album(alb, artist, titre_courant, lang)
                if enrichi is not alb:
                    publier_volet(jeton, lambda d: d.__setitem__("album", enrichi),
                                  prolonger=False)
            threading.Thread(target=_enrichir_fond, daemon=True).start()
        return True

    # cache froid: panneau "recherche" immediat, trois fils paralleles derriere.
    # La touche ne doit JAMAIS attendre les sources externes, et chaque page
    # se remplit des que SA source repond, sans attendre les autres.
    attente = T.get(lang, T["fr"])["searching"]
    album_provisoire = None
    if album_titre:
        album_provisoire = {"title": album_titre, "facts": [], "text": attente,
                            "tracks": [], "credits": [], "prod_facts": [],
                            "source": "", "loading": True}
    jeton = ouvrir_volet({"artist": {"name": artist, "text": attente,
                                     "image": None, "facts": [], "source": ""},
                          "album": album_provisoire}, 30)

    def publier(mutateur):
        publier_volet(jeton, mutateur)

    def fil_artiste():
        try:
            bio = fetch_artist_info(artist, lang, album_titre)
        except Exception:
            bio = None
        art = fiche_artiste(bio, artist, lang)
        publier(lambda d: d.__setitem__("artist", art))

    def fil_album():
        try:
            alb = enrichir_album(fetch_album_info(artist, album_titre, lang),
                                 artist, titre_courant, lang)
        except Exception:
            alb = None
        publier(lambda d: d.__setitem__("album", alb))

    def fil_plage():
        try:
            plage = fetch_track_credits(artist, titre_courant, lang)
        except Exception:
            return
        if not plage:
            return

        def fusion(d):
            alb = d.get("album")
            if alb and not alb.get("loading"):
                d["album"] = avec_credits_de_plage(alb, titre_courant, plage)
        publier(fusion)

    for fil in (fil_artiste, fil_album, fil_plage):
        threading.Thread(target=fil, daemon=True).start()
    return True


def _rev_locale():
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=BASE_DIR,
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception:
        return ""


LOCAL_REV = _rev_locale()
# Nom lisible de la version en service : « v1.2.0 » avec les versions, le
# commit sinon (installation d'avant le lot 0 bis).
VERSION_LOCALE = os.path.basename(os.path.realpath(BASE_DIR)) if DISPO else LOCAL_REV
MAJ_DISPONIBLE = {"ts": 0.0, "version": None, "notes": [], "en_cours": False}
MAJ_VERROU = threading.Lock()
MAJ_RECHERCHE_S = 600
MAJ_VALIDATION_S = 20
MAJ_VALIDATION_ESSAIS = 10   # un Pi 3 peut mettre du temps à tout charger


def chercher_mise_a_jour():
    """Version signée plus récente publiée, et ses nouveautés (en fond)."""
    if not DISPO:
        return
    with MAJ_VERROU:
        if MAJ_DISPONIBLE["en_cours"] or time.time() - MAJ_DISPONIBLE["ts"] < MAJ_RECHERCHE_S:
            return
        MAJ_DISPONIBLE.update(en_cours=True, ts=time.time())

    def travail():
        try:
            with versions.verrou(DISPO):  # jamais pendant une installation
                versions.git(DISPO, "fetch", "--quiet", "--tags", "origin", duree=300)
                # seule une version dont la signature tient est proposée
                locaux = versions.tags_de_ls_remote(
                    versions.git(DISPO, "ls-remote", "--tags", "."))
                cible = versions.proposable(DISPO, locaux, VERSION_LOCALE)
                notes = versions.notes(DISPO, cible) if cible else []
            MAJ_DISPONIBLE.update(version=cible, notes=notes)
        except (versions.ErreurMaj, versions.Occupe, OSError, subprocess.TimeoutExpired) as exc:
            MAJ_DISPONIBLE.update(version=None, notes=[])
            print(f"[diagnostic] recherche de mise à jour : {exc}", flush=True)
        finally:
            MAJ_DISPONIBLE["en_cours"] = False
    threading.Thread(target=travail, daemon=True).start()


def maj_en_cours():
    if not DISPO:
        return None
    etat = versions.lire_etat(DISPO)
    if versions.en_cours(etat):
        return {"etape": etat["etape"], "version": etat.get("version")}
    return None


def lecture_en_cours():
    return ((STATE_CACHE.get("info") or {}).get("etat") == "lecture")


def installer_version(cible):
    """Installe une version signée puis redémarre ; en cas d'échec, le serveur
    continue sur la version actuelle et /config affiche la raison."""
    def travail():
        try:
            versions.installer(DISPO, cible)
        except Exception as exc:  # noqa: BLE001 - le fil ne doit jamais mourir en silence
            print(f"[diagnostic] mise à jour refusée : {exc}", flush=True)
            versions.noter_echec(DISPO, cible, exc)
            return
        os._exit(1)  # systemd relance sur la nouvelle version
    threading.Thread(target=travail, daemon=True).start()


def revenir_version():
    versions.revenir(DISPO)
    threading.Timer(1.0, lambda: os._exit(1)).start()


def valider_au_demarrage(port):
    """Après quelques secondes, si le serveur répond, la version est adoptée ;
    sinon le garde de systemd reviendra à la précédente."""
    if not DISPO:
        return

    def travail():
        for _ in range(MAJ_VALIDATION_ESSAIS):
            time.sleep(MAJ_VALIDATION_S if _ == 0 else 10)
            try:
                r = requests.get(f"http://127.0.0.1:{port}/favicon.ico", timeout=5,
                                 headers={"Host": f"localhost:{port}"})
                if r.status_code != 200:
                    continue
                if versions.valider(DISPO):
                    print(f"[mise à jour] {VERSION_LOCALE} adoptée", flush=True)
                return
            except (requests.RequestException, versions.Occupe, OSError) as exc:
                print(f"[diagnostic] validation, nouvel essai : {exc}", flush=True)
    threading.Thread(target=travail, daemon=True).start()


FAILED = {}
MAX_ATTEMPTS = 5
LOCK_WINDOW = 15 * 60


ECHECS_CONNEXION = []
MAX_ECHECS_CONNEXION = 30  # toutes adresses confondues : changer d'IP ne suffit plus


def is_locked(ip):
    now = time.time()
    attempts = [t for t in FAILED.get(ip, []) if now - t < LOCK_WINDOW]
    if attempts:
        FAILED[ip] = attempts
    else:
        FAILED.pop(ip, None)
    ECHECS_CONNEXION[:] = [t for t in ECHECS_CONNEXION if now - t < LOCK_WINDOW]
    return len(attempts) >= MAX_ATTEMPTS or len(ECHECS_CONNEXION) >= MAX_ECHECS_CONNEXION


def record_failure(ip):
    if len(FAILED) > 1000:
        FAILED.clear()  # borne la mémoire ; le compteur global reste
    FAILED.setdefault(ip, []).append(time.time())
    ECHECS_CONNEXION.append(time.time())


# ------------------------------------------------------------------- helpers


def tr():
    lang = CONFIG.get("language", "fr")
    return T.get(lang, T["fr"])


def eversolo_base():
    return f"http://{CONFIG['eversolo_ip']}:{CONFIG['eversolo_port']}"


def is_configured():
    return load_auth() is not None and CONFIG.get("eversolo_ip")


def empreinte_auth():
    """Empreinte du mot de passe en vigueur : une session ouverte avant un
    changement de mot de passe cesse d'être valable."""
    stored = (load_auth() or {}).get("password_hash", "")
    return hashlib.sha256(stored.encode()).hexdigest()[:32] if stored else ""


def ouvrir_session():
    session.clear()
    session["auth"] = empreinte_auth()
    session.permanent = True


def logged_in():
    attendu, recu = empreinte_auth(), session.get("auth")
    return bool(attendu) and isinstance(recu, str) and secrets.compare_digest(recu, attendu)


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


def csrf_ok():
    token = session.get("csrf")
    sent = request.form.get("csrf", "")
    return token and sent and secrets.compare_digest(token, sent)


def valid_ip(value):
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


ENTETES_RELAIS = ("X-Forwarded-For", "Forwarded", "X-Real-IP")


def requete_locale():
    """Vrai pour le kiosque et le démon IR, qui tournent sur le Pi lui-même.
    Un relais installé un jour sur le Pi (proxy, tunnel) se présenterait lui
    aussi en 127.0.0.1 : on exige en plus un nom local et aucun en-tête de relais."""
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return False
    if any(request.headers.get(h) for h in ENTETES_RELAIS):
        return False
    return nom_hote(request.host) in ("localhost", "127.0.0.1", "::1")


def ip_locale():
    """Adresse du Pi sur le réseau local (aucun paquet n'est envoyé)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def nom_hote(hote):
    """Nom ou adresse d'un en-tête Host, sans port, en minuscules."""
    nom = (hote or "").strip().lower()
    if nom.startswith("["):
        nom = nom[1:nom.find("]")] if "]" in nom else nom[1:]
    elif nom.count(":") == 1:
        nom = nom.split(":", 1)[0]
    return nom.rstrip(".")


def hote_autorise(hote):
    """Vrai si l'en-tête Host désigne bien le Pi : adresse IP, localhost, nom
    du Pi avec ou sans .local, ou nom ajouté dans config.json. Une page piégée
    qui rebondit par DNS vers le Pi arrive toujours avec son propre nom."""
    nom = nom_hote(hote)
    if not nom:
        return False
    try:
        ipaddress.ip_address(nom)
        return True
    except ValueError:
        pass
    if "." not in nom:
        # Nom court (eversolo, localhost) : jamais un domaine d'attaquant, qui
        # a toujours au moins un point.
        return True
    pi = socket.gethostname().lower()
    court = pi.split(".")[0]
    ajoutes = CONFIG.get("hotes_autorises") or []
    if isinstance(ajoutes, str):
        ajoutes = [ajoutes]
    noms = {pi, court + ".local"}
    noms.update(nom_hote(str(n)) for n in ajoutes)
    return nom in noms


# Code de première configuration : affiché sur la TV, exigé de tout appareil
# du réseau tant qu'aucun mot de passe n'existe. Le code reste stable (un
# invité ne peut pas le faire changer sous les yeux du propriétaire) ; ce sont
# les essais qui sont limités : 5 erreurs bloquent une adresse 15 minutes,
# 30 erreurs en tout suspendent l'installation réseau 10 minutes. Au mieux
# 180 essais par heure contre un million de codes possibles.
INSTALLATION = {"code": None, "echecs": {}, "recents": [], "pause_jusqu": 0.0}
INSTALLATION_VERROU = threading.Lock()
ECHECS_PAR_ADRESSE = 5
BLOCAGE_ADRESSE = 15 * 60
ECHECS_GLOBAUX = 30
PAUSE_GLOBALE = 10 * 60


def code_installation():
    with INSTALLATION_VERROU:
        if INSTALLATION["code"] is None:
            INSTALLATION["code"] = f"{secrets.randbelow(10 ** 6):06d}"
            # Le journal sert de repli quand aucune TV n'est branchée.
            print(f"[installation] code affiché sur la TV : {INSTALLATION['code']}", flush=True)
        return INSTALLATION["code"]


def _echecs_recents(adresse, maintenant):
    return [t for t in INSTALLATION["echecs"].get(adresse, []) if maintenant - t < BLOCAGE_ADRESSE]


def code_bloque(adresse):
    maintenant = time.time()
    with INSTALLATION_VERROU:
        return (maintenant < INSTALLATION["pause_jusqu"]
                or len(_echecs_recents(adresse, maintenant)) >= ECHECS_PAR_ADRESSE)


def verifier_code(saisi, adresse=None):
    """Compare le code saisi, sauf si l'adresse ou l'installation est bloquée."""
    attendu = code_installation()
    if code_bloque(adresse):
        return False
    if secrets.compare_digest(attendu.encode(), (saisi or "").strip().encode()):
        return True
    maintenant = time.time()
    with INSTALLATION_VERROU:
        echecs = INSTALLATION["echecs"]
        echecs[adresse] = _echecs_recents(adresse, maintenant) + [maintenant]
        if len(echecs) > 256:
            for ancienne in [a for a in echecs if not _echecs_recents(a, maintenant)]:
                echecs.pop(ancienne, None)
        recents = [t for t in INSTALLATION["recents"] if maintenant - t < PAUSE_GLOBALE]
        recents.append(maintenant)
        if len(recents) >= ECHECS_GLOBAUX:
            INSTALLATION["pause_jusqu"] = maintenant + PAUSE_GLOBALE
            recents = []
        INSTALLATION["recents"] = recents
    return False


def oublier_code():
    with INSTALLATION_VERROU:
        INSTALLATION.update({"code": None, "echecs": {}, "recents": [], "pause_jusqu": 0.0})


def csrf_entete_ok():
    token = session.get("csrf")
    sent = request.headers.get("X-CSRF-Token", "")
    return bool(token and sent and secrets.compare_digest(token, sent))


@app.before_request
def controler_hote():
    if hote_autorise(request.host):
        return None
    texte = tr()["host_refused"].format(ip=ip_locale(), port=CONFIG.get("listen_port", 8080))
    return Response(texte, status=400, mimetype="text/plain")


@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    # Une route peut imposer sa propre politique (proxy de pochettes: sandbox).
    resp.headers.setdefault("Content-Security-Policy", (
        "default-src 'self'; img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self'; script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; frame-ancestors 'none'"
    ))
    return resp


# ------------------------------------------------------- détection du streamer


def probe(ip, port, timeout=0.4):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            pass
        r = requests.get(
            f"http://{ip}:{port}/ZidooMusicControl/v2/getState", timeout=1.5
        )
        if r.ok and isinstance(r.json(), dict):
            return {"ip": ip, "model": device_model(ip, port)}
    except Exception:
        pass
    return None


def local_subnet():
    return ipaddress.ip_network(f"{ip_locale()}/24", strict=False)


SCAN_VERROU = threading.Lock()


def scan_network():
    port = int(CONFIG.get("eversolo_port", 9529))
    hosts = [str(h) for h in local_subnet().hosts()]
    found = []
    with ThreadPoolExecutor(max_workers=64) as pool:
        for result in pool.map(lambda ip: probe(ip, port), hosts):
            if result:
                found.append(result)
    return found


# ------------------------------------------------------------ capture d'état

CAPTURES_DIR = os.path.join(DATA_DIR, "captures")
CAPTURES_MAX = 40
CAPTURE_NOM_RE = re.compile(r"^\d{8}-\d{6}-[a-z]+\.json$")
CAPTURE_VERROU = threading.Lock()
SITUATIONS = ("qobuz", "tidal", "radio", "dsd", "fichier", "pause", "muet", "autre")
# Routes sûres : ni bibliothèque ni recherche, qui peuvent bloquer la base
# musicale de l'Eversolo plusieurs minutes.
CAPTURE_ROUTES = (
    ("getState", "/ZidooMusicControl/v2/getState"),
    ("getInputAndOutputList", "/ZidooMusicControl/v2/getInputAndOutputList"),
    ("getPlayQueue", "/ZidooMusicControl/v2/getPlayQueue?start=0&count=20"),
    ("getModel", "/ControlCenter/getModel"),
)
CLES_SENSIBLES = re.compile(
    r"token|passw|secret|cookie|e?mail|account|login|hmac|signature|serial|uuid|ssid|psk|imei"
    r"|api_?key|device_?id|mac_?addr|_mac$|session_?(id|key)|^mac$|^sn$|^uid$|^user(_?name|_?id)?$"
    r"|auth(?!or)", re.I)
SCHEMA_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.I)
MASQUE = "(masqué)"


def masquer(valeur, cle=""):
    """Copie sans secrets : champs d'identité masqués, adresses de flux
    réduites à leur hôte (les URL Qobuz et Tidal sont signées). Les adresses
    de l'Eversolo lui-même restent intactes."""
    if cle and CLES_SENSIBLES.search(cle) and valeur not in (None, "", [], {}):
        return MASQUE
    if isinstance(valeur, dict):
        return {k: masquer(v, str(k)) for k, v in valeur.items()}
    if isinstance(valeur, list):
        return [masquer(v, cle) for v in valeur]
    if isinstance(valeur, str) and SCHEMA_RE.match(valeur):
        # Toute adresse (http, smb, nfs, rtsp…) : identifiants retirés ; pour
        # un hôte tiers, chemin et paramètres aussi (adresses de flux signées).
        try:
            p = urlparse(valeur)
            hote = p.hostname or ""
            port = p.port
        except ValueError:
            return MASQUE
        netloc = f"[{hote}]" if ":" in hote else hote
        if port:
            netloc += f":{port}"
        if hote and hote == CONFIG.get("eversolo_ip"):
            return p._replace(netloc=netloc, fragment="").geturl()
        # Sous-domaine numérique d'un service tiers : identifiant d'appareil.
        netloc = re.sub(r"(?<![\w-])\d{6,}(?=\.)", "x", netloc)
        return f"{p.scheme}://{netloc}/{MASQUE}"
    return valeur


def capturer_etat(situation):
    """Enregistre ce que l'Eversolo renvoie, une requête à la fois. Renvoie le
    nom du fichier, ou None si l'Eversolo n'a pas répondu du tout."""
    if not CONFIG.get("eversolo_ip"):
        return None
    contenu = {"capture": {"date": time.strftime("%Y-%m-%d %H:%M:%S"),
                           "situation": situation, "version": LOCAL_REV}}
    repondu = False
    for nom, chemin in CAPTURE_ROUTES:
        try:
            contenu[nom] = http.get(eversolo_base() + chemin, timeout=4).json()
            repondu = True
        except Exception as exc:
            contenu[nom] = {"erreur": type(exc).__name__}
    if not repondu:
        return None
    try:
        propre = masquer(contenu)
    except Exception:
        # Jamais de capture non masquée sur le disque.
        return None
    os.makedirs(CAPTURES_DIR, mode=0o700, exist_ok=True)
    fichier = time.strftime("%Y%m%d-%H%M%S") + "-" + situation + ".json"
    ecrire_json(os.path.join(CAPTURES_DIR, fichier), propre)
    for ancien in liste_captures()[CAPTURES_MAX:]:
        try:
            os.remove(os.path.join(CAPTURES_DIR, ancien))
        except OSError:
            pass
    return fichier


def liste_captures():
    try:
        noms = [n for n in os.listdir(CAPTURES_DIR) if CAPTURE_NOM_RE.fullmatch(n)]
    except FileNotFoundError:
        return []
    return sorted(noms, reverse=True)


# ------------------------------------------------------------------ templates

PAGE = """
<!DOCTYPE html><html lang="{{ lang }}" class="{{ classe }}"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="google" content="notranslate">
<meta name="color-scheme" content="light dark">
<title>Eversolo · {{ title }}</title>
<link href="/static/fonts/fonts.css" rel="stylesheet">
<link href="/static/reglages.css" rel="stylesheet">
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
<link rel="icon" type="image/png" href="/static/favicon.png">
<link rel="apple-touch-icon" href="/static/apple-touch-icon.png">
</head><body>
{{ nav }}
{% if large %}<main class="reglages">{{ body }}</main>
{% else %}<main class="card">
  {% if not nav %}<div class="brand"><span class="marque"></span><b>Eversolo</b></div>{% endif %}
  {{ body }}
</main>{% endif %}
</body></html>
"""


def barre_navigation(courant):
    """Bandeau des pages réservées : où l'on est, où aller, se déconnecter."""
    t = tr()
    liens = (("config", "/config", t["config_title"]), ("remote", "/remote", t["remote_title"]),
             ("blaster", "/blaster", t["blaster_title"]))
    actif = ' aria-current="page"'
    items = "".join(
        f'<a href="{href}"{actif if cle == courant else ""}>{escape(nom)}</a>'
        for cle, href, nom in liens)
    modele = escape(MODEL_CACHE.get("name") or "")
    return Markup(f"""<header class="entete"><div class="entete-in">
  <a class="brand" href="/"><span class="marque"></span><b>Eversolo</b><span class="modele">{modele}</span></a>
  <nav>{items}<a href="/" class="vers-ecran">{escape(t['back_display'])}</a>
    <form method="post" action="/logout"><input type="hidden" name="csrf" value="{csrf_token()}">
    <button class="lien">{escape(t['logout'])}</button></form></nav>
</div></header>""")


def page(title, body, lang, large=False, nav=None, sombre=False):
    return render_template_string(
        PAGE, title=title, body=Markup(body), lang=lang, large=large,
        nav=barre_navigation(nav) if nav else "", classe="sombre" if sombre else "")


# --------------------------------------------------------------------- routes


@app.route("/")
def index():
    if not is_configured():
        return redirect("/setup")
    return send_from_directory(app.static_folder, "index.html")


def page_installation_tv(t, lang):
    """Écran de la TV avant la première configuration : où aller, quel code."""
    port = CONFIG.get("listen_port", 8080)
    nom = socket.gethostname()
    code = code_installation()
    body = f"""
<style>
.card{{width:min(1100px,94vw);text-align:center;padding:5vh 4vw}}
.tvurl{{font-family:"Geist Mono",monospace;font-size:clamp(22px,4.4vh,48px);margin:1.2vh 0;word-break:break-all}}
.tvcode{{font-family:"Geist Mono",monospace;font-size:clamp(56px,15vh,170px);letter-spacing:.14em;color:var(--tube);margin-top:1vh}}
.card h1{{font-size:clamp(28px,6vh,64px)}}
.card .intro{{font-size:clamp(16px,3vh,30px);margin:3vh 0 0}}
</style>
<h1>{t['setup_title']}</h1>
<p class="intro">{t['tv_setup_intro']}</p>
<div class="tvurl">http://{escape(ip_locale())}:{port}</div>
<div class="tvurl" style="color:var(--muted)">http://{escape(nom)}.local:{port}</div>
<p class="intro">{t['tv_setup_code']}</p>
<div class="tvcode" id="code">{code}</div>
<div class="foot"><a href="/setup?ici=1&amp;lang={lang}">{t['tv_setup_here']}</a></div>
<script>
setInterval(async function() {{
  try {{
    const d = await (await fetch('/api/setup/etat', {{cache: 'no-store'}})).json();
    if (d.configure) location = '/';
    else if (d.code) document.getElementById('code').textContent = d.code;
  }} catch (e) {{}}
}}, 3000);
</script>
"""
    return page(t["setup_title"], body, lang, sombre=True)


@app.route("/setup", methods=["GET", "POST"])
def setup():
    if load_auth() is not None:
        return redirect("/config")
    lang = request.values.get("lang", CONFIG.get("language", "fr"))
    if lang not in LANGS:
        lang = "fr"
    t = T[lang]
    locale = requete_locale()
    if locale and request.method == "GET" and not request.args.get("ici"):
        return page_installation_tv(t, lang)
    error = None
    code_saisi = ""

    if request.method == "POST":
        if not csrf_ok():
            error = "CSRF"
        elif not locale and not verifier_code(request.form.get("code"), request.remote_addr):
            # Le code passe avant tout le reste : sans lui, aucun champ n'est examiné.
            error = t["locked"] if code_bloque(request.remote_addr) else t["code_bad"]
        else:
            code_saisi = "" if locale else request.form.get("code", "").strip()
            pw = request.form.get("password", "")
            pw2 = request.form.get("password2", "")
            ip = request.form.get("device_ip", "").strip()
            if len(pw) < 8:
                error = t["password_short"]
            elif pw != pw2:
                error = t["password_mismatch"]
            elif not valid_ip(ip):
                error = t["invalid_ip"]
            else:
                save_auth(generate_password_hash(pw, method="scrypt"))
                oublier_code()
                CONFIG.update({"eversolo_ip": ip, "language": lang})
                save_config(CONFIG)
                ouvrir_session()
                return redirect("/")

    champ_code = "" if locale else f"""
  <label for="code">{t['code_label']}</label>
  <input type="text" name="code" id="code" value="{escape(code_saisi)}" inputmode="numeric" pattern="[0-9]{{6}}" maxlength="6" autocomplete="one-time-code" required>"""
    body = f"""
<h1>{t['setup_title']}</h1>
<p class="intro">{t['setup_intro']}</p>
{f'<div class="msg err">{error}</div>' if error else ''}
<form method="post" action="/setup?lang={lang}{'&amp;ici=1' if locale else ''}">
  <input type="hidden" name="csrf" value="{csrf_token()}">{champ_code}
  <label>{t['language']}</label>
  <select onchange="location='/setup?{'ici=1&' if locale else ''}lang='+this.value">
    <option value="fr" {'selected' if lang=='fr' else ''}>Français</option>
    <option value="en" {'selected' if lang=='en' else ''}>English</option>
    <option value="es" {'selected' if lang=='es' else ''}>Español</option>
    <option value="de" {'selected' if lang=='de' else ''}>Deutsch</option>
  </select>
  <label>{t['password']}</label>
  <input type="password" name="password" minlength="8" required autocomplete="new-password">
  <label>{t['password_confirm']}</label>
  <input type="password" name="password2" minlength="8" required autocomplete="new-password">
  <label>{t['device_ip']}</label>
  <div class="row">
    <input type="text" name="device_ip" id="ip" placeholder="192.168.1.50" required>
    <button type="button" id="scan">{t['detect']}</button>
  </div>
  <button type="submit">{t['save']}</button>
</form>
<script>
document.getElementById('scan').onclick = async function() {{
  const champ = document.getElementById('code');
  const entetes = {{}};
  if (champ) {{
    if (!champ.value.trim()) {{ alert({json.dumps(t['code_first'])}); champ.focus(); return; }}
    entetes['X-Code-Installation'] = champ.value.trim();
  }}
  this.textContent = {json.dumps(t['detecting'])}; this.disabled = true;
  try {{
    const r = await fetch('/api/detect', {{headers: entetes}});
    if (r.status === 403) alert({json.dumps(t['code_bad'])});
    else if (r.status === 429) alert({json.dumps(t['detecting'])});
    else {{
      const d = await r.json();
      if (d.found && d.found.length) document.getElementById('ip').value = d.found[0].ip;
      else alert({json.dumps(t['detect_none'])});
    }}
  }} catch (e) {{ alert({json.dumps(t['detect_none'])}); }}
  this.textContent = {json.dumps(t['detect'])}; this.disabled = false;
}};
</script>
"""
    return page(t["setup_title"], body, lang)


@app.route("/login", methods=["GET", "POST"])
def login():
    if load_auth() is None:
        return redirect("/setup")
    t = tr()
    lang = CONFIG.get("language", "fr")
    ip = request.remote_addr or "?"
    error = None

    if request.method == "POST":
        if is_locked(ip):
            error = t["locked"]
        elif not csrf_ok():
            error = t["session_expired"]
        else:
            if password_ok(request.form.get("password", "")):
                FAILED.pop(ip, None)
                ouvrir_session()
                return redirect("/config")
            record_failure(ip)
            error = t["locked"] if is_locked(ip) else t["bad_password"]

    body = f"""
<h1>{t['login_title']}</h1>
{f'<div class="msg err">{error}</div>' if error else ''}
<form method="post" action="/login">
  <input type="hidden" name="csrf" value="{csrf_token()}">
  <label>{t['password']}</label>
  <input type="password" name="password" required autofocus autocomplete="current-password">
  <button type="submit">{t['login']}</button>
</form>
<div class="foot"><a href="/">{t['back_display']}</a></div>
"""
    return page(t["login_title"], body, lang)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect("/")


@app.route("/config", methods=["GET", "POST"])
def config_page():
    if load_auth() is None:
        return redirect("/setup")
    if not logged_in():
        return redirect("/login")
    t = tr()
    lang = CONFIG.get("language", "fr")
    message = error = None

    if request.method == "POST":
        if not csrf_ok():
            error = t["session_expired"]
        elif request.form.get("op") == "update" and DISPO:
            cible = MAJ_DISPONIBLE.get("version")
            if maj_en_cours():
                error = t["maj_deja"]
            elif lecture_en_cours():
                error = t["maj_pendant_lecture"]
            elif not cible:
                error = t["maj_rien"]
            else:
                installer_version(cible)
                message = t["maj_lancee"]
        elif request.form.get("op") == "retour" and DISPO:
            try:
                revenir_version()
                message = t["maj_retour_lance"]
            except (versions.ErreurMaj, versions.Occupe, OSError) as exc:
                error = str(exc)
        elif request.form.get("op") == "affichage":
            CONFIG.update(affichage.reglages_depuis_formulaire(request.form))
            save_config(CONFIG)
            message = t["saved"]
        elif request.form.get("op") == "capture":
            situation = request.form.get("situation", "")
            if situation not in SITUATIONS:
                situation = "autre"
            if CAPTURE_VERROU.acquire(blocking=False):
                try:
                    fichier = capturer_etat(situation)
                finally:
                    CAPTURE_VERROU.release()
                if fichier:
                    message = f"{t['capture_done']} : {fichier}"
                else:
                    error = t["capture_failed"]
            else:
                error = t["capture_busy"]
        else:
            ip = request.form.get("device_ip", "").strip()
            new_lang = request.form.get("language", lang)
            new_pw = request.form.get("new_password", "")
            cur_pw = request.form.get("current_password", "")
            if not valid_ip(ip):
                error = t["invalid_ip"]
            elif new_pw and len(new_pw) < 8:
                error = t["password_short"]
            elif new_pw and not password_ok(cur_pw):
                error = t["bad_password"]
            else:
                if new_pw:
                    save_auth(generate_password_hash(new_pw, method="scrypt"))
                    # les autres sessions (cookie volé, autre appareil) tombent
                    session["auth"] = empreinte_auth()
                CONFIG.update({
                    "eversolo_ip": ip,
                    "language": new_lang if new_lang in LANGS else lang,
                    "theaudiodb_key": request.form.get("tadb_key", "").strip() or TADB_CLE_GRATUITE,
                    "lastfm_api_key": request.form.get("lastfm_key", "").strip(),
                    "discogs_token": request.form.get("discogs_token", "").strip(),
                    "genius_token": request.form.get("genius_token", "").strip(),
                })
                save_config(CONFIG)
                t = tr()
                lang = CONFIG["language"]
                message = t["saved"]

    choix_langue = "".join(
        f'<option value="{code}"{" selected" if lang == code else ""}>{nom}</option>'
        for code, nom in (("fr", "Français"), ("en", "English"), ("es", "Español"), ("de", "Deutsch")))
    section_streamer = groupe("02", t["sec_streamer"], t["sec_streamer_intro"], f"""
    <label for="ip">{t['device_ip']}</label>
    <div class="row">
      <input type="text" name="device_ip" id="ip" class="mono" value="{escape(CONFIG['eversolo_ip'])}" required inputmode="decimal">
      <button type="button" class="second" id="scan">{t['detect']}</button>
    </div>
    <p class="aide" id="scanEtat" role="status"></p>
    <label for="langue">{t['language']}</label>
    <select name="language" id="langue">{choix_langue}</select>""")
    section_sources = groupe("03", t["sec_sources"], t["sec_sources_intro"], "".join((
        champ_cle(t, "lastfm_key", t["lastfm_key"], CONFIG.get("lastfm_api_key", ""), LIENS_CLES["lastfm"]),
        champ_cle(t, "discogs_token", t["discogs_token"], CONFIG.get("discogs_token", ""), LIENS_CLES["discogs"]),
        champ_cle(t, "genius_token", t["genius_token_lbl"], CONFIG.get("genius_token", ""), LIENS_CLES["genius"]),
        champ_cle(t, "tadb_key", t["tadb_key"], cle_theaudiodb(), LIENS_CLES["theaudiodb"]))))
    section_compte = groupe("04", t["sec_compte"], t["sec_compte_intro"], f"""
    <div class="deux">
      <div><label for="npw">{libelle(t['new_password'])[0]}</label>
      <input type="password" name="new_password" id="npw" autocomplete="new-password"></div>
      <div><label for="cpw">{t['current_password']}</label>
      <input type="password" name="current_password" id="cpw" autocomplete="current-password"></div>
    </div>
    <div class="actions"><button type="submit">{t['save']}</button></div>""")
    messages = (f'<div class="msg">{message}</div>' if message else "") + (
        f'<div class="msg err">{error}</div>' if error else "")
    body = f"""
<div class="titre-page"><h1>{t['config_title']}</h1>{messages}</div>
{bloc_affichage(t)}
<form method="post" action="/config" class="formulaire">
  <input type="hidden" name="csrf" value="{csrf_token()}">
  {section_streamer}
  {section_sources}
  {section_compte}
</form>
__VERSION_HTML__
{bloc_capture(t)}
<script>
document.getElementById('scan').onclick = async function() {{
  const etat = document.getElementById('scanEtat');
  this.textContent = {json.dumps(t['detecting'])}; this.disabled = true; etat.textContent = '';
  try {{
    const r = await fetch('/api/detect'); const d = await r.json();
    if (d.found && d.found.length) document.getElementById('ip').value = d.found[0].ip;
    else etat.textContent = {json.dumps(t['detect_none'])};
  }} catch (e) {{ etat.textContent = {json.dumps(t['detect_none'])}; }}
  this.textContent = {json.dumps(t['detect'])}; this.disabled = false;
}};
</script>
"""
    if DISPO:
        version_html = groupe("05", t["sec_maj"], "", bloc_mise_a_jour(t))
    else:
        # ancienne installation (sans dossiers de version) : la mise à jour
        # passe par update.sh, qui migre vers les versions signées
        version_html = groupe("05", t["sec_maj"], "",
                              f'<p class="intro">{t["maj_ancienne"]}</p>'
                              f'<p class="aide mono">{escape(LOCAL_REV)}</p>')
    body = body.replace("__VERSION_HTML__", version_html)
    return page(t["config_title"], body, lang, large=True, nav="config")


LIENS_CLES = {
    "lastfm": "https://www.last.fm/api/account/create",
    "discogs": "https://www.discogs.com/settings/developers",
    "genius": "https://genius.com/api-clients",
    "theaudiodb": "https://www.theaudiodb.com/free_music_api",
}


def libelle(texte):
    """« Clé Last.fm (repli biographies) » → ("Clé Last.fm", "repli biographies")."""
    m = re.fullmatch(r"(.+?)\s*\((.+)\)", texte)
    return (m.group(1), m.group(2)) if m else (texte, "")


def nom_et_detail(texte):
    """« Salon : TV lue à 3-4 m » → ("Salon", "TV lue à 3-4 m")."""
    m = re.match(r"(.+?)\s?:\s(.+)", texte)
    return (m.group(1), m.group(2)) if m else (texte, "")


def groupe(numero, titre, intro, contenu):
    """Une section de réglages : explication à gauche, champs à droite."""
    intro_html = f'<p class="intro">{intro}</p>' if intro else ""
    return f"""<section class="groupe">
  <header><span class="num">{numero}</span><h2>{titre}</h2>{intro_html}</header>
  <div class="champs">{contenu}</div>
</section>"""


def champ_cle(t, nom, texte, valeur, lien):
    titre, aide = libelle(texte)
    return f"""<div class="cle">
  <div class="cle-tete"><label for="{nom}">{escape(titre)}</label>
  <a href="{lien}" target="_blank" rel="noopener noreferrer">{t['get_key']}</a></div>
  <input type="text" name="{nom}" id="{nom}" class="mono" value="{escape(valeur)}" autocomplete="off" spellcheck="false">
  {f'<p class="aide">{escape(aide)}</p>' if aide else ''}
</div>"""


def choix(nom, valeurs, choisie, textes, classe="choix"):
    """Boutons radio présentés en cartes."""
    cartes = []
    for v in valeurs:
        titre, detail = nom_et_detail(textes[v])
        mini = (f'<span class="mini {v}"><i class="c"></i><i class="t"></i><i class="a"></i><i class="b"></i></span>'
                if classe == "themes" else "")
        cartes.append(
            f'<label class="option"><input type="radio" name="{nom}" value="{v}"'
            f'{" checked" if v == choisie else ""}><span class="carte">{mini}'
            f'<span class="nom">{escape(titre)}</span>'
            f'{f"<span class=detail>{escape(detail)}</span>" if detail else ""}</span></label>')
    return f'<div class="{classe}">{"".join(cartes)}</div>'


def bloc_mise_a_jour(t):
    """Section « Mise à jour » : version en service, disponible, retour."""
    chercher_mise_a_jour()
    etat = versions.lire_etat(DISPO)
    precedente = versions.version_de_lien(DISPO.precedente)
    jeton = csrf_token()
    lignes = [f'<p class="version"><span>{t["maj_installee"]}</span> <b class="mono">{escape(VERSION_LOCALE)}</b></p>']
    if etat.get("etape") in ("echec", "retour") and etat.get("erreur"):
        lignes.append(f'<div class="msg err">{escape(etat["erreur"])}</div>')
    en_cours = maj_en_cours()
    if en_cours:
        lignes.append(f'<div class="msg">{t["maj_etape_" + en_cours["etape"]]} '
                      f'({escape(en_cours["version"] or "")})</div>')
    cible = MAJ_DISPONIBLE.get("version")
    if cible and not en_cours:
        notes = "".join(f"<li>{escape(n)}</li>" for n in MAJ_DISPONIBLE.get("notes") or [])
        lignes.append(
            f'<div class="nouvelle"><b>{t["maj_disponible"]} : <span class="mono">{escape(cible)}</span></b>'
            f'<ul>{notes}</ul>'
            f'<form method="post"><input type="hidden" name="csrf" value="{jeton}">'
            f'<input type="hidden" name="op" value="update">'
            f'<button>{t["maj_installer"]}</button></form></div>')
    elif not en_cours:
        lignes.append(f'<p class="aide">{t["up_to_date"]}</p>')
    if precedente and not en_cours:
        lignes.append(
            f'<form method="post" class="actions gauche"><input type="hidden" name="csrf" value="{jeton}">'
            f'<input type="hidden" name="op" value="retour">'
            f'<button class="second">{t["maj_revenir"]} ({escape(precedente)})</button></form>')
    return "\n".join(lignes)


def bloc_affichage(t):
    r = affichage.reglages_affichage(CONFIG)

    def heures(nom, choisie):
        return f'<select name="{nom}" class="heure">' + "".join(
            f'<option value="{h}"{" selected" if h == choisie else ""}>{h}</option>'
            for h in range(24)) + "</select>"

    textes = {k[len("theme_"):]: v for k, v in t.items() if k.startswith("theme_")}
    profils = {k[len("profil_"):]: v for k, v in t.items() if k.startswith("profil_")}
    nuits = {k[len("nuit_"):]: v for k, v in t.items() if k in ("nuit_auto", "nuit_jamais", "nuit_toujours")}
    coche = " checked" if r["protection"] else ""
    contenu = f"""
  <input type="hidden" name="csrf" value="{csrf_token()}">
  <input type="hidden" name="op" value="affichage">
  <fieldset><legend>{t['disp_theme']}</legend>
  {choix('ecran_theme', affichage.THEMES, r['theme'], textes, 'themes')}</fieldset>
  <fieldset><legend>{t['disp_profil']}</legend>
  {choix('ecran_profil', affichage.PROFILS, r['profil'], profils)}</fieldset>
  <fieldset><legend>{libelle(t['disp_nuit'])[0]}</legend>
  {choix('ecran_nuit', affichage.MODES_NUIT, r['nuit'], nuits, 'choix court')}
  <p class="heures">{t['nuit_de']} {heures('nuit_debut', r['nuit_debut'])} {t['nuit_a']}
    {heures('nuit_fin', r['nuit_fin'])} {t['nuit_h']}</p></fieldset>
  <label class="interrupteur"><input type="checkbox" name="ecran_protection" value="1"{coche}>
    <span>{t['disp_protection']}</span></label>
  <div class="actions"><button type="submit">{t['disp_save']}</button></div>"""
    return ('<form method="post" action="/config">'
            + groupe("01", t["disp_title"], t["disp_intro"], contenu) + "</form>")


def bloc_capture(t):
    """Section « Capture de l'état » de /config."""
    noms = {s: t.get("sit_" + s, s.capitalize() if s != "dsd" else "DSD") for s in SITUATIONS}
    options = "".join(f'<option value="{s}">{escape(noms[s])}</option>' for s in SITUATIONS)
    captures = liste_captures()
    liste = ""
    if captures:
        liens = "".join(f'<li><a class="mono" href="/captures/{escape(n)}">{escape(n)}</a></li>'
                        for n in captures[:12])
        liste = f'<p class="sous-titre">{t["captures_list"]}</p><ul class="captures">{liens}</ul>'
    contenu = f"""
  <form method="post" action="/config">
    <input type="hidden" name="csrf" value="{csrf_token()}">
    <input type="hidden" name="op" value="capture">
    <label for="situation">{t['capture_situation']}</label>
    <div class="row">
      <select name="situation" id="situation">{options}</select>
      <button type="submit" class="second">{t['capture_btn']}</button>
    </div>
  </form>
  {liste}"""
    return groupe("06", t["capture_title"], t["capture_intro"], contenu)


@app.route("/captures/<nom>")
def telecharger_capture(nom):
    if not logged_in():
        return redirect("/login")
    if not CAPTURE_NOM_RE.fullmatch(nom) or not os.path.isfile(os.path.join(CAPTURES_DIR, nom)):
        return Response(status=404)
    return send_from_directory(CAPTURES_DIR, nom, as_attachment=True, mimetype="application/json")


@app.route("/api/control/<action>", methods=["POST"])
def api_control(action):
    # L'en-tête personnalisé bloque les requêtes forgées depuis un site web.
    if request.headers.get("X-Requested-With") != "eversolo":
        return jsonify({"error": "forbidden"}), 403
    # Réservé à l'administrateur : aucune page ne s'en sert, il reste ouvert
    # aux intégrations (domotique) qui ouvrent une session.
    if not logged_in():
        return jsonify({"error": "unauthorized"}), 401
    if action not in ACTIONS and action not in ("mute", "info"):
        return jsonify({"error": "unknown action"}), 404
    return jsonify({"ok": do_action(action)})


@app.route("/internal/ir", methods=["POST"])
def internal_ir():
    if not requete_locale():
        return jsonify({"error": "forbidden"}), 403
    if request.headers.get("X-Requested-With") != "eversolo":
        return jsonify({"error": "forbidden"}), 403
    try:
        code = str(int(request.args.get("code", "")))
    except ValueError:
        return jsonify({"error": "bad code"}), 400
    LAST_IR.update({"code": code, "time": time.time()})
    action = (CONFIG.get("ir_map") or {}).get(code)
    if action:
        do_action(action)
    return jsonify({"ok": True, "action": action})


@app.route("/api/ir/last")
def api_ir_last():
    if not logged_in():
        return jsonify({"error": "unauthorized"}), 401
    if LAST_IR["code"] and time.time() - LAST_IR["time"] < 15:
        return jsonify({"code": LAST_IR["code"]})
    return jsonify({"code": None})


@app.route("/remote", methods=["GET", "POST"])
def remote_page():
    if load_auth() is None:
        return redirect("/setup")
    if not logged_in():
        return redirect("/login")
    t = tr()
    lang = CONFIG.get("language", "fr")
    message = error = None

    if request.method == "POST":
        if not csrf_ok():
            error = t["session_expired"]
        else:
            action = request.form.get("action", "")
            code = request.form.get("code", "").strip()
            ir_map = dict(CONFIG.get("ir_map") or {})
            if action == "__clear__":
                target = request.form.get("target", "")
                ir_map = {c: a for c, a in ir_map.items() if a != target}
                CONFIG["ir_map"] = ir_map
                save_config(CONFIG)
                message = t["saved"]
            elif code.isdigit() and (action in ACTIONS or action in ("mute", "info")):
                ir_map = {c: a for c, a in ir_map.items() if a != action}
                ir_map[code] = action
                CONFIG["ir_map"] = ir_map
                save_config(CONFIG)
                message = t["saved"]

    ir_map = CONFIG.get("ir_map") or {}
    by_action = {a: c for c, a in ir_map.items()}
    rows = []
    for act in ["play_pause", "next", "previous", "vol_up", "vol_down", "mute", "info"]:
        code = by_action.get(act)
        code_txt = f"code {code}" if code else t["not_paired"]
        rows.append(f"""
<div class="rrow">
  <div class="rname">{t['act_' + act]}<span class="rcode">{code_txt}</span></div>
  <div class="rbtns">
    <button type="button" class="pairbtn" data-action="{act}">{t['pair']}</button>
    <form method="post" style="margin:0">
      <input type="hidden" name="csrf" value="{csrf_token()}">
      <input type="hidden" name="action" value="__clear__">
      <input type="hidden" name="target" value="{act}">
      <button class="ghost" style="margin:0;width:auto;padding:10px 14px" {'disabled' if not code else ''}>{t['clear']}</button>
    </form>
  </div>
</div>""")

    body = f"""
<style>
.rrow{{display:flex;justify-content:space-between;align-items:center;gap:12px;border-bottom:1px solid var(--line);padding:14px 0}}
.rname{{font-size:15px}}
.rcode{{display:block;font-family:"Geist Mono",monospace;font-size:11px;color:var(--muted);margin-top:4px}}
.rbtns{{display:flex;gap:8px;align-items:center}}
.pairbtn{{width:auto;margin:0;padding:10px 16px;font-size:13px}}
.hw{{margin-top:28px;padding-top:22px;border-top:1px solid var(--line)}}
.hwhead{{display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap}}
.hwtitle{{font-size:11px;font-weight:600;letter-spacing:.2em;text-transform:uppercase;color:var(--muted)}}
.dot{{width:7px;height:7px;border-radius:50%;background:var(--faint);flex:0 0 auto}}
.dot.ok{{background:var(--tube);box-shadow:0 0 8px 2px rgba(232,163,61,.5)}}
.dot.ko{{background:#c65a4a}}
.hwstat{{font-size:12px;color:var(--muted)}}
.hwtab{{width:100%;border-collapse:collapse;font-size:13px}}
.hwtab th{{text-align:left;font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--faint);font-weight:500;padding-bottom:8px}}
.hwtab td{{padding:7px 0;border-top:1px solid var(--line);font-family:"Geist Mono",monospace;color:var(--ivory)}}
.hwtab td:last-child{{text-align:right;color:var(--tube)}}
.gp{{color:var(--muted);font-size:11px}}
.hwnote{{font-size:12px;line-height:1.5;color:var(--muted);margin-top:14px}}
.hwres{{margin-top:10px;font-family:"Geist Mono",monospace;font-size:12px;color:var(--muted)}}
.hwres.ok{{color:var(--tube)}}
.hwres.ko{{color:#c65a4a}}
</style>
<h1>{t['remote_title']}</h1>
<p class="intro">{t['remote_intro']}</p>
{f'<div class="msg">{message}</div>' if message else ''}
{f'<div class="msg err">{error}</div>' if error else ''}
{''.join(rows)}
<form method="post" id="pairform" style="display:none">
  <input type="hidden" name="csrf" value="{csrf_token()}">
  <input type="hidden" name="action" id="pf_action">
  <input type="hidden" name="code" id="pf_code">
</form>
<div class="hw">
  <div class="hwhead">
    <span class="hwtitle">{t['hw_title']}</span>
    <span class="dot" id="rxdot"></span><span class="hwstat" id="rxstat">...</span>
  </div>
  <table class="hwtab">
    <tr><th>{t['hw_leg']}</th><th>{t['hw_pin']}</th></tr>
    <tr><td>{t['hw_signal']}</td><td>11 &nbsp;<span class="gp">GPIO17</span></td></tr>
    <tr><td>{t['hw_gnd']}</td><td>6</td></tr>
    <tr><td>{t['hw_vcc']}</td><td>1 &nbsp;<span class="gp">3,3 V</span></td></tr>
  </table>
  <p class="hwnote">{t['hw_note']}</p>
  <button type="button" class="ghost" id="testbtn" style="margin-top:14px">{t['hw_test']}</button>
  <div class="hwres" id="testres"></div>
</div>
<div class="foot"><a href="/blaster">{t['blaster_link']}</a> &nbsp;·&nbsp; <a href="/config">{t['config_title']}</a> &nbsp;·&nbsp; <a href="/">{t['back_display']}</a></div>
<script>
(async function() {{
  try {{
    const d = await (await fetch('/api/ir/status')).json();
    document.getElementById('rxdot').className = 'dot ' + (d.rx ? 'ok' : 'ko');
    document.getElementById('rxstat').textContent = d.rx
      ? {json.dumps(t['hw_rx_ok'])} : {json.dumps(t['hw_rx_ko'])};
  }} catch (e) {{}}
}})();
document.getElementById('testbtn').onclick = async function() {{
  const btn = this, res = document.getElementById('testres');
  const original = btn.textContent;
  btn.textContent = {json.dumps(t['hw_test_wait'])}; btn.disabled = true; res.textContent = '';
  let seen = null;
  try {{ seen = (await (await fetch('/api/ir/last')).json()).code; }} catch (e) {{}}
  const started = Date.now();
  while (Date.now() - started < 15000) {{
    await new Promise(r => setTimeout(r, 500));
    try {{
      const d = await (await fetch('/api/ir/last')).json();
      if (d.code && d.code !== seen) {{
        res.textContent = {json.dumps(t['hw_test_ok'])} + ' (code ' + d.code + ')';
        res.className = 'hwres ok';
        btn.textContent = original; btn.disabled = false;
        return;
      }}
    }} catch (e) {{}}
  }}
  res.textContent = {json.dumps(t['hw_test_ko'])}; res.className = 'hwres ko';
  btn.textContent = original; btn.disabled = false;
}};
document.querySelectorAll('.pairbtn').forEach(function(btn) {{
  btn.onclick = async function() {{
    const original = btn.textContent;
    btn.textContent = {json.dumps(t['press_key'])}; btn.disabled = true;
    const started = Date.now();
    let seen = null;
    try {{ const r0 = await fetch('/api/ir/last'); seen = (await r0.json()).code; }} catch (e) {{}}
    while (Date.now() - started < 20000) {{
      await new Promise(res => setTimeout(res, 500));
      try {{
        const r = await fetch('/api/ir/last');
        const d = await r.json();
        if (d.code && d.code !== seen) {{
          document.getElementById('pf_action').value = btn.dataset.action;
          document.getElementById('pf_code').value = d.code;
          document.getElementById('pairform').submit();
          return;
        }}
      }} catch (e) {{}}
    }}
    btn.textContent = original; btn.disabled = false;
  }};
}});
</script>
"""
    return page(t["remote_title"], body, lang, nav="remote")


@app.route("/api/blast/<name>", methods=["POST"])
def api_blast(name):
    if request.headers.get("X-Requested-With") != "eversolo":
        return jsonify({"error": "forbidden"}), 403
    # Rejouer un code IR allume ou éteint la TV, l'ampli : pas pour les invités.
    if not logged_in():
        return jsonify({"error": "unauthorized"}), 401
    if not csrf_entete_ok():
        return jsonify({"error": "forbidden"}), 403
    if not NAME_RE.fullmatch(name):
        return jsonify({"error": "bad name"}), 400
    path = os.path.join(IR_CODES_DIR, name + ".ir")
    if not os.path.exists(path):
        return jsonify({"error": "unknown"}), 404
    return jsonify({"ok": send_raw(path)})


@app.route("/blaster", methods=["GET", "POST"])
def blaster_page():
    if load_auth() is None:
        return redirect("/setup")
    if not logged_in():
        return redirect("/login")
    t = tr()
    lang = CONFIG.get("language", "fr")
    message = error = None
    os.makedirs(IR_CODES_DIR, exist_ok=True)

    if request.method == "POST":
        if not csrf_ok():
            error = t["session_expired"]
        else:
            op = request.form.get("op", "")
            name = request.form.get("name", "").strip()
            if not NAME_RE.fullmatch(name):
                error = t["bad_name"]
            elif op == "learn":
                # capture synchrone: la page attend la pression de touche
                if record_raw(os.path.join(IR_CODES_DIR, name + ".ir")):
                    message = t["learned"]
                else:
                    error = t["learn_failed"]
            elif op == "delete":
                try:
                    os.remove(os.path.join(IR_CODES_DIR, name + ".ir"))
                    message = t["saved"]
                except FileNotFoundError:
                    pass

    _, tx = lirc_devices()
    warn = "" if tx else f'<div class="msg err">{t["no_tx"]}</div>'
    rows = []
    for f in sorted(glob.glob(os.path.join(IR_CODES_DIR, "*.ir"))):
        n = os.path.basename(f)[:-3]
        rows.append(f'''
<div class="rrow">
  <div class="rname">{n}</div>
  <div class="rbtns">
    <button type="button" class="pairbtn sendbtn" data-name="{n}">{t['send_cmd']}</button>
    <form method="post" style="margin:0">
      <input type="hidden" name="csrf" value="{csrf_token()}">
      <input type="hidden" name="op" value="delete">
      <input type="hidden" name="name" value="{n}">
      <button class="ghost" style="margin:0;width:auto;padding:10px 14px">{t['delete_cmd']}</button>
    </form>
  </div>
</div>''')

    body = f'''
<style>
.rrow{{display:flex;justify-content:space-between;align-items:center;gap:12px;border-bottom:1px solid var(--line);padding:14px 0}}
.rname{{font-family:"Geist Mono",monospace;font-size:14px}}
.rbtns{{display:flex;gap:8px;align-items:center}}
.pairbtn{{width:auto;margin:0;padding:10px 16px;font-size:13px}}
</style>
<h1>{t['blaster_title']}</h1>
<p class="intro">{t['blaster_intro']}</p>
{warn}
{f'<div class="msg">{message}</div>' if message else ''}
{f'<div class="msg err">{error}</div>' if error else ''}
<form method="post" id="learnform">
  <input type="hidden" name="csrf" value="{csrf_token()}">
  <input type="hidden" name="op" value="learn">
  <label>{t['new_name']}</label>
  <div class="row">
    <input type="text" name="name" pattern="[A-Za-z0-9_-]{{1,32}}" required>
    <button type="submit" id="learnbtn">{t['learn']}</button>
  </div>
</form>
{''.join(rows)}
<div class="foot"><a href="/remote">{t['remote_title']}</a> &nbsp;·&nbsp; <a href="/config">{t['config_title']}</a></div>
<script>
document.getElementById('learnform').addEventListener('submit', function() {{
  const b = document.getElementById('learnbtn');
  b.textContent = {json.dumps(t['learn_hint'])}; b.disabled = false;
}});
document.querySelectorAll('.sendbtn').forEach(function(btn) {{
  btn.onclick = async function() {{
    btn.disabled = true;
    try {{
      await fetch('/api/blast/' + btn.dataset.name, {{
        method: 'POST', headers: {{'X-Requested-With': 'eversolo', 'X-CSRF-Token': {json.dumps(csrf_token())}}}
      }});
    }} catch (e) {{}}
    setTimeout(() => btn.disabled = false, 500);
  }};
}});
</script>
'''
    return page(t["blaster_title"], body, lang, nav="blaster")


@app.route("/api/ir/status")
def api_ir_status():
    if not logged_in():
        return jsonify({"error": "unauthorized"}), 401
    rx, tx = lirc_devices()
    # Un peripherique /dev/lirc* n'existe que si l'overlay gpio-ir est actif:
    # c'est la seule preuve fiable que le récepteur est en place.
    lirc_present = bool(glob.glob("/dev/lirc*"))
    overlay = False
    for cfg in ("/boot/firmware/config.txt", "/boot/config.txt"):
        try:
            with open(cfg, encoding="utf-8", errors="ignore") as f:
                if any(l.strip().startswith("dtoverlay=gpio-ir") for l in f):
                    overlay = True
                    break
        except OSError:
            continue
    return jsonify({
        "rx": bool(rx) or (lirc_present and overlay),
        "tx": bool(tx),
        "overlay": overlay,
    })


@app.route("/api/detect")
def api_detect():
    # Pendant la première configuration : le kiosque, ou qui connaît le code
    # affiché sur la TV. Ensuite : l'administrateur seulement.
    if load_auth() is not None:
        if not logged_in():
            return jsonify({"error": "unauthorized"}), 401
    elif not requete_locale() and not verifier_code(request.headers.get("X-Code-Installation"),
                                                    request.remote_addr):
        return jsonify({"error": "code"}), 403
    # Un balayage du réseau à la fois : 254 adresses, c'est lourd pour un Pi 3.
    if not SCAN_VERROU.acquire(blocking=False):
        return jsonify({"error": "busy"}), 429
    try:
        return jsonify({"found": scan_network()})
    finally:
        SCAN_VERROU.release()


@app.route("/api/setup/etat")
def api_setup_etat():
    """Pour l'écran d'installation de la TV : code courant, fin de l'installation."""
    if not requete_locale():
        return jsonify({"error": "forbidden"}), 403
    fait = load_auth() is not None
    return jsonify({"configure": fait, "code": None if fait else code_installation()})


# ----------------------------------------------------------- données lecture


def find_quality(state):
    found = {}
    wanted = {
        "sampleratenumber": "sample_rate", "samplerate": "sample_rate",
        "samplingrate": "sample_rate",
        "bitdepth": "bit_depth", "bits": "bit_depth",
        "bitrate": "bitrate",
        "audioformat": "format", "format": "format", "codec": "format",
    }

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                target = wanted.get(key.lower())
                if target and isinstance(value, (str, int, float)) and value not in ("", 0):
                    found.setdefault(target, value)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(state)

    # Les appareils renvoient parfois du texte ("44.1kHz", "24bit", "320 kbps"):
    # on extrait des valeurs numériques propres, sinon on ecarte le champ.
    def num(value):
        m = re.search(r"\d+(?:[.,]\d+)*", str(value))
        if not m:
            return None
        token = m.group(0)
        # "1,411" ou "44.100" sont des separateurs de milliers, pas des decimales
        if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", token):
            token = re.sub(r"[.,]", "", token)
        else:
            token = token.replace(",", ".")
        try:
            return float(token)
        except ValueError:
            return None

    cleaned = {}
    if "sample_rate" in found:
        v = num(found["sample_rate"])
        if v and v > 0:
            # valeur en kHz si petite, en Hz sinon; l'interface àttend des Hz
            cleaned["sample_rate"] = v * 1000 if v < 1000 else v
    if "bit_depth" in found:
        v = num(found["bit_depth"])
        if v and 8 <= v <= 64:
            cleaned["bit_depth"] = int(v)
    if "bitrate" in found:
        raw = str(found["bitrate"]).lower()
        if "mb" in raw:
            # exprime en megabits ("1,4 Mbps"): virgule decimale, x1000
            m = re.search(r"\d+(?:[.,]\d+)?", raw)
            v = float(m.group(0).replace(",", ".")) * 1000 if m else None
        else:
            v = num(found["bitrate"])
            if v and v > 10000:
                v = v / 1000
        if v and int(v) >= 32:
            cleaned["bitrate"] = int(v)
    if "format" in found:
        tokens = re.findall(r"[A-Za-z]{2,}", str(found["format"]))
        word = next((t for t in tokens if t.lower() not in
                     ("khz", "hz", "bit", "bits", "kbps", "bps")), None)
        if word:
            cleaned["format"] = word
    return cleaned


def absolute_url(path):
    if not path:
        return None
    if path.startswith("http"):
        return path
    return f"{eversolo_base()}{path}"


def normalize(state):
    play_type = state.get("playType")
    etat = affichage.etat_lecture(state)
    lang = CONFIG.get("language", "fr")
    info = {
        "connected": True,
        "playing": etat == "lecture",
        "etat": etat,
        "title": None, "artist": None, "album": None, "cover": None,
        "position": (state.get("position") or 0) / 1000,
        "duration": (state.get("duration") or 0) / 1000,
        "quality": find_quality(state),
        "signal": affichage.signal_audio(state, lang),
        "volume": affichage.lire_volume(state),
        "lang": lang,
        "model": device_model(),
        "server_time": time.time(),
    }

    # Deux emplacements possibles selon la source:
    # - apps de streaming (Spotify Connect, AirPlay) et Bluetooth -> everSoloPlayInfo
    # - lecteur interne (Tidal, Qobuz, fichiers, web radios) -> playingMusic
    # Fusion avec repli croise pour rester robuste face àux playType inconnus.
    audio = (state.get("everSoloPlayInfo") or {}).get("everSoloPlayAudioInfo") or {}
    music = state.get("playingMusic") or {}

    def pick(*values):
        for v in values:
            if isinstance(v, str) and v.strip():
                return v.strip()
        return None

    app_first = play_type in (4, 6)
    a_title = pick(audio.get("songName"), audio.get("title"), audio.get("name"))
    m_title = pick(music.get("title"), music.get("name"), music.get("songName"))
    info["title"] = pick(a_title, m_title) if app_first else pick(m_title, a_title)
    a_artist = pick(audio.get("artistName"), audio.get("artist"))
    m_artist = pick(music.get("artist"), music.get("artistName"))
    info["artist"] = pick(a_artist, m_artist) if app_first else pick(m_artist, a_artist)
    a_album = pick(audio.get("albumName"), audio.get("album"))
    m_album = pick(music.get("album"), music.get("albumName"))
    info["album"] = pick(a_album, m_album) if app_first else pick(m_album, a_album)

    icon = absolute_url(pick((state.get("everSoloPlayInfo") or {}).get("icon")))
    art = absolute_url(pick(music.get("albumArt"), music.get("albumArtUrl"), music.get("icon")))
    by_id = None
    if music.get("id") is not None:
        by_id = f"{eversolo_base()}/ZidooMusicControl/v2/getImage?id={music['id']}&target=16"
    info["cover"] = (icon or art or by_id) if app_first else (art or by_id or icon)

    # Flux en direct (web radio): pas de durée exploitable
    # (à l'arrêt, la durée vaut aussi 0 : ce n'est pas une radio)
    info["live"] = bool(info["title"]) and info["duration"] <= 0 and etat == "lecture"

    info["cover"] = cover_ref(info["cover"])
    return info


STATE_CACHE = {"info": None, "failures": 0, "down_since": None}
PREFETCH = {"artist": None}

# Entrée et sortie actives : relevées en fond, au plus toutes les 30 s.
IO_CACHE = {"ts": 0.0, "sortie": None, "entree": None}
IO_VERROU = threading.Lock()
IO_DUREE = 30
# Plage suivante : cherchée une fois par plage, dans ses dernières secondes.
FILE_CACHE = {"etat": (None, None)}  # (plage, suivante), remplacé d'un bloc
FILE_VERROU = threading.Lock()
SUIVANT_AVANT_FIN = 30


def rafraichir_entrees_sorties():
    if not IO_VERROU.acquire(blocking=False):
        return
    try:
        r = http.get(f"{eversolo_base()}/ZidooMusicControl/v2/getInputAndOutputList", timeout=3)
        donnees = r.json()
        IO_CACHE.update(sortie=affichage.sortie_active(donnees),
                        entree=affichage.entree_active(donnees))
    except (requests.RequestException, ValueError) as exc:
        print(f"[diagnostic] entrées/sorties illisibles : {type(exc).__name__}", flush=True)
    finally:
        IO_CACHE["ts"] = time.time()
        IO_VERROU.release()


def chercher_suivant(cle, index, titre):
    if not FILE_VERROU.acquire(blocking=False):
        return
    try:
        r = http.get(f"{eversolo_base()}/ZidooMusicControl/v2/getPlayQueue",
                     params={"start": index, "count": 2}, timeout=3)
        suivant = affichage.suivant_dans_file(r.json(), index, titre)
    except (requests.RequestException, ValueError) as exc:
        print(f"[diagnostic] file de lecture illisible : {type(exc).__name__}", flush=True)
        suivant = None
    finally:
        FILE_VERROU.release()
    # Une recherche tardive ne doit pas écraser celle d'une plage plus récente.
    if FILE_CACHE["etat"][0] == cle:
        FILE_CACHE["etat"] = (cle, suivant)


def _en_fond(cible, *args):
    threading.Thread(target=cible, args=args, daemon=True).start()


def _depuis_cache(cache, cle):
    entree = cache.get(cle)
    return entree[1] if entree else None


def infos_ecran(brut, info):
    """Ce que l'écran ajoute à l'état : sortie, plage suivante, découvertes,
    réglages. Ne lit que des caches ; les relevés partent en fond."""
    if time.time() - IO_CACHE["ts"] > IO_DUREE:
        IO_CACHE["ts"] = time.time()
        _en_fond(rafraichir_entrees_sorties)

    titre, artiste, album = info.get("title"), info.get("artist"), info.get("album")
    index = brut.get("trackIndex")
    cle_file = (titre, index)
    reste = info["duration"] - info["position"]
    if (info["etat"] == "lecture" and not info["live"] and 0 < reste < SUIVANT_AVANT_FIN
            and isinstance(index, int) and index >= 0 and FILE_CACHE["etat"][0] != cle_file):
        FILE_CACHE["etat"] = (cle_file, None)
        _en_fond(chercher_suivant, cle_file, index, titre)
    cle_connue, suivant = FILE_CACHE["etat"]
    ensuite = suivant if cle_connue == cle_file else None

    lang = info["lang"]
    fiche_album = fiche_art = None
    plage = []
    if artiste:
        a, al = artiste.lower(), (album or "").lower()
        fiche_album = _depuis_cache(ALBUM_CACHE, (a, al, lang)) if album else None
        bio = _depuis_cache(ARTIST_CACHE, (a, al, lang))
        if bio:
            fiche_art = {"name": bio.get("artist"), "facts": bio.get("facts") or [],
                         "text": bio.get("text")}
        if titre:
            plage = _depuis_cache(TRACK_CACHE, (a, titre.lower(), lang)) or []
    return {
        "sortie": IO_CACHE["sortie"],
        "entree": IO_CACHE["entree"],
        "ensuite": ensuite,
        "decouvertes": affichage.decouvertes(titre, fiche_album, fiche_art, plage,
                                             info["signal"], IO_CACHE["sortie"], lang),
        "display": affichage.reglages_affichage(CONFIG),
    }


@app.route("/favicon.ico")
def favicon():
    return app.send_static_file("favicon.ico")


ETAT_INEXPLOITABLE = {"quand": 0.0}


def etat_de_repli(panne_reseau):
    """Un raté isolé (Wi-Fi, streamer occupé) ne doit pas faire clignoter
    « introuvable » : on ressert le dernier état connu quelques secondes."""
    STATE_CACHE["failures"] += 1
    if panne_reseau and STATE_CACHE["failures"] >= 3 and not STATE_CACHE["down_since"]:
        STATE_CACHE["down_since"] = time.time()
        print(f"[diagnostic] Eversolo injoignable ({CONFIG.get('eversolo_ip')})", flush=True)
    if STATE_CACHE["info"] and STATE_CACHE["failures"] < 3:
        stale = dict(STATE_CACHE["info"])
        stale["server_time"] = time.time()
        return jsonify(stale)
    return jsonify({
        "connected": False,
        "lang": CONFIG.get("language", "fr"),
        "server_time": time.time(),
    })


def noter_etat_inexploitable(exc):
    """Le streamer a répondu mais sa réponse n'a pas pu être mise en forme :
    une ligne au journal, une par minute au plus, avec l'endroit de l'erreur."""
    if time.time() - ETAT_INEXPLOITABLE["quand"] < 60:
        return
    ETAT_INEXPLOITABLE["quand"] = time.time()
    lieu = ""
    pile = traceback.extract_tb(exc.__traceback__)
    if pile:
        lieu = f" ({pile[-1].name}:{pile[-1].lineno})"
    print(f"[diagnostic] réponse du streamer inexploitable : {type(exc).__name__}{lieu}",
          flush=True)


def precharger_fiches(info):
    """Trois recherches indépendantes, lancées de front à chaque nouvelle plage :
    chacune arrive à son rythme, aucune n'attend les autres."""
    artiste = info.get("artist")
    cle_pf = (artiste, info.get("album"), info.get("title"))
    if not artiste or cle_pf == PREFETCH["artist"]:
        return
    PREFETCH["artist"] = cle_pf
    lg = CONFIG.get("language", "fr")
    al, ti = info.get("album"), info.get("title")
    for cible in (
        lambda: fetch_artist_info(artiste, lg, al),
        lambda: fetch_album_info(artiste, al, lg),
        lambda: fetch_track_credits(artiste, ti, lg),
    ):
        threading.Thread(target=cible, daemon=True).start()


@app.route("/api/state")
def api_state():
    if not is_configured():
        return jsonify({"connected": False, "setup": True})
    try:
        r = http.get(f"{eversolo_base()}/ZidooMusicControl/v2/getState", timeout=3)
        r.raise_for_status()
        brut = r.json()
    except Exception:
        return etat_de_repli(panne_reseau=True)
    try:
        info = normalize(brut)
        info["rev"] = LOCAL_REV
        info.update(infos_ecran(brut, info))
        info["maj"] = maj_en_cours() if requete_locale() else None
        precharger_fiches(info)
    except Exception as exc:
        noter_etat_inexploitable(exc)
        return etat_de_repli(panne_reseau=False)
    if STATE_CACHE["down_since"]:
        durée = int(time.time() - STATE_CACHE["down_since"])
        print(f"[diagnostic] Eversolo de retour après {durée} s d'indisponibilité", flush=True)
    STATE_CACHE.update({"info": info, "failures": 0, "down_since": None})
    # une seule lecture : le volet peut être fermé par une touche pendant le relevé
    volet = ARTIST_PANEL["data"]
    if volet and ARTIST_PANEL["until"] > time.time():
        noter_longueur_volet(request.args.get("volet_pas", ""))
        info = {**info, "panel": {**volet, "scroll": ARTIST_PANEL["scroll"],
                                  "page": ARTIST_PANEL["page"]}}
    return jsonify(info)


def adresse_privee(texte):
    try:
        addr = ipaddress.ip_address(texte)
    except ValueError:
        return True
    return (addr.is_private or addr.is_loopback or addr.is_link_local
            or addr.is_reserved or addr.is_multicast or addr.is_unspecified)


def host_is_private(hostname):
    """Vrai si l'hote resout vers une adresse privee, locale ou reservee."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except Exception:
        return True
    return any(adresse_privee(info[4][0]) for info in infos)


def ip_du_pair(reponse):
    """Adresse réellement jointe par la connexion, quand urllib3 la donne."""
    try:
        return reponse.raw._connection.sock.getpeername()[0]
    except Exception:
        return None


# Le proxy ne sert que les images que le serveur a lui-même désignées (état de
# lecture, photos d'artistes) : plus d'URL libre, donc plus de relais ouvert.
COVERS = OrderedDict()
COVERS_VERROU = threading.Lock()
COVERS_MAX = 512


def cover_ref(url):
    """Chemin local d'une image distante, par identifiant stable."""
    if not url:
        return None
    if url.startswith("/api/cover?"):
        # Fiches mises en cache par les versions précédentes (?u=URL).
        url = (parse_qs(urlparse(url).query).get("u") or [""])[0]
        if not url:
            return None
    ident = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
    with COVERS_VERROU:
        COVERS[ident] = url
        COVERS.move_to_end(ident)
        while len(COVERS) > COVERS_MAX:
            COVERS.popitem(last=False)
    return "/api/cover?id=" + ident


COVER_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"}
COVER_MAX_OCTETS = 5 * 1024 * 1024
COVER_MAX_REDIRECTIONS = 3


CHEMINS_IMAGES_STREAMER = re.compile(
    r"/ZidooMusicControl/v2/getImage|/SystemSettings/getItemSettingIcon"
    r"|/[A-Za-z0-9_./%-]*\.(?:jpe?g|png|webp|gif|bmp)", re.IGNORECASE)


def image_du_streamer(chemin):
    return bool(CHEMINS_IMAGES_STREAMER.fullmatch(chemin or ""))


def _cover_refus():
    # Même réponse pour tous les refus et échecs: le proxy ne doit pas servir
    # à sonder quels ports ou machines répondent sur le réseau local.
    return Response(status=502)


@app.route("/api/cover")
def api_cover():
    with COVERS_VERROU:
        url = COVERS.get(request.args.get("id", ""))
    if not url:
        return Response(status=404)
    streamer = {
        f"{CONFIG['eversolo_ip']}:{CONFIG['eversolo_port']}",
        CONFIG["eversolo_ip"],
    }
    # Anti SSRF, en plus de la liste des images désignées : le streamer
    # configuré est toujours autorisé ; tout autre hôte doit être public (les pochettes Tidal/Qobuz/Spotify/radios viennent de
    # CDN externes). Les redirections sont suivies à la main pour revalider
    # chaque destination: un hôte public ne peut pas renvoyer vers le LAN.
    try:
        for saut in range(COVER_MAX_REDIRECTIONS + 1):
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                return _cover_refus()
            # Le streamer a des commandes en GET (muet, suivant…) : seules ses
            # adresses d'images sont lues, et jamais au bout d'une redirection.
            du_streamer = parsed.netloc in streamer
            if du_streamer and (saut or not image_du_streamer(parsed.path)):
                return _cover_refus()
            if not du_streamer and host_is_private(parsed.hostname):
                return _cover_refus()
            r = http.get(url, timeout=5, stream=True, allow_redirects=False)
            pair = ip_du_pair(r)
            if not du_streamer and pair and adresse_privee(pair):
                # Le nom a changé d'adresse entre la vérification et la
                # connexion (rebinding DNS) : on ne lit rien.
                r.close()
                return _cover_refus()
            if r.is_redirect:
                url = requests.compat.urljoin(url, r.headers.get("Location", ""))
                r.close()
                continue
            break
        else:
            return _cover_refus()
        with r:
            r.raise_for_status()
            ctype = r.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if ctype not in COVER_TYPES:
                # SVG, HTML ou XML refusés: ils peuvent contenir du script
                # exécuté sous l'origine du Pi. Le streamer, qui ne type pas
                # toujours ses images, est servi en JPEG neutre.
                if not du_streamer:
                    return _cover_refus()
                ctype = "image/jpeg"
            longueur = r.headers.get("Content-Length")
            if longueur and longueur.isdigit() and int(longueur) > COVER_MAX_OCTETS:
                return _cover_refus()
            contenu = bytearray()
            for morceau in r.iter_content(64 * 1024):
                contenu.extend(morceau)
                if len(contenu) > COVER_MAX_OCTETS:
                    return _cover_refus()
        resp = Response(bytes(contenu), content_type=ctype)
        resp.headers["Cache-Control"] = "max-age=86400"
        resp.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
        return resp
    except Exception:
        return _cover_refus()


if load_auth() is None:
    # Tiré dès le démarrage : le journal le donne sans attendre un premier essai.
    code_installation()


if __name__ == "__main__":
    from waitress import serve
    valider_au_demarrage(CONFIG["listen_port"])
    serve(app, host="0.0.0.0", port=CONFIG["listen_port"], threads=8)
