#!/usr/bin/env bash
# BioReactor AI — the last «sudo» with a password:
#   1. sudo WITHOUT a password for the user who runs this (bio):  /etc/sudoers.d/010-bio-nopasswd
#   2. SSH ONLY with a key: PasswordAuthentication no, KbdInteractiveAuthentication no  (/etc/ssh/sshd_config.d/01-...)
#      The console (monitor + keyboard on the Pi) still asks for the password — the way in if the laptop is lost.
# Safety:
#   - stops if ~/.ssh/authorized_keys of that user is missing/empty/has wrong rights (no key = no way in over SSH)
#   - every file is checked first (visudo -cf, sshd -t) and only then put in place
#   - the SSH change is on probation: unless someone logs in WITH THE KEY in a NEW session and runs
#     «touch /tmp/ssh-keys-ok» within 5 min, the SSH change is undone by itself (sudo stays passwordless)
#   sudo ./ssh_keys_only.sh            apply            sudo ./ssh_keys_only.sh undo     password SSH + sudo password back
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Run with sudo" >&2; exit 1; }
U="${SUDO_USER:-}"
[[ -n "$U" && "$U" != "root" ]] || { echo "Run as: sudo $0 (from the user bio)" >&2; exit 1; }
HOME_U="$(getent passwd "$U" | cut -d: -f6)"
SUDOERS=/etc/sudoers.d/010-${U}-nopasswd
SSHD=/etc/ssh/sshd_config.d/01-bioreactor-keys-only.conf

if [[ "${1:-}" == "undo" ]]; then
  rm -f "$SSHD" "$SUDOERS"
  sshd -t && systemctl reload ssh
  echo "undone: SSH accepts passwords again, sudo asks for the password again"
  exit 0
fi

echo "[1/4] the key of $U"
AK="$HOME_U/.ssh/authorized_keys"
if [[ ! -s "$AK" ]] || ! grep -qE '^(ssh-ed25519|ssh-rsa|ecdsa-sha2-)' "$AK"; then
  echo "STOP: $AK has no key — SSH by password stays on, nothing changed." >&2; exit 1
fi
[[ "$(stat -c %U "$AK")" == "$U" && "$(stat -c %a "$AK")" =~ ^6[04]0$ && "$(stat -c %a "$HOME_U/.ssh")" == "700" ]] \
  || { echo "STOP: wrong owner/rights on $HOME_U/.ssh (need 700) or $AK (600) — nothing changed." >&2; exit 1; }
passwd -S "$U" | grep -q " P " || echo "WARNING: $U has no usable password — the console login would not work"
echo "      $(wc -l < "$AK") key(s): $(cut -d' ' -f3- "$AK" | tr '\n' ' ')"

echo "[2/4] sudo without a password for $U"
TMP="$(mktemp)"; printf '# BioReactor AI: %s uses sudo without a password (SSH is key-only)\n%s ALL=(ALL) NOPASSWD: ALL\n' "$U" "$U" > "$TMP"
chmod 440 "$TMP"
visudo -cf "$TMP" >/dev/null || { rm -f "$TMP"; echo "STOP: visudo rejected the rule" >&2; exit 1; }
mv "$TMP" "$SUDOERS"; chown root:root "$SUDOERS"
rm -f /etc/sudoers.d/zz-session-only
visudo -c >/dev/null && echo "      visudo -c: OK"

echo "[3/4] SSH: key only"
TMP="$(mktemp)"
printf '# BioReactor AI: SSH only with a key; the console still uses the password\nPubkeyAuthentication yes\nPasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin no\n' > "$TMP"
chmod 644 "$TMP"
mv "$TMP" "$SSHD"
if ! sshd -t; then rm -f "$SSHD"; echo "STOP: sshd rejected the config — removed, SSH unchanged" >&2; exit 1; fi
sshd -T 2>/dev/null | grep -E '^(passwordauthentication|kbdinteractiveauthentication|pubkeyauthentication|permitrootlogin) '
sshd -T 2>/dev/null | grep -q '^passwordauthentication no' || { rm -f "$SSHD"; echo "STOP: another file still allows passwords — removed" >&2; exit 1; }
rm -f /tmp/ssh-keys-ok
systemctl reload ssh

echo "[4/4] probation: 5 min to log in with the key in a NEW session and run: touch /tmp/ssh-keys-ok"
systemctl stop ssh-keys-probation.timer >/dev/null 2>&1 || true
systemd-run --quiet --on-active=300 --unit=ssh-keys-probation /bin/sh -c \
  "test -f /tmp/ssh-keys-ok && logger -t bioreactor-ssh 'key-only SSH confirmed' || { rm -f $SSHD; systemctl reload ssh; logger -t bioreactor-ssh 'key-only SSH NOT confirmed: passwords allowed again'; }"
echo "Done. sudo: no password. SSH: key only (confirm within 5 min). Console: password, as before."
