#!/usr/bin/env bash
# BioReactor AI — network laptop <-> Pi WITHOUT internet (NetworkManager: Raspberry Pi OS Bookworm, Debian 13 trixie).
#
#   sudo ./setup_network.sh cable      MAIN: direct Ethernet cable, Pi = 192.168.50.2, laptop gets 192.168.50.x by DHCP (no gateway)
#   sudo ./setup_network.sh hotspot    own Wi-Fi "BioReactor-Pi" (WPA2, Pi = 10.42.0.1, password typed in) + the service
#                                      bioreactor-wifi: phone hotspot near -> stay on it; gone for 45 s -> own Wi-Fi
#   sudo ./setup_network.sh hotspot-remove
#   sudo ./setup_network.sh status
#
# The cable profile does not touch Wi-Fi; the Wi-Fi part never touches the cable.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo" >&2
  exit 1
fi
if ! command -v nmcli >/dev/null; then
  echo "nmcli not found: this script needs NetworkManager (Raspberry Pi OS Bookworm or newer)." >&2
  echo "Older systems: add to /etc/dhcpcd.conf:  interface eth0 / static ip_address=192.168.50.2/24" >&2
  exit 1
fi

case "${1:-}" in
  cable)
    # Pi = 192.168.50.2 and hands the laptop an address by DHCP (NetworkManager "shared" = its own dnsmasq).
    # NO default gateway and NO DNS are sent: the laptop keeps its internet on Wi-Fi, the cable is only for the Pi.
    # Wi-Fi of the Pi is not touched. The Debian 13 netplan profile "netplan-eth0" stays; ours wins by priority.
    # Safety: if the cable link is up, the change is rolled back after 3 min unless someone confirms over the cable:
    #   ssh bio@192.168.50.2 "touch /tmp/bioreactor-net-ok"
    mkdir -p /etc/NetworkManager/dnsmasq-shared.d
    cat > /etc/NetworkManager/dnsmasq-shared.d/bioreactor-no-gateway.conf <<'CONF'
