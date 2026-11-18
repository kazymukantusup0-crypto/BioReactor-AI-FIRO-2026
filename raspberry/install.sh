#!/usr/bin/env bash
# BioReactor AI — install the Raspberry Pi bridge (works WITHOUT internet: pyserial comes from ./wheels).
#
#   cd ~/BioReactor_AI/raspberry && sudo ./install.sh            install + autostart (systemd)
#   sudo ./install.sh --simulate                                  same, but with the virtual Arduino (no hardware)
#
# What it does:
#   /opt/bioreactor-pi/            code (bioreactor_pi) + its own Python venv with pyserial
#   /etc/bioreactor-pi/config.json settings (created once from default_config.json; edit it, then restart)
#   /var/lib/bioreactor-pi/        SQLite journal
#   user "bioreactor" in group "dialout" (access to /dev/ttyACM*, /dev/ttyUSB*)
#   systemd service "bioreactor-pi": starts at boot, restarts after a crash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo ./install.sh" >&2
  exit 1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP=/opt/bioreactor-pi
CONF=/etc/bioreactor-pi
DATA=/var/lib/bioreactor-pi
SIMULATE=""
if [[ "${1:-}" == "--simulate" ]]; then SIMULATE="--simulate"; fi

echo "[1/5] user 'bioreactor' (group dialout for the USB port)"
if ! id bioreactor >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin bioreactor
fi
usermod -a -G dialout bioreactor

echo "[2/5] code -> $APP"
mkdir -p "$APP"
rm -rf "$APP/bioreactor_pi"
cp -r "$HERE/bioreactor_pi" "$APP/"
find "$APP" -name "__pycache__" -prune -exec rm -rf {} +

echo "[3/5] Python venv + pyserial (offline wheel first)"
if [[ ! -x "$APP/venv/bin/python" ]]; then
  python3 -m venv "$APP/venv"
fi
"$APP/venv/bin/pip" install --no-index --find-links "$HERE/wheels" pyserial==3.5 \
  || "$APP/venv/bin/pip" install pyserial==3.5

echo "[4/5] config $CONF/config.json, journal $DATA"
mkdir -p "$CONF" "$DATA"
if [[ ! -f "$CONF/config.json" ]]; then
  cp "$HERE/bioreactor_pi/default_config.json" "$CONF/config.json"
  echo "      created $CONF/config.json (edit thresholds / port there)"
else
  echo "      kept the existing $CONF/config.json"
fi
chown -R bioreactor:bioreactor "$DATA"

echo "[5/5] systemd service bioreactor-pi"
sed "s|@SIMULATE@|$SIMULATE|" "$HERE/bioreactor-pi.service" > /etc/systemd/system/bioreactor-pi.service
systemctl daemon-reload
systemctl enable bioreactor-pi
systemctl restart bioreactor-pi
sleep 2
systemctl --no-pager --lines=5 status bioreactor-pi || true

PORT=$(python3 -c "import json;print(json.load(open('$CONF/config.json'))['http']['port'])")
echo
echo "Done. Check from the Pi:      curl http://127.0.0.1:$PORT/health"
echo "Check from the laptop:        http://<Pi address>:$PORT/health   (direct cable: http://192.168.50.2:$PORT/health)"
echo "Logs:                         journalctl -u bioreactor-pi -f"
