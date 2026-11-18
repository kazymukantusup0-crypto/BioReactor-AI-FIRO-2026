#!/usr/bin/env bash
# BioReactor AI — Wi-Fi of the Pi chooses by itself (systemd service bioreactor-wifi, runs as root, no screen needed):
#
#   the phone's hotspot is near   -> the Pi stays on it (development: SSH, internet for updates)
#   no phone network for LOST_S   -> the Pi starts its own Wi-Fi «BioReactor-Pi» (10.42.0.1) for the demo
#   own Wi-Fi with nobody on it for RETRY_PHONE_S -> try the phone once more (back to development by itself);
#                                    if the phone is not there, the own Wi-Fi comes back at once
#   somebody is connected to the own Wi-Fi -> never switch away (the demo is not interrupted)
#   test mode (setup_network.sh hotspot-test, /run/bioreactor-wifi/hold-until) -> stay on the own Wi-Fi until then
#
# The first time the own Wi-Fi comes up after installation, it is on probation: unless someone confirms over the new
# network within 3 min (ssh bio@10.42.0.1 "touch /tmp/bioreactor-hotspot-ok"), everything is rolled back
# (bioreactor-wifi-rollback.sh): own Wi-Fi profile deleted, this service removed, the phone network back —
# but never while the direct cable is connected (the Pi is reachable over it anyway).
# The direct cable (192.168.50.2) is never touched.
# Settings: /etc/default/bioreactor-wifi (PHONE_CON, HOTSPOT_CON, LOST_S, RETRY_PHONE_S). Log: journalctl -u bioreactor-wifi
set -u

PHONE_CON="netplan-wlan0-iPhone"
HOTSPOT_CON="bioreactor-hotspot"
LOST_S=45
RETRY_PHONE_S=300
STEP_S=5
PROBATION=/etc/bioreactor-pi/hotspot-unconfirmed
[[ -f /etc/default/bioreactor-wifi ]] && . /etc/default/bioreactor-wifi

log() { echo "$*"; }
# the connection of wlan0, but only when it is really CONNECTED (state 100): while NetworkManager keeps retrying a phone
# that is gone, the name is still there — that must count as «no network»
active() {
  local state
  state="$(nmcli -g GENERAL.STATE device show wlan0 2>/dev/null | head -1)"
  [[ "$state" == 100* ]] && nmcli -g GENERAL.CONNECTION device show wlan0 2>/dev/null | head -1
}
stations() { /usr/sbin/iw dev wlan0 station dump 2>/dev/null | grep -c '^Station'; }

hotspot_up() {
  log "no phone network for ${LOST_S}s -> own Wi-Fi ${HOTSPOT_CON} (10.42.0.1)"
  if nmcli --wait 30 connection up "$HOTSPOT_CON" >/dev/null; then
    if [[ -f "$PROBATION" ]] && ! systemctl is-active --quiet bioreactor-wifi-rollback.timer; then
      rm -f /tmp/bioreactor-hotspot-ok
      systemd-run --quiet --on-active=180 --unit=bioreactor-wifi-rollback /usr/local/sbin/bioreactor-wifi-rollback
      log "probation: rollback in 3 min unless confirmed over 10.42.0.1"
    fi
  else
    log "own Wi-Fi did not start"
  fi
}

HOLD=/run/bioreactor-wifi/hold-until   # test mode (setup_network.sh hotspot-test): stay on the own Wi-Fi until then
held() { [[ -f "$HOLD" ]] && (( $(date +%s) < $(cat "$HOLD" 2>/dev/null || echo 0) )); }

lost=0
idle=0
seen=-1
log "start: phone=${PHONE_CON} hotspot=${HOTSPOT_CON} lost=${LOST_S}s retry=${RETRY_PHONE_S}s"
while true; do
  now="$(active)"
  if [[ "$now" == "$HOTSPOT_CON" ]]; then
    lost=0
    count="$(stations)"
    if [[ "$count" != "$seen" ]]; then log "devices on the own Wi-Fi: ${count}"; seen="$count"; fi
    if [[ "$count" -eq 0 ]]; then idle=$((idle + STEP_S)); else idle=0; fi
    if held; then idle=0; fi
    if (( idle >= RETRY_PHONE_S )) && ! systemctl is-active --quiet bioreactor-wifi-rollback.timer; then
      log "own Wi-Fi idle ${idle}s -> trying the phone network"
      nmcli connection down "$HOTSPOT_CON" >/dev/null 2>&1
      if nmcli --wait 40 connection up "$PHONE_CON" >/dev/null 2>&1; then
        log "back on ${PHONE_CON}"
      else
        log "phone network not found -> own Wi-Fi again"
        nmcli --wait 30 connection up "$HOTSPOT_CON" >/dev/null 2>&1
      fi
      idle=0
    fi
  elif [[ -n "$now" ]]; then
    lost=0
    idle=0
  else
    lost=$((lost + STEP_S))
    if (( lost >= LOST_S )); then
      hotspot_up
      lost=0
    fi
  fi
  sleep "$STEP_S"
done
