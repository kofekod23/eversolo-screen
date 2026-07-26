#!/bin/bash
# Lance par cloud-init au premier démarrage (root): installe le service de
# provision qui réessaie a chaque démarrage jusqu'à réussite.
set -e
curl -fsSL https://raw.githubusercontent.com/kofekod23/eversolo-screen/main/tools/provision.sh \
    -o /usr/local/sbin/eversolo-provision.sh
chmod 0755 /usr/local/sbin/eversolo-provision.sh
cat > /etc/systemd/system/eversolo-provision.service << 'UNIT'
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
UNIT
systemctl daemon-reload
systemctl enable eversolo-provision.service
systemctl start eversolo-provision.service