# BioReactor AI: DHCP on the Pi cable gives only an address. Empty value = option is NOT sent.
dhcp-option=3
dhcp-option=6
CONF
    nmcli con delete bioreactor-cable >/dev/null 2>&1 || true
    nmcli con add type ethernet ifname eth0 con-name bioreactor-cable \
      ipv4.method shared ipv4.addresses 192.168.50.2/24 ipv4.never-default yes \
      ipv6.method disabled connection.autoconnect yes connection.autoconnect-priority 10
    if [[ "$(cat /sys/class/net/eth0/carrier 2>/dev/null)" == "1" ]]; then
      rm -f /tmp/bioreactor-net-ok
      systemctl stop bioreactor-net-rollback.timer >/dev/null 2>&1 || true
      systemd-run --quiet --on-active=180 --unit=bioreactor-net-rollback /bin/sh -c \
        'test -f /tmp/bioreactor-net-ok || { nmcli con delete bioreactor-cable; rm -f /etc/NetworkManager/dnsmasq-shared.d/bioreactor-no-gateway.conf; logger "bioreactor: cable profile rolled back (not confirmed)"; }'
      nmcli con up bioreactor-cable
      echo "Cable profile is up. NOT confirmed within 3 min -> rolled back automatically."
      echo "Confirm from the laptop over the cable:  ssh bio@192.168.50.2 \"touch /tmp/bioreactor-net-ok\""
    else
      echo "Cable not plugged in: profile saved, it comes up by itself when the cable is connected (no rollback timer)."
    fi
    echo "Pi: 192.168.50.2. Laptop: Ethernet adapter on automatic (DHCP) gets 192.168.50.x, no gateway, no DNS."
    echo "Laptop pi_url: http://192.168.50.2:8780.  Undo: sudo nmcli con delete bioreactor-cable"
    ;;
  hotspot)
    # The Pi's own Wi-Fi «BioReactor-Pi» (WPA2), Pi = 10.42.0.1, the laptop gets 10.42.0.x by DHCP (no gateway, no DNS:
    # dnsmasq-shared.d/bioreactor-no-gateway.conf from «cable»). The password is typed here and kept ONLY in the
    # NetworkManager profile on the Pi (root-only file), never in the project.
    # Nothing changes now: the service bioreactor-wifi switches to this Wi-Fi only when the phone network is gone
    # for 45 s (and back to the phone when nobody uses this Wi-Fi). First start = probation, see wifi/*.sh.
    HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PHONE_CON="$(nmcli -t -f NAME,TYPE,AUTOCONNECT con show | awk -F: '$2=="802-11-wireless" && $3=="yes" && $1!="bioreactor-hotspot" {print $1; exit}')"
    if [[ -z "$PHONE_CON" ]]; then
      echo "No phone Wi-Fi profile with autoconnect found (nmcli con show)." >&2
      exit 1
    fi
    while true; do
      read -rsp "Password for the Wi-Fi BioReactor-Pi (8-63 characters): " PASSWORD; echo
      read -rsp "Again: " PASSWORD2; echo
      if [[ "$PASSWORD" != "$PASSWORD2" ]]; then echo "Not the same, again."; continue; fi
      if (( ${#PASSWORD} < 8 || ${#PASSWORD} > 63 )); then echo "8-63 characters, again."; continue; fi
      break
    done
    mkdir -p /etc/NetworkManager/dnsmasq-shared.d /etc/bioreactor-pi
    if [[ ! -f /etc/NetworkManager/dnsmasq-shared.d/bioreactor-no-gateway.conf ]]; then
      printf '# BioReactor AI: DHCP of the Pi gives only an address. Empty value = option is NOT sent.\ndhcp-option=3\ndhcp-option=6\n' \
        > /etc/NetworkManager/dnsmasq-shared.d/bioreactor-no-gateway.conf
    fi
    nmcli con delete bioreactor-hotspot >/dev/null 2>&1 || true
    nmcli con add type wifi ifname wlan0 con-name bioreactor-hotspot autoconnect no ssid BioReactor-Pi \
      802-11-wireless.mode ap 802-11-wireless.band bg 802-11-wireless.channel 6 \
      ipv4.method shared ipv4.addresses 10.42.0.1/24 ipv4.never-default yes ipv6.method disabled \
      wifi-sec.key-mgmt wpa-psk wifi-sec.proto rsn wifi-sec.pairwise ccmp wifi-sec.group ccmp wifi-sec.pmf disable >/dev/null
    # The password goes straight into the root-only profile file (through an environment variable, never on a command
    # line that «ps» could show). The own Wi-Fi is NOT started now: the Pi stays on the phone network.
    KEYFILE=/etc/NetworkManager/system-connections/bioreactor-hotspot.nmconnection
    if [[ ! -f "$KEYFILE" ]] || ! grep -q '^\[wifi-security\]' "$KEYFILE"; then
      echo "Profile file $KEYFILE not found — stop." >&2
      exit 1
    fi
    PSK="$PASSWORD" awk '{ print } /^\[wifi-security\]$/ { p = ENVIRON["PSK"]; gsub(/\\/, "\\\\", p); print "psk=" p }' \
      "$KEYFILE" > "$KEYFILE.new"
    chmod 600 "$KEYFILE.new"
    mv "$KEYFILE.new" "$KEYFILE"
    unset PASSWORD PASSWORD2
    nmcli con reload
    if [[ -z "$(nmcli -s -g 802-11-wireless-security.psk con show bioreactor-hotspot 2>/dev/null)" ]]; then
      echo "The password was not stored in the profile — stop, nothing else changed." >&2
      exit 1
    fi
    printf 'PHONE_CON="%s"\nHOTSPOT_CON="bioreactor-hotspot"\nLOST_S=45\nRETRY_PHONE_S=300\n' "$PHONE_CON" > /etc/default/bioreactor-wifi
    install -m 755 "$HERE/wifi/bioreactor-wifi-watch.sh" /usr/local/sbin/bioreactor-wifi-watch
    install -m 755 "$HERE/wifi/bioreactor-wifi-rollback.sh" /usr/local/sbin/bioreactor-wifi-rollback
    install -m 644 "$HERE/wifi/bioreactor-wifi.service" /etc/systemd/system/bioreactor-wifi.service
    touch /etc/bioreactor-pi/hotspot-unconfirmed
    systemctl daemon-reload
    systemctl enable --now bioreactor-wifi.service >/dev/null
    echo "Wi-Fi BioReactor-Pi ready (WPA2, Pi = 10.42.0.1, no internet). Phone network: ${PHONE_CON}."
    echo "Now: phone near -> the Pi stays on it. Phone off for 45 s -> the Pi starts BioReactor-Pi."
    echo "First start is on probation: confirm within 3 min over the new Wi-Fi: ssh bio@10.42.0.1 \"touch /tmp/bioreactor-hotspot-ok\""
    echo "Log: journalctl -u bioreactor-wifi -f.  Remove: sudo $0 hotspot-remove"
    ;;
  hotspot-remove)
    systemctl disable --now bioreactor-wifi.service >/dev/null 2>&1 || true
    rm -f /etc/systemd/system/bioreactor-wifi.service /usr/local/sbin/bioreactor-wifi-watch /usr/local/sbin/bioreactor-wifi-rollback \
      /etc/default/bioreactor-wifi /etc/bioreactor-pi/hotspot-unconfirmed
    systemctl daemon-reload
    nmcli con delete bioreactor-hotspot >/dev/null 2>&1 || true
    echo "Own Wi-Fi removed; the phone network and the cable are unchanged."
    ;;
  status)
    nmcli -f NAME,DEVICE,STATE con show --active
    ip -4 -br addr
    systemctl is-active bioreactor-wifi 2>/dev/null | sed 's/^/bioreactor-wifi: /'
    [[ -f /etc/bioreactor-pi/hotspot-unconfirmed ]] && echo "own Wi-Fi: on probation (not confirmed yet)"
    true
    ;;
  *)
    echo "usage: sudo $0 cable | hotspot | hotspot-remove | status" >&2
    exit 1
    ;;
esac
