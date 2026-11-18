#!/usr/bin/env bash
# BioReactor AI — 3 min after the own Wi-Fi first came up (probation). Started by bioreactor-wifi-watch.sh via systemd-run.
#   confirmed (/tmp/bioreactor-hotspot-ok exists) -> probation ends, everything stays
#   not confirmed -> undo the Wi-Fi setup: own Wi-Fi profile deleted, watcher removed, phone network back
# The direct cable profile (bioreactor-cable, 192.168.50.2) is never touched.
PHONE_CON="netplan-wlan0-iPhone"
HOTSPOT_CON="bioreactor-hotspot"
[[ -f /etc/default/bioreactor-wifi ]] && . /etc/default/bioreactor-wifi

if [[ -f /tmp/bioreactor-hotspot-ok ]]; then
  rm -f /etc/bioreactor-pi/hotspot-unconfirmed
  logger -t bioreactor-wifi "own Wi-Fi confirmed over the new network: probation over"
  exit 0
fi
logger -t bioreactor-wifi "own Wi-Fi NOT confirmed in 3 min: rolling back"
systemctl disable --now bioreactor-wifi.service >/dev/null 2>&1
rm -f /etc/systemd/system/bioreactor-wifi.service /usr/local/sbin/bioreactor-wifi-watch
systemctl daemon-reload
nmcli connection delete "$HOTSPOT_CON" >/dev/null 2>&1
rm -f /etc/bioreactor-pi/hotspot-unconfirmed
nmcli --wait 40 connection up "$PHONE_CON" >/dev/null 2>&1
logger -t bioreactor-wifi "rollback done: phone network ${PHONE_CON}"
