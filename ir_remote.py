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
    """Trouve le peripherique du récepteur infrarouge GPIO.

    Plusieurs peripheriques rc coexistent souvent (le CEC du HDMI en expose
    un aussi): on identifie explicitement le capteur gpio_ir_recv, sinon on
    ecouterait le mauvais et aucune touche ne serait vue.
    """
    candidates = []
    for rc in sorted(glob.glob("/sys/class/rc/rc*")):
        events = sorted(glob.glob(os.path.join(rc, "input*/event*")))
        if not events:
            continue
        dev = "/dev/input/" + os.path.basename(events[0])
        info = ""
        for meta in glob.glob(os.path.join(rc, "input*/name")) + [
            os.path.join(rc, "uevent")
        ]:
            try:
                with open(meta, encoding="utf-8", errors="ignore") as f:
                    info += f.read().lower()
            except OSError:
                pass
        link = os.path.join(rc, "device", "driver")
        if os.path.islink(link):
            info += os.path.basename(os.path.realpath(link)).lower()
        if "gpio_ir_recv" in info or "gpio-ir" in info:
            return dev
        candidates.append(dev)
    return candidates[0] if candidates else None


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
    print(f"demon IR démarre, serveur local sur le port {port}", flush=True)
    last_code, last_time = None, 0.0

    while True:
        device = find_rc_device()
        if not device:
            print("récepteur IR introuvable (overlay gpio-ir actif ?), nouvel essai dans 15 s", flush=True)
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
            print("accès refuse au peripherique, verifier que le service tourne en root", flush=True)
            time.sleep(30)
        except Exception as exc:
            print(f"lecture interrompue ({exc}), reprise dans 5 s", flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
