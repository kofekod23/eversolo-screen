#!/bin/bash
# Execute sur le Pi (root): installe eversolo-screen pour l'utilisateur principal.
exec >> /var/log/eversolo-provision.log 2>&1
echo "=== provision démarrée: $(date) ==="
for i in $(seq 1 90); do
    curl -sI --max-time 5 https://github.com > /dev/null 2>&1 && break
    sleep 5
done
USERNAME="$(id -nu 1000)"
if [ -z "$USERNAME" ]; then echo "Utilisateur 1000 introuvable"; exit 1; fi
apt-get update
apt-get install -y git curl
runuser -l "$USERNAME" -c 'test -d eversolo-screen || git clone https://github.com/kofekod23/eversolo-screen.git'
runuser -l "$USERNAME" -c 'cd eversolo-screen && git pull --ff-only || true'
runuser -l "$USERNAME" -c 'cd eversolo-screen && ./install.sh --kiosk'
systemctl disable eversolo-provision.service 2>/dev/null || true
echo "=== provision terminée: $(date) ==="
