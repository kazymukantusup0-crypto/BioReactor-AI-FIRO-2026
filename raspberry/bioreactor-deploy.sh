#!/usr/bin/env bash
# BioReactor AI — put the bridge code that scripts/deploy_to_pi.ps1 copied to ~/BioReactor_AI/raspberry into
# /opt/bioreactor-pi and restart the service. Installed by install.sh as /usr/local/sbin/bioreactor-deploy (root:root 755)
# with ONE sudoers rule: the deploying user may run exactly this file, with no arguments, without a password.
#
# SECURITY: the source folder belongs to that user, so root NEVER opens a path in it. Every read is done by a process
# running AS THE USER (sudo -u), root only writes the bytes it receives into its own new folder. So a symlink planted in
# the user's folder (to /etc/shadow, /root, /etc ...) can only reach what the user could read anyway, and nothing in
# that folder can make root change, follow or copy a system file. Accepted: flat files *.py / *.json with plain names
# (the package has no sub-folders), regular files only, at most 512 KB each; the version stamp: 120 safe characters.
# The code then runs as the unprivileged service user «bioreactor». Unit, config and network scripts are never taken.
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
umask 022
OWNER="${SUDO_USER:-}"
if [[ -z "$OWNER" || "$OWNER" == "root" ]] || ! id "$OWNER" >/dev/null 2>&1; then
  echo "Run as: sudo /usr/local/sbin/bioreactor-deploy (from the deploying user)" >&2
  exit 1
fi
as_user() { sudo -n -u "$OWNER" -- "$@"; }        # reads happen with the user's rights only
USER_HOME="$(getent passwd "$OWNER" | cut -d: -f6)"
SRC="$USER_HOME/BioReactor_AI/raspberry/bioreactor_pi"
APP=/opt/bioreactor-pi
NEW="$APP/bioreactor_pi.new"

# the list of files, made by the user's process: regular files only (find -type f does not follow symlinks)
mapfile -t NAMES < <(as_user find "$SRC" -mindepth 1 -maxdepth 1 -type f \( -name '*.py' -o -name '*.json' \) -printf '%f\n' | sort)
if (( ${#NAMES[@]} == 0 )); then
  echo "No code in $SRC — copy it first (scripts/deploy_to_pi.ps1)." >&2
  exit 1
fi
rm -rf "$NEW"
install -d -o root -g root -m 755 "$NEW"
for name in "${NAMES[@]}"; do
  [[ "$name" =~ ^[A-Za-z0-9_]+\.(py|json)$ ]] || { echo "refused file name: $name" >&2; rm -rf "$NEW"; exit 1; }
  # the user's process opens the file; -L check inside it refuses a symlink swapped in after the listing
  as_user sh -c 'f="$1"; [ -f "$f" ] && [ ! -L "$f" ] && head -c 524289 -- "$f"' _ "$SRC/$name" > "$NEW/$name" \
    || { echo "could not read $name as $OWNER" >&2; rm -rf "$NEW"; exit 1; }
  if (( $(stat -c %s "$NEW/$name") > 524288 )); then echo "too big: $name" >&2; rm -rf "$NEW"; exit 1; fi
  chmod 644 "$NEW/$name"
done
[[ -f "$NEW/__main__.py" ]] || { echo "no __main__.py — not the bridge package" >&2; rm -rf "$NEW"; exit 1; }
rm -rf "$APP/bioreactor_pi.old"
[[ -d "$APP/bioreactor_pi" ]] && mv "$APP/bioreactor_pi" "$APP/bioreactor_pi.old"
mv "$NEW" "$APP/bioreactor_pi"
STAMP="$(as_user sh -c 'f="$1"; [ -f "$f" ] && [ ! -L "$f" ] && head -c 200 -- "$f"' _ "$USER_HOME/BioReactor_AI/raspberry/DEPLOYED" 2>/dev/null \
  | tr -cd 'A-Za-z0-9 .:+_-' | head -c 120 || true)"
printf '%s\n' "${STAMP:-unknown}" > "$APP/DEPLOYED"
chmod 644 "$APP/DEPLOYED"
systemctl restart bioreactor-pi
echo "bridge code updated (${#NAMES[@]} files, ${STAMP:-no stamp}), service restarted"
