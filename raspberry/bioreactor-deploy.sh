#!/usr/bin/env bash
# BioReactor AI — put the bridge code that scripts/deploy_to_pi.ps1 copied to ~/BioReactor_AI/raspberry into
# /opt/bioreactor-pi and restart the service. Installed by install.sh as /usr/local/sbin/bioreactor-deploy (root-owned)
# with ONE sudoers rule: the deploying user may run exactly this file without a password.
#
# It only copies the Python package bioreactor_pi (it runs as the unprivileged user «bioreactor») and the version
# stamp. It never takes the systemd unit, the config, the network scripts or anything run as root from the user's
# folder — those still need «sudo ./install.sh» / «sudo ./setup_network.sh ...».
set -euo pipefail
USER_HOME="$(getent passwd "${SUDO_USER:-bio}" | cut -d: -f6)"
SRC="$USER_HOME/BioReactor_AI/raspberry"
APP=/opt/bioreactor-pi
if [[ ! -f "$SRC/bioreactor_pi/__main__.py" ]]; then
  echo "No code in $SRC/bioreactor_pi — copy it first (scripts/deploy_to_pi.ps1)." >&2
  exit 1
fi
rm -rf "$APP/bioreactor_pi.new"
cp -r "$SRC/bioreactor_pi" "$APP/bioreactor_pi.new"
find "$APP/bioreactor_pi.new" -name "__pycache__" -prune -exec rm -rf {} +
chown -R root:root "$APP/bioreactor_pi.new"
chmod -R a+rX,go-w "$APP/bioreactor_pi.new"
rm -rf "$APP/bioreactor_pi.old"
[[ -d "$APP/bioreactor_pi" ]] && mv "$APP/bioreactor_pi" "$APP/bioreactor_pi.old"
mv "$APP/bioreactor_pi.new" "$APP/bioreactor_pi"
if [[ -f "$SRC/DEPLOYED" ]]; then
  head -c 200 "$SRC/DEPLOYED" > "$APP/DEPLOYED"
  chmod 644 "$APP/DEPLOYED"
fi
systemctl restart bioreactor-pi
echo "bridge code updated ($(cat "$APP/DEPLOYED" 2>/dev/null || echo 'no stamp')), service restarted"
