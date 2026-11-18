#!/usr/bin/env bash
# BioReactor AI — a sudo password typed in one terminal works ONLY in that terminal (not in other SSH sessions,
# not in sessions without a terminal). Adds /etc/sudoers.d/zz-session-only (read last, so it wins):
#     Defaults timestamp_type=tty
# The file is checked with visudo BEFORE it is put in place: a broken sudoers file could lock sudo out.
#   sudo ./sudo_session_only.sh            install          sudo ./sudo_session_only.sh remove     undo
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Run with sudo" >&2; exit 1; }
FILE=/etc/sudoers.d/zz-session-only
if [[ "${1:-}" == "remove" ]]; then
  rm -f "$FILE"; echo "removed $FILE"; exit 0
fi
echo "timestamp settings before:"
grep -rhs "timestamp" /etc/sudoers /etc/sudoers.d/ | grep -v '^#' || echo "  (none: sudo defaults)"
TMP="$(mktemp)"
printf '# BioReactor AI: a sudo password counts only in the terminal where it was typed\nDefaults timestamp_type=tty\n' > "$TMP"
chmod 440 "$TMP"
if visudo -cf "$TMP" >/dev/null; then
  mv "$TMP" "$FILE"
  chown root:root "$FILE"
else
  rm -f "$TMP"; echo "visudo rejected the file — nothing changed" >&2; exit 1
fi
visudo -c >/dev/null && echo "sudoers OK"
rm -rf /run/sudo/ts/* 2>/dev/null || true      # forget every saved sudo password now (all sessions)
echo "installed $FILE: $(grep -v '^#' "$FILE")"
