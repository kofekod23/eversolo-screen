#!/usr/bin/env bash
# A lancer sur macOS juste apres avoir flashe la carte avec Raspberry Pi Imager
# (en ayant utilise "Modifier les reglages": utilisateur, SSH, Wi-Fi).
#
# Depose un auto-installateur sur la carte: au premier demarrage, le Pi
# installe eversolo-screen et le kiosque tout seul, sans SSH ni clavier.
#
# Usage : bash prepare-sd.sh [chemin_partition_boot]
set -e

BOOT="$1"
if [ -z "$BOOT" ]; then
    for cand in /Volumes/bootfs /Volumes/boot; do
        if [ -d "$cand" ]; then BOOT="$cand"; break; fi
    done
fi
if [ -z "$BOOT" ] || [ ! -d "$BOOT" ]; then
    echo "Partition de demarrage introuvable."
    echo "Debranchez puis rebranchez la carte SD apres le flash, et relancez ce script."
    exit 1
fi

FR="$BOOT/firstrun.sh"
UD="$BOOT/user-data"

# Images recentes (Raspberry Pi OS Trixie + Imager 2.0): mecanisme cloud-init
if [ ! -f "$FR" ] && [ -f "$UD" ]; then
    if grep -q "eversolo-screen/main/tools/bootstrap.sh" "$UD"; then
        echo "La carte est deja preparee, rien a faire."
        exit 0
    fi
    if grep -q "^runcmd:" "$UD"; then
        # une section runcmd existe deja: on y ajoute notre commande
        TMPUD="$(mktemp)"
        awk '{print} /^runcmd:/ && !done {print "  - [ sh, -c, \"apt-get update && apt-get install -y curl && curl -fsSL https://raw.githubusercontent.com/kofekod23/eversolo-screen/main/tools/bootstrap.sh | bash\" ]"; done=1}' "$UD" > "$TMPUD"
        cp "$TMPUD" "$UD"; rm -f "$TMPUD"
    else
        cat >> "$UD" << 'FIN_CLOUD'

runcmd:
  - [ sh, -c, "apt-get update && apt-get install -y curl && curl -fsSL https://raw.githubusercontent.com/kofekod23/eversolo-screen/main/tools/bootstrap.sh | bash" ]
FIN_CLOUD
    fi
    echo "Carte preparee (mecanisme cloud-init)."
    echo "1. Ejectez la carte proprement, inserez-la dans le Raspberry, branchez."
    echo "2. Attendez 10 a 15 minutes: le Pi installe tout seul."
    echo "3. Ouvrez http://eversolo.local:8080 pour la premiere configuration."
    exit 0
fi

if [ ! -f "$FR" ]; then
    echo "Ni firstrun.sh ni user-data sur la carte."
    echo "Refaites le flash avec Raspberry Pi Imager en passant par 'Modifier les reglages'"
    echo "(nom d'utilisateur, mot de passe, Wi-Fi, SSH)."
    exit 1
fi

if grep -q "eversolo-provision" "$FR"; then
    echo "La carte est deja preparee, rien a faire."
    exit 0
fi

BLOCK="$(mktemp)"
cat > "$BLOCK" << 'FIN_BLOC'
# --- eversolo-screen : auto-installation au premier demarrage ---
install -m 0755 /dev/stdin /usr/local/sbin/eversolo-provision.sh << 'FIN_PROV'
#!/bin/bash
exec >> /var/log/eversolo-provision.log 2>&1
echo "=== provision demarree: $(date) ==="
for i in $(seq 1 90); do
    curl -sI --max-time 5 https://github.com > /dev/null 2>&1 && break
    sleep 5
done
USERNAME="$(id -nu 1000)"
if [ -z "$USERNAME" ]; then echo "Utilisateur 1000 introuvable"; exit 1; fi
apt-get update
apt-get install -y git curl
runuser -l "$USERNAME" -c 'test -d eversolo-screen || git clone https://github.com/kofekod23/eversolo-screen.git'
runuser -l "$USERNAME" -c 'cd eversolo-screen && ./install.sh --kiosk'
systemctl disable eversolo-provision.service
echo "=== provision terminee: $(date) ==="
FIN_PROV
cat > /etc/systemd/system/eversolo-provision.service << 'FIN_UNIT'
[Unit]
Description=Auto-installation eversolo-screen
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/sbin/eversolo-provision.sh
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
FIN_UNIT
mkdir -p /etc/systemd/system/multi-user.target.wants
ln -sf /etc/systemd/system/eversolo-provision.service /etc/systemd/system/multi-user.target.wants/eversolo-provision.service
# --- fin eversolo-screen ---
FIN_BLOC

OUT="$(mktemp)"
head -n 1 "$FR" > "$OUT"
cat "$BLOCK" >> "$OUT"
tail -n +2 "$FR" >> "$OUT"
cp "$OUT" "$FR"
rm -f "$BLOCK" "$OUT"

echo "Carte preparee."
echo "1. Ejectez la carte proprement (Finder ou: diskutil eject '$BOOT')."
echo "2. Inserez-la dans le Raspberry, branchez ecran puis alimentation."
echo "3. Attendez 10 a 15 minutes: le Pi telecharge et installe tout seul."
echo "4. Ouvrez http://eversolo.local:8080 pour la premiere configuration."
