#!/usr/bin/env bash
# BioReactor AI — the Pi's Wi-Fi (systemd service bioreactor-wifi, runs as root, no screen needed).
# Settings: /etc/default/bioreactor-wifi. Log: journalctl -u bioreactor-wifi
#
# MODE=always (default since 2026-11-18) — the Pi's own Wi-Fi «BioReactor-Pi» (10.42.0.1) all the time:
#   at power-on NetworkManager starts it by itself (profile autoconnect, the phone profile has autoconnect off);
#   this service only puts it back if wlan0 is on anything else for HOTSPOT_BACK_S
#   «setup_network.sh online [min]» -> the phone hotspot for a while (internet for the Pi), then back by itself
#   (/run/bioreactor-wifi/online-until); «setup_network.sh back» -> back at once
#
# MODE=auto (the first version) — phone hotspot when near, own Wi-Fi when the phone is gone for LOST_S,
#   back to the phone when nobody uses the own Wi-Fi for RETRY_PHONE_S; first own-Wi-Fi start on probation
#   (3 min, rollback unless confirmed over 10.42.0.1 — never while the direct cable is connected).
# The direct cable (192.168.50.2) is never touched by this service.
set -u

MODE="always"
PHONE_CON="netplan-wlan0-iPhone"
HOTSPOT_CON="bioreactor-hotspot"
LOST_S=45
RETRY_PHONE_S=300
HOTSPOT_BACK_S=20
STEP_S=5
PROBATION=/etc/bioreactor-pi/hotspot-unconfirmed
ONLINE=/run/bioreactor-wifi/online-until
HOLD=/run/bioreactor-wifi/hold-until
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
until_file() { [[ -f "$1" ]] && (( $(date +%s) < $(cat "$1" 2>/dev/null || echo 0) )); }

hotspot_up() {
  log "$1 -> own Wi-Fi ${HOTSPOT_CON} (10.42.0.1)"
  if nmcli --wait 30 connection up "$HOTSPOT_CON" >/dev/null; then
    if [[ "$MODE" == "auto" && -f "$PROBATION" ]] && ! systemctl is-active --quiet bioreactor-wifi-rollback.timer; then
      rm -f /tmp/bioreactor-hotspot-ok
      systemd-run --quiet --on-active=180 --unit=bioreactor-wifi-rollback /usr/local/sbin/bioreactor-wifi-rollback
      log "probation: rollback in 3 min unless confirmed over 10.42.0.1 (never while the cable is connected)"
    fi
  else
    log "own Wi-Fi did not start"
  fi
}

lost=0
idle=0
away=0
seen=-1
log "start: mode=${MODE} phone=${PHONE_CON} hotspot=${HOTSPOT_CON}"
while true; do
  now="$(active)"
  if [[ "$now" == "$HOTSPOT_CON" ]]; then
    lost=0
    away=0
    count="$(stations)"
    if [[ "$count" != "$seen" ]]; then log "devices on the own Wi-Fi: ${count}"; seen="$count"; fi
  fi

  if [[ "$MODE" == "always" ]]; then
    if [[ -f "$ONLINE" ]] && ! until_file "$ONLINE"; then
      rm -f "$ONLINE"
      [[ "$now" != "$HOTSPOT_CON" ]] && hotspot_up "online time is over"
    elif [[ "$now" != "$HOTSPOT_CON" ]] && ! until_file "$ONLINE"; then
      away=$((away + STEP_S))
      if (( away >= HOTSPOT_BACK_S )); then
        hotspot_up "wlan0 not on the own Wi-Fi for ${away}s (now: ${now:-nothing})"
        away=0
      fi
    fi
  else   # MODE=auto
    if [[ "$now" == "$HOTSPOT_CON" ]]; then
      if [[ "$count" -eq 0 ]]; then idle=$((idle + STEP_S)); else idle=0; fi
      if until_file "$HOLD"; then idle=0; fi
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
        hotspot_up "no phone network for ${LOST_S}s"
        lost=0
      fi
    fi
  fi
  sleep "$STEP_S"
done
