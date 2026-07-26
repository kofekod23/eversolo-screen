#!/usr/bin/env python3
"""Demon infrarouge eversolo-screen.

Lit les codes decodes par le noyau (capteur TSOP sur GPIO, overlay gpio-ir)
et les transmet au serveur local, qui applique le mappage appris et pilote
l'Eversolo. Aucune dependance externe.
"""

import glob
import json
import os
import struct
import time
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

EV_MSC = 0x04
MSC_SCAN = 0x04
EVENT_FORMAT = "llHHI"
EVENT_SIZE = struct.calcsize(EVENT_FORMAT)


def listen_port():
    try:
        with open(os.path.join(BASE_DIR, "config.json"), encoding="utf-8") as f:
            return int(json.load(f).get("listen_port", 8080))
    except Exception:
        return 8080


def find_rc_device():
    """Trouve le peripherique d'entree du recepteur infrarouge."""
    for path in glob.glob("/sys/class/rc/rc*/input*/event*"):
        return "/dev/input/" + os.path.basename(path)
    return None


def forward(port, code, when_ok=None):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/internal/ir?code={code}",
        method="POST",
        headers={"X-Requested-With": "eversolo"},
    )
    try:
        urllib.request.urlopen(req, timeout=3).read()
        if when_ok:
            when_ok()
    except Exception as exc:
        print(f"transmission impossible: {exc}", flush=True)


def main():
    port = listen_port()
    print(f"demon IR demarre, serveur local sur le port {port}", flush=True)
    last_code, last_time = None, 0.0

    while True:
        device = find_rc_device()
        if not device:
            print("recepteur IR introuvable (overlay gpio-ir actif ?), nouvel essai dans 15 s", flush=True)
            time.sleep(15)
            continue
        print(f"lecture de {device}", flush=True)
        try:
            with open(device, "rb") as f:
                while True:
                    data = f.read(EVENT_SIZE)
                    if len(data) < EVENT_SIZE:
                        break
                    _, _, etype, ecode, value = struct.unpack(EVENT_FORMAT, data)
                    if etype != EV_MSC or ecode != MSC_SCAN:
                        continue
                    now = time.monotonic()
                    # anti-rebond: on ignore les repetitions immediates du
                    # protocole, mais une touche maintenue continue d'agir
                    if value == last_code and now - last_time < 0.25:
                        continue
                    last_code, last_time = value, now
                    forward(port, value)
        except PermissionError:
            print("acces refuse au peripherique, verifier que le service tourne en root", flush=True)
            time.sleep(30)
        except Exception as exc:
            print(f"lecture interrompue ({exc}), reprise dans 5 s", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
